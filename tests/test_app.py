import time
from pathlib import Path

from fastapi.testclient import TestClient

from src.pitchguard import ROOT
from src.server import create_app


def test_advice_and_invalid_inputs(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/').status_code==200
        response=client.post('/api/advice',json={'opponent':'4-4-2','objective':'keep_ball'})
        assert response.status_code==200
        assert response.json()['opponent']['strengths']
        assert response.json()['recommended']['reason']
        assert client.post('/api/advice',json={'opponent':'banana'}).status_code==422
        assert client.post('/api/advice',json={'squad':{'passing':9}}).status_code==422
        assert client.get('/api/jobs/not-a-record').status_code==404
        assert client.get('/api/uploads/not-a-record/frame').status_code==404


def test_upload_errors_do_not_leave_partial_files(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.post('/api/uploads',files={'file':('notes.txt',b'bad','text/plain')}).status_code==415
        assert client.post('/api/uploads',files={'file':('bad.mp4',b'not video','video/mp4')}).status_code==422
        assert not list((tmp_path/'uploads').iterdir())


def test_video_job_review_export_and_deletion(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        with (ROOT/'data/synthetic_input.avi').open('rb') as f:
            upload=client.post('/api/uploads',files={'file':('match.avi',f,'video/x-msvideo')})
        assert upload.status_code==201
        meta=upload.json();assert 'path' not in meta
        assert client.get(f'/api/uploads/{meta["id"]}/frame?time_s=0').headers['content-type']=='image/jpeg'
        config={'detector':'markers','sample_fps':5,'corners':[[110,70],[850,105],[925,550],[35,550]]}
        response=client.post('/api/jobs',json={'upload_id':meta['id'],'config':config})
        assert response.status_code==202
        job_id=response.json()['id']
        until=time.monotonic()+90
        while time.monotonic()<until:
            state=client.get(f'/api/jobs/{job_id}').json()
            if state['status'] not in ('queued','running'):break
            time.sleep(.1)
        assert state['status']=='completed',state
        output=client.get(f'/api/jobs/{job_id}/result').json()
        assert output['summary']['formation_coverage']==1
        drift=next(e for e in output['events'] if e['kind']=='role_drift')
        assert drift['start_s']==2 and drift['detected_s']==2.8
        saved=client.put(f'/api/jobs/{job_id}/events/{drift["id"]}/review',json={'status':'confirmed','notes':'Cover the channel','reviewer':'Test coach'})
        assert saved.status_code==200
        exported=client.get(f'/api/jobs/{job_id}/export/result.json').json()
        assert exported['events'][0]['review']['notes']=='Cover the channel'
        csv=client.get(f'/api/jobs/{job_id}/export/tracks.csv')
        assert csv.status_code==200 and 'track_id,team' in csv.text
        assert client.get(f'/api/jobs/{job_id}/export/status.json').status_code==404
        assert client.delete(f'/api/uploads/{meta["id"]}').status_code==409
        assert client.delete(f'/api/jobs/{job_id}').status_code==204
        assert client.delete(f'/api/uploads/{meta["id"]}').status_code==204
