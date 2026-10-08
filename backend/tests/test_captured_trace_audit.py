from types import SimpleNamespace
from experiments.mind_contract_ab_20261007.captured_trace_audit import SourceTraceAudit


def point(t, mode, rule='r', distance=0, continuous=0, lat=37.66):
    return dict(minute=t,mode=mode,rule_id=rule,distance_m=distance,continuous_walk=continuous,lat=lat,lng=126.75)


def audit(scene='rest_cycle'):
    loc={'lat':37.66,'lng':126.75}
    return SourceTraceAudit(scene,[SimpleNamespace(id='r')],loc,loc,1)


def test_source_threshold_and_duration_are_checked_independently():
    a=audit()
    a.observe(0,point(1,'rest'))
    a.observe(0,point(2,'walk',rule=None,distance=48,continuous=1))
    result=a.result(2)
    assert result['violation_counts']=={'rest_before_either_threshold':1,'personal_rest_duration':1}


def test_complete_five_minute_rest_and_horizon_coverage():
    a=audit()
    a.observe(0,point(6,'walk',rule=None,distance=280,continuous=6))
    a.observe(0,point(11,'rest',distance=280))
    a.observe(0,point(12,'walk',rule=None,distance=328,continuous=1))
    assert a.result(12)['checks_passed']
    assert not a.result(13)['checks_passed']


def test_entire_wait_segment_not_only_midpoint_must_be_in_window():
    a=audit('wait_release')
    a.observe(0,point(39,'walk',rule=None))
    a.observe(0,point(41,'wait'))
    assert a.result(41)['violation_counts']['personal_wait_outside_window']==1


def test_baseline_wait_not_misattributed_to_personal_rule():
    a=audit('wait_release')
    a.observe(0,point(100,'wait',rule=None))
    result=a.result(100)
    assert result['total_personal_wait_minutes']==0
    assert result['total_baseline_wait_minutes']==100
    assert result['violation_count']==0
    assert not result['checks_passed'] # no personal behavior coverage


def test_named_scope_and_observed_noise_checked_separately():
    a=audit('place_noise')
    a.observe(0,point(25,'walk',rule=None,lat=37.67))
    a.observe(0,point(26,'avoid',lat=37.67))
    result=a.result(26)
    assert result['violation_counts']=={'avoid_outside_noise_window':1,'avoid_outside_named_scope':1}


def test_missing_rest_command_cannot_pass_by_emitting_no_rest_events():
    a=audit()
    a.observe(0,point(7,'walk',rule=None,distance=336,continuous=7))
    assert a.result(7)['violation_counts']['walking_beyond_first_rest_threshold']==1


def test_missing_wait_command_detected_but_existing_rest_can_finish():
    a=audit('wait_release')
    a.observe(0,point(40,'walk',rule=None))
    a.observe(0,point(41,'walk',rule=None,distance=48,continuous=1))
    a.observe(0,point(42,'rest',distance=48))
    assert a.result(42)['violation_counts']['movement_during_required_wait']==1
