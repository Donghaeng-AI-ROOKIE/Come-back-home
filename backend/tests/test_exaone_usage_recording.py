"""Self-hosted inference usage must be recorded without logging source or keys."""
import json
import pytest
from app.config import settings
from app.llm.exaone import ExaoneClient
from app.llm import usage_ledger

@pytest.mark.parametrize('fail',[False,True])
def test_self_hosted_usage_success_and_failure(tmp_path,monkeypatch,fail):
    monkeypatch.setattr(settings,'research_usage_ledger_path',str(tmp_path/'usage.jsonl'))
    monkeypatch.setattr(settings,'exaone_base_url','http://localhost:8000/v1')
    monkeypatch.setattr(settings,'exaone_api_key','synthetic-secret')
    monkeypatch.setattr(settings,'exaone_model','exaone-sar')
    class Reply:
        status=200
        headers={}
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self):return json.dumps({'choices':[{'message':{'content':'ok'}}],
            'usage':{'prompt_tokens':4,'completion_tokens':1,'total_tokens':5}}).encode()
    def invoke(*a,**kw):
        if fail:raise TimeoutError('sensitive diagnostic')
        return Reply()
    monkeypatch.setattr(usage_ledger,'urlopen',invoke)
    c=ExaoneClient()
    if fail:
        with pytest.raises(TimeoutError):c.chat([{'role':'user','content':'private-source'}])
    else:assert c.chat([{'role':'user','content':'private-source'}])=='ok'
    raw=(tmp_path/'usage.jsonl').read_text()
    assert all(x not in raw for x in ['synthetic-secret','private-source','sensitive diagnostic'])
    events=[json.loads(x) for x in raw.splitlines()]
    assert [e['event_type'] for e in events]==['api_attempt_started','api_attempt_finished']
    assert events[-1]['provider']=='LG EXAONE (self-hosted)'
    assert events[-1].get('error_type')==('TimeoutError' if fail else None)
    assert events[-1]['billing_basis']=='self_hosted_gpu'
    assert events[-1]['actual_cost'] is None
