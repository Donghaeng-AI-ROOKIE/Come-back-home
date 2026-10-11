"""The statistical prior remains separate from personal K adjustments."""
from app.schemas.prediction import PriorParams,LognormalParams
from app.phase2.continuous_prediction import statistical_prior
from app.phase2 import pipeline


def prior(mu=1):
    return PriorParams(strategy_probs={'random_walk':1},attraction_weights={},radius_lognormal=LognormalParams(mu=mu,sigma=1))


def test_statistical_snapshot_removes_k_numbers_and_persona_projection():
    sar=prior();personal=prior(-1);personal.strategy_probs={'staying_put':1}
    personal.persona_adjustments={'persona_id':'p','axis_scores':{'x':1}}
    personal.initial_interpretation={'status':'applied'}
    personal.sar_numeric_baseline=sar.model_dump(mode='json',exclude={'reasoning','sar_numeric_baseline','initial_interpretation','persona_adjustments'})
    got,source=statistical_prior(personal)
    assert got.strategy_probs==sar.strategy_probs and got.radius_lognormal==sar.radius_lognormal
    assert not got.persona_adjustments and not got.initial_interpretation
    assert source=='original_sar_numeric_snapshot'
    assert personal.radius_lognormal.mu==-1 and personal.strategy_probs=={'staying_put':1}


def test_legacy_prepared_prior_missing_snapshot_is_disclosed():
    personal=prior();personal.initial_interpretation={'status':'applied'}
    got,source=statistical_prior(personal)
    assert got is personal and source=='legacy_prepared_numbers_raw_sar_snapshot_missing'


def test_pipeline_captures_sar_before_k_compilation_without_second_sar_call(monkeypatch):
    sar=prior();sar.reasoning='PRIVATE_GUARDIAN_MARKER';calls=[]
    monkeypatch.setattr(pipeline.exaone,'generate_prior',lambda *a:calls.append(1) or sar)
    monkeypatch.setattr(pipeline.exaone,'_default_prior',lambda *a:prior())
    def compile(*a):
        changed=prior(-1);changed.initial_interpretation={'status':'applied'};return changed
    monkeypatch.setattr(pipeline,'apply_prepared',compile)
    personal=pipeline._initial_prior(None,None,[]);got,source=statistical_prior(personal)
    assert calls==[1] and personal.radius_lognormal.mu==-1
    assert got.radius_lognormal.mu==1 and source=='original_sar_numeric_snapshot'
    assert 'PRIVATE_GUARDIAN_MARKER' not in str(personal.sar_numeric_baseline)
