import copy,json
import pytest
from app.config import Settings,settings
from app.llm import mind_policy
from tests.test_walker_traces import geography,mixed_prior,walk
from tests.test_continuous_prediction import case_for,prepared


def test_candidate_cap_and_default(monkeypatch):
    monkeypatch.delenv('WALKER_TRACE_COUNT',raising=False)
    assert Settings(_env_file=None).walker_trace_count==64
    with pytest.raises(ValueError):Settings(_env_file=None,walker_trace_count=65)


def test_64_candidates_leave_forecast_and_continuation_checkpoint_identical(geography,monkeypatch):
    net,center=geography
    monkeypatch.setattr(settings,'mc_num_walkers',80)
    monkeypatch.setattr(mind_policy,'RELEASE_QUALIFIED',True)
    p=prepared(center);base=case_for(p);runs={}
    for count in (0,8,64):
        monkeypatch.setattr(settings,'walker_trace_count',count)
        c=base.model_copy(deep=True)
        outputs=[walk(c,p,net,.5),walk(c,p,net,1)]
        runs[count]=(outputs,copy.deepcopy(c.continuous_state))
    for count in (8,64):
        assert runs[count][0]==runs[0][0]
        assert runs[count][1]['checkpoint']==runs[0][1]['checkpoint']
        assert runs[count][1]['key']==runs[0][1]['key']
    tr=runs[64][1]['walker_traces']
    assert len(tr['walkers'])==64
    assert all(w['starts_at_minute']==0 and w['points'][0][2]==0 and w['points'][-1][2]==60 for w in tr['walkers'])
    assert all(len(w['points'])<=400 for w in tr['walkers'])
    assert len(json.dumps(tr).encode())<1_000_000
