import pytest

from src.evaluation import compare_targets, evaluate_events, evaluate_locations, reviewer_agreement, validate_splits


def test_match_split_leakage_is_rejected():
    data={'clips':[{'id':'a','match_id':'same','split':'train','permission_note':'User supplied'},
                   {'id':'b','match_id':'same','split':'test','permission_note':'User supplied'}]}
    with pytest.raises(ValueError,match='leakage'):validate_splits(data)


def test_location_error_and_identity_switches_include_misses():
    result={'timeline':[]}
    truth={'frames':[]}
    for index,track_id in enumerate([4,9]):
        result['timeline'].append({'frame':index,'shape':{'valid':True},'observations':[
            {'team':'own','xy':[10.1,20],'track_id':track_id}]})
        truth['frames'].append({'frame':index,'players':[{'team':'own','xy':[10,20],'identity':'alice'},
                                                       {'team':'opponent','xy':[80,30],'identity':'bob'}]})
    metrics=evaluate_locations(result,truth)
    assert metrics['precision']==1 and metrics['recall']==.5
    assert metrics['identity_switches']==1
    assert metrics['mean_position_error_m']==pytest.approx(.1)
    assert metrics['calibration_error_px'] is None


def test_missing_label_sample_cannot_silently_improve_scores():
    with pytest.raises(ValueError,match='not an analysis sample'):
        evaluate_locations({'timeline':[]},{'frames':[{'frame':10,'players':[]}]})


def test_event_evaluation_requires_review_and_counts_false_alarms():
    result={'events':[{'kind':'unit_gap','start_s':2,'end_s':4,'detected_s':2.8},
                      {'kind':'role_drift','start_s':6,'end_s':8,'detected_s':6.8}]}
    labels={'events':[{'kind':'unit_gap','start_s':2,'end_s':4}],
            'events_reviewed':True,'reviewed_intervals':[[0,10]]}
    report=evaluate_events(result,labels)
    assert report['precision']==.5 and report['recall']==1
    assert report['false_positives']==1 and report['mean_onset_latency_s']==pytest.approx(.8)
    with pytest.raises(ValueError,match='coach-reviewed'):evaluate_events(result,{})


def test_targets_and_reviewer_disagreement():
    assert not compare_targets({'recall':.8},{'recall':{'min':.9}})['passed']
    assert not compare_targets({}, {'mean_position_error_m':{'max':1}})['passed']
    report=reviewer_agreement([{'item_id':'1','judgement':'issue'}],[{'item_id':'1','judgement':'intended'}])
    assert report['raw_agreement']==0 and report['disagreements']==['1']


def test_review_boundary_does_not_hide_a_false_alarm():
    result={'events':[{'kind':'unit_gap','start_s':2,'end_s':8,'detected_s':2.8}]}
    labels={'events_reviewed':True,'reviewed_intervals':[[0,3]],'events':[]}
    metrics=evaluate_events(result,labels)
    assert metrics['false_positives']==1 and metrics['recall'] is None
    assert metrics['false_alarms_per_reviewed_minute']==20
    labels['events']=[{'kind':'unit_gap','start_s':2,'end_s':3}]
    matched=evaluate_events(result,labels)
    assert matched['true_positives']==1 and matched['recall']==1
