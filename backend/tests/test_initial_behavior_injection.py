"""Source preservation and privacy across onboarding and prediction boundaries."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from app import storage
from app.config import settings
from app.llm import initial_behavior as ib
from app.llm.exaone import ExaoneClient
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona, PersonaType, AttractionPoint, InterviewSession
from app.schemas.report import MissingReport

def inputs():
 p=Persona(id='initial-person-test',type='dementia',name='개인정보',age=80,home=GeoPoint(lat=37.6,lng=127.),
  attraction_points=[AttractionPoint(label='옛 직장',location=GeoPoint(lat=37.61,lng=127.01)),AttractionPoint(label='공원',location=GeoPoint(lat=37.62,lng=127.02))],
  onboarding_quotes={'routine_destinations':['출근해야 한다고 하지만 여기로 이사 온 지 일주일이에요.'],'lost_behavior':['길을 못 찾았을 때는 앉아서 기다리셨어요.'],'capacity':['5분 걸으면 다리가 아파 쉬어야 해요.']},
  behavior_tendency='stay',axis_scores={'mobility_transport_capacity':.5})
 r=MissingReport(id='initial-report',persona_id=p.id,missing_type=PersonaType.dementia,lkp=p.home,lkp_time=datetime.now()-timedelta(hours=1),situation='외출 준비 중 문을 나섬')
 default=ExaoneClient()._default_prior(p,r)
 payload=ib.build_payload(p,r,[{'source':'논문A','kind':'paper','text':'조건부 연구 발췌'}],default)
 return p,r,default,payload


def test_whole_onboarding_survives():
 p,r,sar,payload=inputs()
 assert len(payload['notes'])==3 and payload['incident']['context']==r.situation
 assert all(n['text'] in sum(p.onboarding_quotes.values(),[]) for n in payload['notes'])
 assert '개인정보' not in json.dumps(payload,ensure_ascii=False)
 assert 'location' not in payload['places'][0]


def test_finalize_preserves_non_axis_quotes(monkeypatch):
 from app.phase0 import interview
 p,r,sar,payload=inputs()
 session=InterviewSession(id='initial-session',guardian_name='보호자',persona_type=PersonaType.dementia,draft_fields={'name':'대상','age':80,'home':'집'},slot_quotes={'routine_destinations':['어릴 때 다니던 길은 알아요.'],'identity':['이름 주소'],'home':['주소']})
 monkeypatch.setattr(interview,'locate_home',lambda *a:SimpleNamespace(point=p.home))
 monkeypatch.setattr(interview,'to_attraction_points',lambda *a,**kw:([],[]))
 monkeypatch.setattr(settings,'axis_scoring_enabled',False)
 assert interview.finalize_persona(session).onboarding_quotes=={'routine_destinations':['어릴 때 다니던 길은 알아요.']}


def test_raw_quotes_hidden_in_list_and_detail():
 from fastapi.testclient import TestClient
 from app.main import app
 p,*_=inputs();p.guardian_id='initial-owner';storage.personas.save(p.id,p);client=TestClient(app)
 rows=client.get('/phase0/personas',params={'guardian_id':'initial-owner'}).json()
 assert len(rows)==1
 for row in [rows[0],client.get('/phase0/personas/'+p.id).json()]:assert 'onboarding_quotes' not in row and 'onboarding_turns' not in row and 'axis_quotes' not in row and 'prepared_initial' not in row


def test_derived_qa_not_promoted_to_behavioral_evidence():
 p,r,sar,_=inputs()
 research=[{'source':'paper','kind':'paper','text':'원논문 발췌'}, {'source':'derived','kind':'qa','text':'검증되지 않은 처방'}]
 payload=ib.build_payload(p,r,research,sar)
 assert [x['id'] for x in payload['research']]==['R0']
 assert len(payload['retrieval_audit'])==2
 assert '검증되지 않은 처방' not in json.dumps(payload,ensure_ascii=False)
