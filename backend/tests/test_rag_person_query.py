from app.llm.exaone import _build_rag_query
from app.schemas.persona import Persona, PersonaType, AttractionPoint
from app.schemas.common import GeoPoint


def person():
 return Persona(id='rag-query',name='이름은 검색하지 않음',age=80,type=PersonaType.dementia,home=GeoPoint(lat=37.6,lng=127.0),attraction_points=[AttractionPoint(label='등록 후보',location=GeoPoint(lat=37.6,lng=127.0))])


def test_later_lost_behavior_note_is_not_silently_omitted():
 p=person();p.behavior_notes=['외출 목적 미확인','경로 지식 미확인','오래 걸을 수 있음','길을 잃은 두 번 모두 벤치에서 가족을 기다렸음']
 q=_build_rag_query(p)
 assert all(n in q for n in p.behavior_notes)
 assert '자주 가던 장소' not in q and '방문·의도 확인과 별개' in q


def test_non_axis_original_quotes_reach_retrieval_once():
 p=person();p.onboarding_quotes={'lost_behavior':['낯선 길에서는 가게에 들어가 도움을 청했어요.'],'identity':['개인 신원'],'home':['상세 주소']};p.axis_quotes={'lost_behavior':['낯선 길에서는 가게에 들어가 도움을 청했어요.']};p.behavior_notes=['낯선 길에서는 가게에 들어가 도움을 청했어요.']
 q=_build_rag_query(p)
 assert q.count('낯선 길에서는 가게에 들어가 도움을 청했어요.')==1
 assert '개인 신원' not in q and '상세 주소' not in q and p.name not in q


def test_original_correction_is_not_replaced_by_extracted_note():
 p=person();p.onboarding_quotes={'routine_destinations':['지난달과 달리 이번 주는 공원으로 가세요.']};p.behavior_notes=['과거에는 시장 방문']
 q=_build_rag_query(p)
 assert '지난달과 달리 이번 주는 공원으로 가세요.' in q and '과거에는 시장 방문' in q
