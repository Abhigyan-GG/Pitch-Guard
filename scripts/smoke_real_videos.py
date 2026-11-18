"""Process the two user-supplied clips through the real HTTP job workflow.

Calibration is manually estimated for engineering smoke tests, not labelled truth.
No published source video or coach annotation is fabricated by this check.
"""
import json
import time
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    report={'evidence_type':'Unlabelled real-video engineering smoke tests','clips':[]}
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=60) as client:
        examples=client.get('/api/examples').json()
        for name in ['Top View','gettyimages-1293195390']:
            example=next((e for e in examples if e['name'].startswith(name)),None)
            if example is None:raise SystemExit(f'Missing user clip: {name}')
            response=client.post('/api/examples/'+example['id']);response.raise_for_status();upload=response.json()
            if name=='Top View':
                config={'corners':[[960,250],[1258,550],[960,850],[660,550]],
                        'world_points':[[52.5,24.85],[61.65,34],[52.5,43.15],[43.35,34]],
                        'detector':'overhead','own_colour':'#d16d3a','opponent_colour':'#80f78e','sample_fps':2}
            else:
                config={'corners':[[111,47],[651,47],[765,425],[5,425]],'detector':'players',
                        'own_colour':'#ecece5','opponent_colour':'#2a4850','confidence':.15,'sample_fps':2}
            response=client.post('/api/jobs',json={'upload_id':upload['id'],'config':config});response.raise_for_status();job_id=response.json()['id']
            last=None;deadline=time.monotonic()+600
            while time.monotonic()<deadline:
                response=client.get('/api/jobs/'+job_id);response.raise_for_status();job=response.json()
                if job['message']!=last:print(example['name'][:32],job['status'],job['message'],flush=True);last=job['message']
                if job['status'] not in ('running','queued'):break
                time.sleep(.5)
            if job['status']!='completed':raise SystemExit(str(job))
            result=client.get(f'/api/jobs/{job_id}/result').json()
            assert result['timeline'] and result['timeline'][-1]['time_s']>=upload['video']['duration_s']-.6
            for filename in ['result.json','tracks.csv','annotated.avi','manifest.json']:
                response=client.get(f'/api/jobs/{job_id}/export/{filename}');response.raise_for_status();assert response.content
            report['clips'].append({'name':upload['name'],'job_id':job_id,'video':upload['video'],
                                    'summary':result['summary'],'warnings':result['warnings'],
                                    'model':result['manifest']['model'],'runtime_seconds':result['manifest']['seconds'],
                                    'calibration_note':'Manual approximate landmarks for smoke testing, not independently verified ground truth'})
    (ROOT/'results/real_video_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
