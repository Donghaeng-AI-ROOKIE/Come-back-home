import json
from types import SimpleNamespace
import pytest
from experiments.mind_contract_ab_20261007 import resume_concise8 as repair, run_v2


def test_oversized_correction_is_terminal_not_retried(tmp_path, monkeypatch):
    run_v2.write(tmp_path/'manifest.json', {})
    folder=tmp_path/'P1'/'1'
    run_v2.write(folder/'first'/'response.public.json', {'content':'bad'})
    calls=[]
    def original(*args):
        calls.append(args[2][0]['job'])
        raise ValueError(repair.CAP_ERROR)
    monkeypatch.setattr(run_v2,'judge',lambda *a: ('invalid','invalid',None))
    jobs=[{'job':'x','input':{'id':'P1','personal':{}},'rep':1}]
    for _ in range(2):
        assert not repair.execute_guarded(original,'d8_dev8',tmp_path,jobs,None,None,None,32)
    assert calls==['x']
    marker=json.loads((folder/'correction_unavailable.json').read_text())
    assert marker['submitted'] is False and marker['terminal']
    assert not (folder/'fix'/'result.json').exists()


def test_terminal_failure_stays_failed_in_score(tmp_path, monkeypatch):
    run_v2.write(tmp_path/'P1'/'1'/'correction_unavailable.json', {'reason':repair.CAP_ERROR})
    row={'input_id':'P1','rep':1,'first_state':'done','first_problem':'invalid',
         'fix_state':'pending','policy':None,'complete':False,'corrected':False}
    monkeypatch.setattr(run_v2,'load_candidate',lambda x:(None,None,None))
    monkeypatch.setattr(run_v2,'summarize',lambda m,r:{'complete':all(x['complete'] for x in r)})
    monkeypatch.setattr(run_v2,'gate',lambda *a:{'advance':False})
    rows,summary,gate=repair.score_with_unavailable(lambda *a:([row],{},{}),'d8_dev8',tmp_path)
    assert summary['complete'] and summary['corrections_unavailable']==1
    assert rows[0]['policy'] is None and not rows[0]['corrected'] and not gate['advance']


def test_unexpected_failure_is_not_swallowed(tmp_path):
    run_v2.write(tmp_path/'manifest.json',{})
    def original(*args):raise ValueError('not the input cap')
    with pytest.raises(ValueError,match='not the input cap'):
        repair.execute_guarded(original,'d8_dev8',tmp_path,
          [{'job':'x','input':{'id':'P1','personal':{}},'rep':1}],None,None,None,32)
