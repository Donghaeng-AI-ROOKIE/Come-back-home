from copy import deepcopy
import pytest
from app.phase0 import interview
from app.phase0.slots import slot_by_key
from app.schemas.persona import InterviewSession,PersonaType
from app.geo.geocode import GeoResult,to_attraction_points
from app.schemas.common import GeoPoint

ANSWER='대화동의 느티공원과 해든상가, 솔빛쉼터를 함께 가요.'


def apply(session,points,answer=ANSWER):
    interview._apply_extraction(session,slot_by_key('routine_destinations'),
        {'answer_kind':'informative','attraction_points':deepcopy(points)},utterance=answer)


def test_later_model_type_survives_duplicate_merge_and_geocoding():
    labels=['느티공원','해든상가','솔빛쉼터']
    types=['공원','상가','쉼터']
    s=InterviewSession(id='type-merge',guardian_name='합성',persona_type=PersonaType.dementia)
    first=[{'label':x,'area_text':'대화동','evidence':'mention_only','quote':ANSWER} for x in labels]
    apply(s,first)
    assert all(not a.get('place_type') for a in s.draft_attractions)
    apply(s,[dict(a,place_type=t,evidence='caregiver_report') for a,t in zip(first,types)])
    assert len(s.draft_attractions)==3
    assert [a['place_type'] for a in s.draft_attractions]==types
    class Geo:
        def locate(self,query,anchor=None):return GeoResult(GeoPoint(lat=37.665,lng=126.748),'poi','synthetic_fixture')
    points,unresolved=to_attraction_points(s.draft_attractions,Geo())
    assert not unresolved and [p.place_type for p in points]==types
    assert [a['place_type'] for a in s.extraction_audit if a['event']=='place_type_backfilled']==types


@pytest.mark.parametrize('incoming',[None,'','  ',42,{},[]])
def test_no_type_is_invented_from_name(incoming):
    s=InterviewSession(id='type-empty',guardian_name='합성',persona_type=PersonaType.dementia,
        draft_attractions=[{'label':'느티공원','area_text':'대화동'}])
    apply(s,[{'label':'느티공원','place_type':incoming,'quote':ANSWER}])
    assert not s.draft_attractions[0].get('place_type')


def test_existing_type_and_unmentioned_place_are_not_overwritten():
    s=InterviewSession(id='type-existing',guardian_name='합성',persona_type=PersonaType.dementia,
        draft_attractions=[{'label':'느티공원','place_type':'park','area_text':'대화동'},
                           {'label':'다른장소','area_text':'대화동'}])
    apply(s,[{'label':'느티공원','place_type':'market','quote':ANSWER},
             {'label':'다른장소','place_type':'market','quote':ANSWER}])
    assert s.draft_attractions[0]['place_type']=='park'
    assert not s.draft_attractions[1].get('place_type')
