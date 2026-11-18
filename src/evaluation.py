"""Label-driven held-out evaluation; never treats generated predictions as truth."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from .pipeline import save_json


def validate_splits(manifest):
    clips=manifest.get('clips',[])
    if not clips:raise ValueError('Dataset manifest needs clips')
    matches={}
    for clip in clips:
        if clip.get('split') not in ('train','validation','test') or not clip.get('match_id'):
            raise ValueError('Every clip needs a split and match_id')
        previous=matches.setdefault(clip['match_id'],clip['split'])
        if previous!=clip['split']:raise ValueError('A match occurs in multiple splits; split leakage detected')
        if not clip.get('permission_note'):raise ValueError('Record dataset access/provenance in permission_note')
    return clips


def evaluate_locations(result,labels,gate_m=2):
    truth_frames=labels.get('frames',[])
    if not truth_frames:raise ValueError('No manually labelled frames supplied')
    predictions={r['frame']:r for r in result['timeline']}
    tp=fp=fn=0;errors=[];coverage=0;switches=0;prior_ids={};camera_errors=[]
    for truth in truth_frames:
        row=predictions.get(truth['frame'])
        if row is None:raise ValueError(f'Labelled frame {truth["frame"]} is not an analysis sample; align sample rate and labels')
        coverage+=int(row['shape']['valid'])
        observations=row['observations']
        fp+=sum(o['team']=='unknown' or o['xy'] is None for o in observations)
        for team in ('own','opponent'):
            actual=[p for p in truth['players'] if p['team']==team]
            guessed=[p for p in observations if p['team']==team and p['xy'] is not None]
            matched=0
            if actual and guessed:
                cost=np.linalg.norm(np.array([p['xy'] for p in actual])[:,None,:]-np.array([p['xy'] for p in guessed])[None,:,:],axis=2)
                rows,cols=linear_sum_assignment(cost)
                for i,j in zip(rows,cols):
                    if cost[i,j]>=gate_m:continue
                    matched+=1;errors.append(float(cost[i,j]))
                    truth_id=actual[i].get('identity');prediction_id=guessed[j].get('track_id')
                    if truth_id is not None and prediction_id is not None:
                        key=(team,truth_id)
                        if key in prior_ids and prior_ids[key]!=prediction_id:switches+=1
                        prior_ids[key]=prediction_id
            tp+=matched;fp+=len(guessed)-matched;fn+=len(actual)-matched
        if truth.get('landmarks') and row.get('image_to_pitch') is not None:
            import cv2
            inverse=np.linalg.inv(np.array(row['image_to_pitch']))
            world=np.float32([p['world_xy'] for p in truth['landmarks']]).reshape(1,-1,2)
            mapped=cv2.perspectiveTransform(world,inverse)[0]
            image=np.array([p['image_xy'] for p in truth['landmarks']])
            camera_errors.extend(np.linalg.norm(mapped-image,axis=1).tolist())
    return {'labelled_frames':len(truth_frames),'precision':tp/max(tp+fp,1),'recall':tp/max(tp+fn,1),
            'mean_position_error_m':float(np.mean(errors)) if errors else None,'accepted_pairs':tp,
            'team_shape_coverage':coverage/len(truth_frames),'identity_switches':switches,
            'calibration_error_px':float(np.mean(camera_errors)) if camera_errors else None,
            'calibration_error_source':'Independent labelled landmark error, when supplied'}


def interval_iou(a,b):
    overlap=max(0,min(a['end_s'],b['end_s'])-max(a['start_s'],b['start_s']))
    union=max(a['end_s'],b['end_s'])-min(a['start_s'],b['start_s'])
    return overlap/max(union,.0001)


def evaluate_events(result,labels,minimum_iou=.3):
    if not labels.get('events_reviewed'):
        raise ValueError('Event evaluation requires coach-reviewed labels, including reviewed negative intervals')
    intervals=labels.get('reviewed_intervals',[])
    if not intervals:raise ValueError('State which time intervals the coach reviewed')
    ordered=sorted(intervals)
    if any(start<0 or end<=start for start,end in ordered) or any(a[1]>b[0] for a,b in zip(ordered,ordered[1:])):
        raise ValueError('Reviewed intervals must be positive, ordered and nonoverlapping')
    def covered(e):return any(start<=e['start_s'] and e['end_s']<=end for start,end in intervals)
    def reviewed_duration(start,end):
        return sum(max(0,min(end,b)-max(start,a)) for a,b in intervals)
    truth=labels.get('events',[])
    if any(not covered(e) or e['end_s']<=e['start_s'] for e in truth):
        raise ValueError('Every labelled issue must be inside a reviewed interval and have positive duration')
    # Include observations crossing a review boundary. Dropping those would hide
    # false alarms, especially when a coach reviews a short negative interval.
    predicted=[e for e in result['events'] if reviewed_duration(e['start_s'],e['end_s'])>0]
    matches=[]
    if truth and predicted:
        cost=np.ones((len(truth),len(predicted)))
        for i,a in enumerate(truth):
            for j,b in enumerate(predicted):
                if a['kind']==b['kind']:
                    intersection=reviewed_duration(max(a['start_s'],b['start_s']),min(a['end_s'],b['end_s']))
                    union=reviewed_duration(a['start_s'],a['end_s'])+reviewed_duration(b['start_s'],b['end_s'])-intersection
                    score=intersection/max(union,.0001)
                    cost[i,j]=1-score if score>=minimum_iou else 1e6
                else:cost[i,j]=1e6
        rows,cols=linear_sum_assignment(cost)
        matches=[(i,j) for i,j in zip(rows,cols) if 1-cost[i,j]>=minimum_iou]
    latencies=[predicted[j]['detected_s']-truth[i]['start_s'] for i,j in matches]
    seconds=sum(end-start for start,end in intervals)
    return {'true_positives':len(matches),'false_positives':len(predicted)-len(matches),'false_negatives':len(truth)-len(matches),
            'precision':len(matches)/len(predicted) if predicted else None,'recall':len(matches)/len(truth) if truth else None,
            'mean_onset_latency_s':float(np.mean(latencies)) if latencies else None,
            'false_alarms_per_reviewed_minute':(len(predicted)-len(matches))/(seconds/60),
            'reviewed_seconds':seconds,'minimum_interval_iou':minimum_iou}


def reviewer_agreement(first,second):
    a={r['item_id']:r['judgement'] for r in first};b={r['item_id']:r['judgement'] for r in second}
    common=set(a)&set(b)
    if not common:raise ValueError('No shared review items')
    return {'shared_items':len(common),'raw_agreement':sum(a[k]==b[k] for k in common)/len(common),
            'disagreements':sorted(k for k in common if a[k]!=b[k])}


def compare_targets(metrics,targets):
    checks=[]
    for name,rule in targets.items():
        value=metrics.get(name)
        passed=value is not None and (value>=rule['min'] if 'min' in rule else value<=rule['max'])
        checks.append({'metric':name,'value':value,'target':rule,'passed':bool(passed)})
    return {'checks':checks,'passed':bool(checks) and all(c['passed'] for c in checks)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Evaluate measured predictions against separate human labels')
    parser.add_argument('--result',required=True);parser.add_argument('--labels',required=True)
    parser.add_argument('--manifest',required=True);parser.add_argument('--clip-id',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--targets')
    args=parser.parse_args();manifest=json.loads(Path(args.manifest).read_text())
    clips=validate_splits(manifest);clip=next((c for c in clips if c['id']==args.clip_id),None)
    if clip is None or clip['split']!='test':raise SystemExit('Select a declared held-out test clip')
    labels=json.loads(Path(args.labels).read_text());result=json.loads(Path(args.result).read_text())
    if labels.get('clip_id')!=args.clip_id:raise SystemExit('Label clip_id does not match selected clip')
    if labels.get('input_sha256') and labels['input_sha256']!=result['manifest']['input_sha256']:
        raise SystemExit('Human labels refer to a different source video checksum')
    report={'clip_id':args.clip_id,'locations':evaluate_locations(result,labels) if labels.get('frames') else None,
            'events':None,'annotation_context':labels.get('annotation_context','Externally supplied labels')}
    if labels.get('events_reviewed'):report['events']=evaluate_events(result,labels)
    if report['locations'] is None and report['events'] is None:
        raise SystemExit('Supply labelled player frames or completed coach-reviewed event intervals; a draft review cannot establish accuracy')
    if args.targets:
        targets=json.loads(Path(args.targets).read_text())
        if not targets.get('approved_by') or not targets.get('frozen_before_test'):
            raise SystemExit('Targets need reviewer approval and frozen_before_test declaration')
        report['acceptance']={section:compare_targets(report.get(section) or {},rules) for section,rules in targets['metrics'].items()}
    save_json(args.output,report);print(json.dumps(report,indent=2))
