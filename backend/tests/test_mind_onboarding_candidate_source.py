"""Real storage/source boundary with synthetic answers; no live quality claim."""
import json

from app import storage
from app.geo.geocode import GeoResult
from app.llm import mind_policy
from app.phase0 import interview, person_preparation
from app.phase0.slots import SLOTS
from app.schemas.common import GeoPoint
from app.schemas.persona import InterviewSession, Persona, PersonaType
from experiments.mind_contract_ab_20261007 import contract_d8, onboarding_fixture as case


def test_real_finalize_keeps_question_context_and_originals_through_reload(monkeypatch):
    class Geo:
        def locate(self, query, anchor=None):
            return GeoResult(GeoPoint(lat=37.661,lng=126.746),precision='dong',source='synthetic_fixture')
    queued=[]
    monkeypatch.setattr(person_preparation,'enqueue',lambda pid:queued.append(pid))
    assert set(case.ANSWERS)=={s.key for s in SLOTS}
    turns=[{'slot':s.key,'question':s.question,'answer':case.ANSWERS[s.key]} for s in SLOTS]
    session=InterviewSession(id='synthetic-storage-handoff',guardian_name='합성 보호자',
        persona_type=PersonaType.dementia,draft_fields={'name':case.NAME,'age':case.AGE,'home':case.HOME},
        slot_turns=turns,draft_behaviors=['모델 미검증 요약: 아프지 않아도 계속 앉아 있음'])
    persona=interview.finalize_persona(session,geocoder=Geo())
    reloaded=Persona.model_validate_json(storage.personas.get(persona.id).model_dump_json())
    assert queued==[persona.id]
    assert reloaded.onboarding_turns==turns
    source=mind_policy.source(reloaded)
    assert len(source['notes'])==len(turns)
    assert all(n['provenance']=='guardian_original' for n in source['notes'])
    all_text='\n'.join(n['text'] for n in source['notes'])
    assert '모델 미검증 요약' not in all_text
    for turn in turns:
        assert f"질문: {turn['question']}\n답변: {turn['answer']}" in all_text
    body=contract_d8.request(source,'test-model')
    payload=json.loads(body['messages'][-1]['content'])
    assert payload['original_notes']==source['notes']
    assert len(payload['answers_by_turn'])==len(turns)
    assert len(json.dumps(body,ensure_ascii=False).encode())<=40000
