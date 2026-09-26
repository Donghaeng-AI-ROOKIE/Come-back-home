"""Prepared K uses the tested explicit baseline; missing preparation stays visible."""
import copy
import pytest
from app.phase0 import person_preparation as prep
from app.phase2 import pipeline
from tests.test_person_evidence_projection import sample


def ready(sample):
    p=sample[0].model_copy(deep=True)
    key=prep.fingerprint(p)
    p.initial_preparation_status={'state':'ready','fingerprint':key}
    p.prepared_initial={'fingerprint':key,'core':copy.deepcopy(sample[-2]),
                        'scope':copy.deepcopy(sample[-1])}
    return p


def test_prepared_person_skips_sar_and_matches_explicit_baseline(sample,monkeypatch):
    p=ready(sample);report=sample[1]
    monkeypatch.setattr(pipeline.exaone,'generate_prior',lambda *a:pytest.fail('SAR must not run for a ready K preparation'))
    baseline=pipeline.exaone._default_prior(p,report)
    baseline=baseline.model_copy(update={'source':'profile_baseline','strategy_before_behavior':dict(baseline.strategy_probs)})
    expected=prep.apply_prepared(p,report,baseline,baseline,[])
    actual=pipeline._initial_prior(p,report,[])
    assert actual.source=='prepared_person'
    assert actual.initial_interpretation['SAR_called_during_prediction'] is False
    assert actual.initial_interpretation['sar_source'] is None
    for field in ('strategy_probs','attraction_weights','radius_lognormal','persona_adjustments'):
        assert getattr(actual,field)==getattr(expected,field)
    assert sum(actual.strategy_probs.values())==pytest.approx(1)


@pytest.mark.parametrize('state',['no_profile','queued','stale','invalid'])
def test_unavailable_preparation_uses_legacy_path_once(sample,monkeypatch,state):
    p=ready(sample);report=sample[1];calls=[]
    if state=='no_profile':p=None
    elif state=='queued':p.initial_preparation_status['state']='queued'
    elif state=='stale':p.age+=1
    else:p.prepared_initial['core']={}
    expected_source=sample[2].source
    def sar(*a):calls.append(a);return sample[2].model_copy(deep=True)
    monkeypatch.setattr(pipeline.exaone,'generate_prior',sar)
    result=pipeline._initial_prior(p,report,[])
    assert len(calls)==1
    assert result.source==expected_source
    assert result.initial_interpretation['initial_prior_path']=='legacy_SAR_fallback'
    assert result.initial_interpretation['status']!='applied'


def test_current_incident_link_is_applied_without_sar(sample,monkeypatch):
    p=ready(sample)
    monkeypatch.setattr(pipeline.exaone,'generate_prior',lambda *a:pytest.fail('SAR unexpected'))
    result=pipeline._initial_prior(p,sample[1],[{'place':'공원','relation':'stated_destination','quote':'오늘 공원에 간다고'}])
    assert result.initial_interpretation['status']=='applied'
    assert result.initial_interpretation['semantic_contract']['goals']['공원']['value']=='current_statement'
    assert result.initial_interpretation['situation_links'][0]['place']=='공원'
