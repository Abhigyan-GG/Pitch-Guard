import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from src.evaluation import evaluate_events
from src.pipeline import ROOT
from src.server import create_app


@pytest.fixture
def review_app(tmp_path):
    job='a'*32;directory=tmp_path/'jobs'/job;directory.mkdir(parents=True)
    machine={'summary':{'start_s':0,'end_s':10},'manifest':{'input_sha256':'source-checksum'},
             'events':[{'kind':'unit_gap','start_s':4,'end_s':5,'detected_s':4.8}],'timeline':[]}
    (directory/'result.json').write_text(json.dumps(machine))
    (directory/'status.json').write_text(json.dumps({'id':job,'upload_id':'b'*32,'status':'completed'}))
    with TestClient(create_app(tmp_path)) as client:
        yield client,job,directory,machine


def body(**changes):
    return {'expected_revision':0,'clip_id':'match-test','reviewer':'Fixture reviewer','reviewer_role':'coach',
            'reviewed_periods':[{'start_s':0,'end_s':10}],
            'manual_events':[{'id':'manual-one','kind':'role_drift','start_s':2,'end_s':3,'notes':'A missed candidate','judgement':'issue'}],
            'attested':True,**changes}


def test_human_labels_persist_without_copying_or_changing_predictions(review_app):
    client,job,directory,machine=review_app
    assert client.get(f'/api/jobs/{job}/annotations').json()['revision']==0
    assert client.get(f'/api/jobs/{job}/export/human-labels.json').status_code==404
    response=client.put(f'/api/jobs/{job}/annotations',json=body())
    assert response.status_code==200
    assert response.json()['revision']==1
    assert client.get(f'/api/jobs/{job}/annotations').json()['manual_events'][0]['notes']=='A missed candidate'
    labels=client.get(f'/api/jobs/{job}/export/human-labels.json').json()
    assert labels['events_reviewed'] and labels['input_sha256']=='source-checksum'
    assert [e['kind'] for e in labels['events']]==['role_drift']
    assert labels['frames']==[]
    assert json.loads((directory/'result.json').read_text())==machine


def test_negative_review_period_is_useful_without_inventing_positive_labels(review_app):
    client,job,_,machine=review_app
    assert client.put(f'/api/jobs/{job}/annotations',json=body(manual_events=[])).status_code==200
    labels=client.get(f'/api/jobs/{job}/export/human-labels.json').json()
    report=evaluate_events(machine,labels)
    assert report['false_positives']==1 and report['false_negatives']==0
    assert report['recall'] is None and report['precision']==0
    assert report['false_alarms_per_reviewed_minute']==6


def test_draft_or_noncoach_review_never_claims_coach_verified_labels(review_app):
    client,job,_,_=review_app
    draft=body(attested=False,reviewer='')
    assert client.put(f'/api/jobs/{job}/annotations',json=draft).status_code==200
    assert not client.get(f'/api/jobs/{job}/export/human-labels.json').json()['events_reviewed']
    assert client.put(f'/api/jobs/{job}/annotations',json=body(expected_revision=1,reviewer_role='player')).status_code==200
    assert not client.get(f'/api/jobs/{job}/export/human-labels.json').json()['events_reviewed']


@pytest.mark.parametrize('change',[
    {'reviewer':''},
    {'reviewed_periods':[]},
    {'reviewed_periods':[{'start_s':0,'end_s':5},{'start_s':4,'end_s':9}]},
    {'reviewed_periods':[{'start_s':0,'end_s':1}]},
    {'reviewed_periods':[{'start_s':0,'end_s':11}]},
    {'manual_events':[{'id':'unclear','kind':'role_drift','start_s':2,'end_s':3,'judgement':'uncertain'}]},
])
def test_invalid_review_cannot_establish_truth(review_app,change):
    client,job,_,_=review_app
    response=client.put(f'/api/jobs/{job}/annotations',json=body(**change))
    assert response.status_code==422,response.text
    assert client.get(f'/api/jobs/{job}/annotations').json()['revision']==0


def test_stale_save_does_not_overwrite_another_reviewer(review_app):
    client,job,_,_=review_app
    assert client.put(f'/api/jobs/{job}/annotations',json=body()).status_code==200
    assert client.put(f'/api/jobs/{job}/annotations',json=body(reviewer='Other tab')).status_code==409
    assert client.get(f'/api/jobs/{job}/annotations').json()['reviewer']=='Fixture reviewer'


def test_event_only_labels_can_be_evaluated_without_fabricated_player_positions(tmp_path):
    files={
        'result':{'manifest':{'input_sha256':'checksum'},'events':[],'timeline':[]},
        'labels':{'clip_id':'test','input_sha256':'checksum','frames':[],'events_reviewed':True,'reviewed_intervals':[[0,10]],'events':[]},
        'manifest':{'clips':[{'id':'test','match_id':'unique','split':'test','permission_note':'Fixture data'}]},
    }
    for name,data in files.items():(tmp_path/f'{name}.json').write_text(json.dumps(data))
    report=tmp_path/'report.json'
    command=[sys.executable,'-m','src.evaluation','--result',str(tmp_path/'result.json'),'--labels',str(tmp_path/'labels.json'),
             '--manifest',str(tmp_path/'manifest.json'),'--clip-id','test','--output',str(report)]
    completed=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr
    output=json.loads(report.read_text())
    assert output['locations'] is None and output['events']['recall'] is None
