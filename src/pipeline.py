"""Reproducible video-to-tracks-to-coaching pipeline, independent of HTTP."""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import time
from pathlib import Path

import cv2
import numpy as np

from .coaching import EventEngine, analyse_shape
from .pitchguard import open_writer, project
from .schemas import AnalysisConfig
from .vision import CameraRegistration, KitClassifier, PersonDetector, Tracker, marker_observations, overhead_observations

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/".runtime"
MODEL=ROOT/"models"/"yolov8n.pt"


def checksum(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()


def inspect_video(path):
    cap=cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():raise ValueError("Cannot decode this video. Try an MP4 with H.264 encoding.")
        fps=float(cap.get(cv2.CAP_PROP_FPS));count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w,h=int(cap.get(3)),int(cap.get(4))
        if not np.isfinite(fps) or not .5<=fps<=240 or count<=0 or not 64<=w<=7680 or not 64<=h<=4320:
            raise ValueError("Video metadata is unsupported or invalid")
        if count/fps>3*60*60:raise ValueError("Use videos up to three hours, or split this recording into halves.")
        ok,_=cap.read()
        if not ok:raise ValueError("Video contains no readable frames")
        return {"width":w,"height":h,"fps":fps,"frame_count":count,"duration_s":round(count/fps,3)}
    finally:cap.release()


def read_frame(path,time_s):
    cap=cv2.VideoCapture(str(path))
    try:
        fps=cap.get(cv2.CAP_PROP_FPS)
        cap.set(cv2.CAP_PROP_POS_FRAMES,max(0,int(time_s*fps)))
        ok,frame=cap.read()
        if not ok:raise ValueError("No readable frame at this time")
        return frame
    finally:cap.release()


def save_json(path,data):
    path=Path(path)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(data,indent=2,allow_nan=False),encoding="utf-8")
    temporary.replace(path)


def run_analysis(video,out,config:AnalysisConfig,progress=lambda fraction,message:None,cancelled=lambda:False):
    started=time.perf_counter();video=Path(video);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    info=inspect_video(video);end=config.end_s or info['duration_s']
    if config.start_s>=info['duration_s'] or end>info['duration_s']+.05:
        raise ValueError("Analysis interval must be inside the video")
    for points in [config.corners]+[k.corners for k in config.keyframes]:
        if any(not 0<=p[0]<=info['width'] or not 0<=p[1]<=info['height'] for p in points):
            raise ValueError("Calibration points must lie inside the video image")
    if any(k.time_s>=end for k in config.keyframes):raise ValueError("Calibration keyframe is outside the video interval")
    stride=max(1,int(round(info['fps']/config.sample_fps)))
    effective_fps=info['fps']/stride
    first_idx=int(round(config.start_s*info['fps']));last_idx=min(info['frame_count'],int(np.ceil(end*info['fps'])))
    total=(last_idx-first_idx+stride-1)//stride
    if total>60000:raise ValueError("More than 60,000 analysis samples. Reduce sample rate or split the video.")
    progress(.01,"Preparing detector and calibration")
    os.environ.setdefault("YOLO_CONFIG_DIR",str(RUNTIME/"ultralytics"))
    detector=PersonDetector(MODEL,config.confidence) if config.detector=='players' else None
    classifier=KitClassifier(config.own_colour,config.opponent_colour)
    reference=read_frame(video,config.start_s)
    registration=CameraRegistration(reference,config.corners,config.compensate_camera,config.world_points)
    tracker=Tracker();engine=EventEngine(config.thresholds.persistence_s,max(1.1,2/effective_fps))
    cap=cv2.VideoCapture(str(video));cap.set(cv2.CAP_PROP_POS_FRAMES,first_idx)
    writer=None;timeline=[];keyframes=iter(config.keyframes);next_key=next(keyframes,None)
    previous_camera_valid=True;rejected=0;sampled=0
    try:
        writer=open_writer(out/'annotated.avi',effective_fps,(info['width'],info['height']))
        for index in range(first_idx,last_idx):
            if cancelled():raise InterruptedError("Analysis cancelled")
            if (index-first_idx)%stride:
                if not cap.grab():break
                continue
            ok,frame=cap.read()
            if not ok:break
            time_s=index/info['fps']
            if frame.shape[:2]!=(info['height'],info['width']):raise ValueError("Video resolution changed during analysis")
            while next_key is not None and time_s>=next_key.time_s:
                ref=read_frame(video,next_key.time_s)
                registration=CameraRegistration(ref,next_key.corners,config.compensate_camera,next_key.world_points or config.world_points)
                tracker.reset();next_key=next(keyframes,None)
            H,camera=registration.update(frame)
            if H is None:
                rejected+=1
                if previous_camera_valid:tracker.reset()
            previous_camera_valid=H is not None
            if config.detector=='markers':
                observations=marker_observations(frame,H) if H is not None else []
            elif config.detector=='overhead':
                observations=overhead_observations(frame,classifier.colours,H,config.overhead_tolerance)
            else:
                observations=detector(frame)
                for o in observations:
                    classifier.assign(frame,o)
                    if H is not None:
                        xy=project([o.footpoint],H)[0]
                        if np.isfinite(xy).all() and 0<=xy[0]<=105 and 0<=xy[1]<=68:o.xy=xy.tolist()
            observations=tracker.update(observations,time_s)
            possession=config.possession
            for segment in config.possession_segments:
                if segment.start_s<=time_s<segment.end_s:possession=segment.possession;break
            state=analyse_shape(observations,config.formation,config.direction,possession,config.thresholds.model_dump(exclude={'persistence_s'}))
            if H is None:
                state.update(valid=False,local_valid=False,local_signals=[],signals=[],reason=camera['reason'])
            event_ids=engine.update(time_s,state)
            timeline.append({'frame':index,'time_s':round(time_s,3),'camera':camera,
                             'observations':[o.record() for o in observations],'shape':state,'active_events':event_ids})
            overlay=frame.copy()
            for o in observations:
                colour={'own':(80,225,170),'opponent':(65,145,250),'unknown':(150,150,150)}[o.team]
                x1,y1,x2,y2=map(int,o.box)
                cv2.rectangle(overlay,(x1,y1),(x2,y2),colour,2)
                cv2.putText(overlay,f'{o.team} #{o.track_id or "?"}',(x1,max(18,y1-5)),cv2.FONT_HERSHEY_SIMPLEX,.45,colour,1)
            cv2.putText(overlay,f'{time_s:.1f}s | {"Shape review" if state["valid"] else "Partial / uncertain view"}',(18,28),cv2.FONT_HERSHEY_SIMPLEX,.7,(255,255,255),2)
            writer.write(overlay);sampled+=1
            if sampled==1 or sampled%10==0:progress(min(.98,sampled/max(total,1)),f'Analysed {sampled}/{total} samples')
    finally:
        cap.release()
        if writer is not None:writer.release()
    if not sampled:raise ValueError("No frames were analysed")
    if len(timeline)<total-1:raise ValueError("Video ended before its declared interval; export is incomplete")
    valid=sum(t['shape']['valid'] for t in timeline)
    local=sum(bool(t['shape'].get('local_valid')) for t in timeline)
    counts=[len(t['observations']) for t in timeline]
    warnings=[]
    if config.detector=='markers':warnings.append('Synthetic marker mode: these results are not real-player measurements.')
    if config.detector=='overhead':warnings.append('Overhead kit blobs can include nonplayers and split or merge jerseys. Confirm detections before interpreting distances.')
    if valid/sampled<.5:warnings.append('Most frames do not show enough confidently assigned players for whole-team formation analysis. Local support observations may omit off-screen teammates.')
    if rejected:warnings.append(f'Camera calibration was unavailable in {rejected} samples. Pitch-based analysis abstained during those samples; add calibration keyframes for those sections.')
    if not any(counts):warnings.append('No people were detected. Try overhead mode for aerial footage, a lower confidence threshold, or a clearer wide-angle clip.')
    manifest={'schema_version':1,'created_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
              'input_sha256':checksum(video),'configuration':config.model_dump(),
              'model':{'name':'YOLOv8n COCO person' if detector else config.detector,
                       'weights_sha256':checksum(MODEL) if detector else None,
                       'ultralytics_version':importlib.metadata.version('ultralytics') if detector else None},
              'python':platform.python_version(),'opencv':cv2.__version__,'numpy':np.__version__,
              'video':info,'effective_sample_fps':round(effective_fps,4),
              'timing_scope':'Entire processing pipeline, including decoding, registration, detection, tactics and video writing',
              'seconds':round(time.perf_counter()-started,3),
              'evidence_status':'Engineering run; no held-out tactical accuracy or coach agreement claimed'}
    result={'summary':{'samples':sampled,'formation_coverage':round(valid/sampled,4),
                       'local_only_coverage':round(local/sampled,4),'camera_coverage':round(1-rejected/sampled,4),
                       'events':len(engine.events),'average_detections':round(float(np.mean(counts)),2),
                       'start_s':config.start_s,'end_s':end},
            'events':engine.events,'timeline':timeline,'warnings':warnings,'manifest':manifest}
    save_json(out/'result.json',result);save_json(out/'manifest.json',manifest)
    with (out/'tracks.csv').open('w',newline='',encoding='utf-8') as f:
        fields=['frame','time_s','track_id','team','confidence','team_confidence','x_m','y_m','foot_u','foot_v','observed']
        writer_csv=csv.DictWriter(f,fieldnames=fields);writer_csv.writeheader()
        for row in timeline:
            for o in row['observations']:
                xy=o['xy'] or [None,None]
                writer_csv.writerow({'frame':row['frame'],'time_s':row['time_s'],'track_id':o['track_id'],
                                     'team':o['team'],'confidence':o['confidence'],'team_confidence':o['team_confidence'],
                                     'x_m':xy[0],'y_m':xy[1],'foot_u':o['footpoint'][0],'foot_v':o['footpoint'][1],'observed':True})
    progress(1.,'Ready for review')
    return result
