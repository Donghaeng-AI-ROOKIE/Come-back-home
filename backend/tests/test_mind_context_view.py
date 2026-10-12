from copy import deepcopy
import pytest
from experiments.mind_grounded.context_view import presentation


def sample():
    return {'person':{'evidence_notes':[{'text':'안 기다리고 움직여요'}]},'known_places':[],
            'clock_time':'2026-09-28T19:00:00','research':[],
            'state':{'elapsed_minutes':60,'fatigue':.9,'confusion':.8,'distance_m':500,
                     'target_reached':True,'last_rest_end_minutes':59,
                     'current_action':'seek','target_label':'A',
                     'recent_events':[{'kind':'orientation_lost','elapsed_minutes':59}]},
            'environment':{'observed_signals':{'market':{'noisy':None,'crowded':False}}}}


def test_event_time_is_one_minute_ago_not_fifty_nine():
    c=sample();original=deepcopy(c);v=presentation(c)
    assert v['simulated_events_not_real_patient_observations'][0]['minutes_before_current_decision']==1
    assert v['current_decision']['minutes_since_last_rest_completed']==1
    assert v['current_decision']['fatigue']==.9
    assert v['current_decision']['target_already_reached'] is True
    assert v['guardian_and_person']==c['person'] and c==original
    assert v['environment_facts_supplied_by_simulator']['observed_signals']['market']=={'noisy':None,'crowded':False}


def test_future_events_are_rejected_without_inventing_a_current_state():
    c=sample();c['state']['recent_events'][0]['elapsed_minutes']=61
    with pytest.raises(ValueError):presentation(c)
