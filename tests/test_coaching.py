import numpy as np
import pytest

from src.coaching import EventEngine, analyse_shape
from src.formations import PROFILES, anchors, recommend
from src.schemas import AnalysisConfig
from src.vision import Observation, Tracker


def observations(points=None):
    own=anchors('4-3-3') if points is None else points
    return [Observation([0,0,10,20],[5,20],.9,team,.9,list(map(float,p)),i+offset)
            for team,points,offset in [('own',own,1),('opponent',anchors('4-3-3',-1),20)] for i,p in enumerate(points)]


def test_all_formations_have_eleven_roles_and_mirror():
    for name in PROFILES:
        a=anchors(name);b=anchors(name,-1)
        assert a.shape==(11,2)
        np.testing.assert_allclose(a[:,0]+b[:,0],105)


def test_recommendation_responds_to_objective_and_squad():
    defensive=recommend('4-4-2','protect_lead',current='4-2-3-1')
    attacking=recommend('4-4-2','chase_goal',current='4-3-3')
    assert defensive['recommended']['formation']!=attacking['recommended']['formation']
    weak=recommend('4-4-2',squad={'stamina':1,'wingers':1})
    strong=recommend('4-4-2',squad={'stamina':5,'wingers':5})
    w=next(r['score'] for r in weak['ranking'] if r['formation']=='4-3-3')
    s=next(r['score'] for r in strong['ranking'] if r['formation']=='4-3-3')
    assert s>w
    for item in strong['ranking']:
        assert item['score']==pytest.approx(sum(item['components'].values()))
    with pytest.raises(ValueError):recommend('2-2-2')


def test_shape_removes_translation_and_excludes_goalkeeper():
    shape=analyse_shape(observations(anchors('4-3-3')+[3,2]),'4-3-3')
    assert shape['valid'] and not shape['signals']
    assert shape['metrics']['depth_m']==45
    assert shape['metrics']['mean_deviation_m']==0


def test_drift_is_track_specific_and_persistent():
    points=anchors('4-3-3');points[1,0]+=18
    shape=analyse_shape(observations(points),'4-3-3')
    engine=EventEngine(.8)
    for time in [0,.2,.4,.6]:assert not engine.update(time,shape)
    assert engine.update(.8,shape)
    drift=next(e for e in engine.events if e['kind']=='role_drift')
    assert drift['track_ids']==[2]
    assert drift['start_s']==0 and drift['detected_s']==.8
    invalid={**shape,'valid':False,'local_signals':[]}
    engine.update(1.,invalid);assert not engine.update(1.2,shape)


def test_missing_frames_do_not_sustain_alerts():
    p=anchors('4-3-3');p[1,0]+=18;s=analyse_shape(observations(p),'4-3-3')
    engine=EventEngine(.8,max_sample_gap_s=1)
    engine.update(0,s);assert not engine.update(3,s)


def test_partial_view_abstains_from_team_shape():
    obs=observations()[:5]
    state=analyse_shape(obs,'4-3-3')
    assert not state['valid'] and state.get('local_valid')
    assert not state['roles'] and not state['lanes']


def test_tracker_keeps_team_ids_and_does_not_invent_observations():
    tracker=Tracker()
    def obs(x,team):return Observation([0,0,1,1],[0,0],.9,team,1,[x,20])
    first=tracker.update([obs(20,'own'),obs(21,'opponent')],0)
    own_id=first[0].track_id;opponent_id=first[1].track_id
    second=tracker.update([obs(21.2,'opponent'),obs(20.2,'own')],.2)
    assert [o.track_id for o in second]==[opponent_id,own_id]
    assert tracker.update([],.4)==[]
    third=tracker.update([obs(20.4,'own')],.6)
    assert third[0].track_id==own_id
    fourth=tracker.update([obs(20.5,'own')],3)
    assert fourth[0].track_id!=own_id


def test_invalid_configuration_rejected():
    corners=[[110,70],[850,105],[925,550],[35,550]]
    for options in [{'sample_fps':0},{'own_colour':'#ff0000','opponent_colour':'#ff0000'},
                    {'formation':'2-2'},{'end_s':1,'start_s':2}, {'confidence':float('nan')}]:
        with pytest.raises(ValueError):AnalysisConfig(corners=corners,**options)


def test_possession_context_changes_reference_geometry():
    p=anchors('4-3-3');p[8:,0]+=8
    a=analyse_shape(observations(p),'4-3-3',possession='in')
    b=analyse_shape(observations(p),'4-3-3',possession='out')
    assert a['roles']!=b['roles']
