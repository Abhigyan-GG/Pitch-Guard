"""Local coaching application: bounded uploads, durable jobs and review exports."""
from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import cv2
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .formations import PROFILES, anchors, recommend
from .pipeline import MODEL, ROOT, inspect_video, read_frame, run_analysis, save_json
from .schemas import AdviceRequest, ReviewRequest, StartRequest


def create_app(runtime=None):
    runtime=Path(runtime or ROOT/'.runtime');uploads=runtime/'uploads';jobs=runtime/'jobs'
    uploads.mkdir(parents=True,exist_ok=True);jobs.mkdir(parents=True,exist_ok=True)
    lock=threading.RLock();executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='pitchguard')
    cancellations={};futures={}
    maximum=int(os.environ.get('PITCHGUARD_MAX_UPLOAD_MB','2048'))*1024*1024

    @asynccontextmanager
    async def lifespan(app):
        # No job is resumed from stale metadata. Mark interrupted work explicitly.
        for path in jobs.glob('*/status.json'):
            saved=json.loads(path.read_text())
            if saved['status'] in ('queued','running'):
                saved.update(status='interrupted',message='Server restarted. Start a new analysis to continue.')
                save_json(path,saved)
        yield
        for event in cancellations.values():event.set()
        executor.shutdown(wait=True,cancel_futures=True)

    app=FastAPI(title='PitchGuard Coaching Studio',version='2.0.0',lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','[::1]','testserver'])

    def identity(value):
        if len(value)!=32 or any(c not in '0123456789abcdef' for c in value):
            raise HTTPException(404,'Record not found')
        return value

    def metadata(upload_id):
        path=uploads/identity(upload_id)/'metadata.json'
        if not path.is_file():raise HTTPException(404,'Upload not found')
        return json.loads(path.read_text())

    def status(job_id):
        path=jobs/identity(job_id)/'status.json'
        if not path.is_file():raise HTTPException(404,'Analysis not found')
        return json.loads(path.read_text())

    def result(job_id):
        saved=status(job_id)
        if saved['status']!='completed':raise HTTPException(409,'Analysis is not ready for review')
        return json.loads((jobs/job_id/'result.json').read_text())

    def public_upload(meta):
        return {k:v for k,v in meta.items() if k!='path'}

    @app.get('/api/health')
    def health():
        return {'status':'ok','model_ready':MODEL.is_file(),'max_upload_mb':maximum//(1024*1024),
                'version':'2.0.0'}

    @app.get('/api/formations')
    def formations():
        return {key:{**value,'anchors':anchors(key).tolist()} for key,value in PROFILES.items()}

    @app.post('/api/advice')
    def advice(request:AdviceRequest):
        return recommend(request.opponent,request.objective,request.squad,request.current)

    @app.get('/api/examples')
    def examples():
        available=[{'id':'demo','name':'Six-second synthetic demonstration','kind':'synthetic'}] if (ROOT/'data/synthetic_input.avi').exists() else []
        for i,p in enumerate(sorted(ROOT.glob('*.mp4'))):
            available.append({'id':f'local-{i}','name':p.name,'kind':'user-supplied video'})
        return available

    @app.post('/api/examples/{example_id}')
    def use_example(example_id:str):
        if example_id=='demo':path=ROOT/'data/synthetic_input.avi'
        else:
            paths=sorted(ROOT.glob('*.mp4'))
            try:path=paths[int(example_id.removeprefix('local-'))]
            except (ValueError,IndexError):raise HTTPException(404,'Example not found')
            if not example_id.startswith('local-') or int(example_id[6:])<0:raise HTTPException(404,'Example not found')
        if not path.is_file():raise HTTPException(404,'Example not found')
        key=uuid.uuid4().hex;directory=uploads/key;directory.mkdir()
        meta={'id':key,'name':path.name,'path':str(path.resolve()),'video':inspect_video(path),'example':example_id,'created_utc':datetime.now(timezone.utc).isoformat()}
        save_json(directory/'metadata.json',meta)
        return public_upload(meta)

    @app.post('/api/uploads',status_code=201)
    async def upload(file:UploadFile=File(...)):
        suffix=Path(file.filename or '').suffix.lower()
        if suffix not in ('.mp4','.mov','.avi','.mkv','.webm','.m4v'):
            await file.close();raise HTTPException(415,'Choose MP4, MOV, AVI, MKV, M4V or WebM video')
        key=uuid.uuid4().hex;directory=uploads/key;directory.mkdir()
        path=directory/f'input{suffix}';size=0
        try:
            with path.open('wb') as f:
                while chunk:=await file.read(1024*1024):
                    size+=len(chunk)
                    if size>maximum:raise HTTPException(413,f'Upload exceeds {maximum//(1024*1024)} MB. Split the match into halves.')
                    f.write(chunk)
            info=inspect_video(path)
            meta={'id':key,'name':Path((file.filename or 'match').replace('\\','/')).name[:200],
                  'path':str(path.resolve()),'video':info,'size_bytes':size,'created_utc':datetime.now(timezone.utc).isoformat()}
            save_json(directory/'metadata.json',meta)
            return public_upload(meta)
        except ValueError as exc:
            shutil.rmtree(directory);raise HTTPException(422,str(exc))
        except BaseException:
            shutil.rmtree(directory);raise
        finally:await file.close()

    @app.get('/api/uploads/{upload_id}/frame')
    def frame(upload_id:str,time_s:float=Query(0,ge=0)):
        meta=metadata(upload_id)
        if time_s>=meta['video']['duration_s']:raise HTTPException(422,'Time lies outside the video')
        try:image=read_frame(meta['path'],time_s)
        except ValueError as exc:raise HTTPException(422,str(exc))
        ok,encoded=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,85])
        if not ok:raise HTTPException(500,'Cannot render frame')
        return Response(encoded.tobytes(),media_type='image/jpeg',headers={'Cache-Control':'private, max-age=60'})

    @app.get('/api/jobs')
    def list_jobs():
        return sorted([json.loads(p.read_text()) for p in jobs.glob('*/status.json')],key=lambda j:j['created_utc'],reverse=True)[:50]

    @app.post('/api/jobs',status_code=202)
    def start(request:StartRequest):
        meta=metadata(request.upload_id)
        if request.config.detector=='players' and not MODEL.exists():raise HTTPException(409,'Install player weights using python scripts/setup_model.py --download')
        duration=meta['video']['duration_s'];config=request.config
        if config.start_s>=duration or (config.end_s and config.end_s>duration+.05):
            raise HTTPException(422,'Analysis interval is outside the video')
        if any(not 0<=p[0]<=meta['video']['width'] or not 0<=p[1]<=meta['video']['height'] for p in config.corners):
            raise HTTPException(422,'Calibration points must be inside the video')
        key=uuid.uuid4().hex;directory=jobs/key
        with lock:
            active=sum(json.loads(p.read_text())['status'] in ('queued','running') for p in jobs.glob('*/status.json'))
            if active>=4:raise HTTPException(429,'Four analyses are queued. Wait for one to finish or cancel it.')
            directory.mkdir();cancel=threading.Event();cancellations[key]=cancel
            state={'id':key,'upload_id':meta['id'],'name':meta['name'],'status':'queued','progress':0,
                   'message':'Waiting for analysis worker','created_utc':datetime.now(timezone.utc).isoformat()}
            save_json(directory/'status.json',state);save_json(directory/'config.json',request.config.model_dump())

        def update(fraction,message):
            with lock:
                state.update(progress=round(fraction,4),message=message)
                save_json(directory/'status.json',state)

        def work():
            try:
                if cancel.is_set():raise InterruptedError('Analysis cancelled')
                state['status']='running';update(0,'Starting analysis')
                output=run_analysis(meta['path'],directory,request.config,update,cancel.is_set)
                if cancel.is_set():raise InterruptedError('Analysis cancelled')
                state.update(status='completed',summary=output['summary']);update(1,'Ready for review')
            except InterruptedError:
                state['status']='cancelled';update(state['progress'],'Analysis cancelled')
            except Exception as exc:
                state['status']='failed';update(state['progress'],f'{type(exc).__name__}: {exc}')
        futures[key]=executor.submit(work)
        return state

    @app.get('/api/jobs/{job_id}')
    def get_job(job_id:str):return status(job_id)

    @app.post('/api/jobs/{job_id}/cancel')
    def cancel_job(job_id:str):
        saved=status(job_id)
        if saved['status'] not in ('queued','running'):raise HTTPException(409,'This analysis is no longer running')
        event=cancellations.get(job_id)
        if event:event.set()
        return {'message':'Cancellation requested'}

    @app.get('/api/jobs/{job_id}/result')
    def get_result(job_id:str):return result(job_id)

    @app.put('/api/jobs/{job_id}/events/{event_id}/review')
    def review(job_id:str,event_id:str,request:ReviewRequest):
        with lock:
            output=result(job_id)
            event=next((e for e in output['events'] if e['id']==event_id),None)
            if event is None:raise HTTPException(404,'Event not found')
            event['review']={**request.model_dump(),'reviewed_utc':datetime.now(timezone.utc).isoformat()}
            save_json(jobs/job_id/'result.json',output)
        return event

    @app.get('/api/jobs/{job_id}/export/{filename}')
    def export(job_id:str,filename:str):
        status(job_id)
        allowed={'result.json','manifest.json','tracks.csv','annotated.avi'}
        if filename not in allowed:raise HTTPException(404,'Export not found')
        if status(job_id)['status']!='completed':raise HTTPException(409,'Analysis is not ready')
        return FileResponse(jobs/job_id/filename,filename=f'pitchguard-{job_id[:8]}-{filename}')

    @app.delete('/api/jobs/{job_id}',status_code=204)
    def delete_job(job_id:str):
        with lock:
            saved=status(job_id)
            if saved['status'] in ('queued','running'):raise HTTPException(409,'Cancel and wait for analysis to stop before deleting')
            shutil.rmtree(jobs/job_id)

    @app.delete('/api/uploads/{upload_id}',status_code=204)
    def delete_upload(upload_id:str):
        with lock:
            metadata(upload_id)
            if any(json.loads(p.read_text())['upload_id']==upload_id for p in jobs.glob('*/status.json')):
                raise HTTPException(409,'Delete associated analyses first')
            # Example files are never deleted; only the task-owned record.
            shutil.rmtree(uploads/upload_id)

    app.mount('/',StaticFiles(directory=ROOT/'web',html=True),name='web')
    return app


app=create_app()
