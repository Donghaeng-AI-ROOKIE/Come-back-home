import json
from copy import deepcopy
import pytest
from app.geo.geocode import ChainGeocoder, GeoResult, to_attraction_points
from app.geo.named_place_cache import NamedPlaceCache
from app.schemas.common import GeoPoint
from app.schemas.persona import InterviewSession, PersonaType
from app.phase0 import interview
from app.llm import mind_policy_guarded_core as guarded

HOME = GeoPoint(lat=37.556, lng=126.910)


def cache(tmp_path):
    path=tmp_path/'bundles';path.mkdir()
    data={'schema_version':1,'source_sha256':'a'*64,
          'bbox_south_west_north_east':[37.49,126.83,37.62,126.99],
          'places':[{'name':'망원시장','lat':37.55717,'lng':126.90582,
                     'osm_type':'node','osm_id':4196342490,'precision':'poi'}]}
    (path/'named-places.json').write_text(json.dumps(data))
    return NamedPlaceCache(tmp_path)


class EmptyProvider:
    def keyword_candidates(self,*args):return []
    def locate(self,*args,**kwargs):return None


class ExactChooser:
    def pick(self,draft,results,**kwargs):
        matches=[i for i,r in enumerate(results) if r.matched==draft['label']]
        return matches[0] if len(matches)==1 else None
    def landmark(self,draft):return None


def test_named_destination_survives_empty_provider_and_uses_verified_cache(tmp_path):
    chain=ChainGeocoder(EmptyProvider(),cache(tmp_path))
    points,unresolved=to_attraction_points([{'label':'망원시장','area_text':'서울 마포구 망원동',
        'name_kind':'proper','place_type':'market','evidence':'caregiver_report','origin_slot':'routine_destinations'}],
        chain,anchor=HOME,chooser=ExactChooser())
    assert not unresolved
    assert len(points)==1 and points[0].label=='망원시장'
    assert points[0].location.lng==126.90582 and points[0].place_type=='market'
    assert points[0].origin_slot=='routine_destinations'


def test_cache_does_not_supply_home_unanchored_or_wrong_region(tmp_path):
    geo=cache(tmp_path)
    assert geo.locate('망원시장',HOME) is None
    assert geo.keyword_candidates('망원시장')==[]
    assert geo.keyword_candidates('망원시장',GeoPoint(lat=35,lng=129))==[]
    assert geo.keyword_candidates('망원시장약국',HOME)==[]


def session():
    return InterviewSession(id='goal-preserve',guardian_name='합성',persona_type=PersonaType.dementia,
        draft_fields={'name':'합성인물','age':'78','home':'합성 기준점'},
        home_geo={'query':'합성 기준점','lat':HOME.lat,'lng':HOME.lng},
        draft_attractions=[{'label':'망원시장','area_text':'망원동','name_kind':'proper'}],
        awaiting_confirmation=True)


def test_unresolved_destination_cannot_be_silently_confirmed():
    s=session()
    with pytest.raises(interview.UnresolvedAttractionError):
        interview.finalize_persona(s,geocoder=EmptyProvider())
    assert s.persona_id is None and not s.done
    assert s.draft_attractions[0]['label']=='망원시장'


def test_failed_destination_keeps_home_and_confirmation_open(monkeypatch):
    s=session();before=deepcopy(s.home_geo)
    monkeypatch.setattr(interview,'_GEO',EmptyProvider())
    monkeypatch.setattr(interview.midm,'extract_correction',lambda *a:{'intent':'confirm','fields':{},'place_ops':[]})
    result=interview._handle_confirmation(s,'네')
    assert result.awaiting_confirmation and not result.done
    assert result.home_geo==before and result.draft_fields['home']=='합성 기준점'
    assert '망원시장' in result.messages[-1]['text'] and '등록을 완료하지 않았어요' in result.messages[-1]['text']


def test_repair_reports_each_invalid_rule_without_changing_source_or_draft():
    source={'notes':[{'id':'N0','text':'길을 잃으면 등록시장으로 향한다.'},
                     {'id':'N1','text':'30분 걸으면 10분 쉰다.'}],
            'places':[{'label':'등록시장'}],'prepared_initial':{}}
    rules=[{'action':'seek','goal_place':'','applies_only_at':[],'condition':'lost_awareness','hold_minutes':0,'note_ids':['N0']},
           {'action':'walk','goal_place':'','applies_only_at':[],'condition':'True','hold_minutes':0,'note_ids':['N1']}]
    draft={'source_assessment':'길 잃음 시 이동, 보행 한계 시 휴식','rules':rules,'non_action_note_ids':[]}
    original=deepcopy(draft)
    payload=json.loads(guarded.repair_request(source,'test',json.dumps(draft),'first failure')['messages'][1]['content'])
    assert [e['rule_index'] for e in payload['rule_validation_errors']]==[0,1]
    assert 'seek_without_registered_goal' in payload['rule_validation_errors'][0]['error']
    assert 'specific trigger' in payload['rule_validation_errors'][1]['error']
    assert draft==original and payload['original_notes']==source['notes']
    with pytest.raises(ValueError):guarded.compile(draft,source)
    fixed=deepcopy(draft);fixed['rules'][0]['goal_place']='등록시장'
    fixed['rules'][1].update(action='rest',condition='is_walking and continuous_walk_minutes >= 30',hold_minutes=10)
    compiled=guarded.compile(fixed,source)
    assert [r.action for r in compiled.rules]==['seek','rest']
    assert compiled.rules[1].hold_minutes==10


def test_empty_primary_uses_nominatim_candidates_without_network(monkeypatch):
    import io
    from app.geo.geocode import NominatimGeocoder
    import urllib.request
    data=[{'lat':'37.55717','lon':'126.90582','display_name':'망원시장, 마포구','osm_type':'node','osm_id':4196342490}]
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**k:io.BytesIO(json.dumps(data).encode()))
    hits=ChainGeocoder(EmptyProvider(),NominatimGeocoder()).keyword_candidates('망원시장',HOME)
    assert len(hits)==1 and hits[0].source=='nominatim'
    assert hits[0].detail['osm_id']==4196342490


def test_without_cache_or_providers_factory_preserves_gazetteer(monkeypatch,tmp_path):
    from app.geo.geocode import get_geocoder, GazetteerGeocoder
    from app.config import settings
    monkeypatch.setattr(settings,'roadnet_cache_dir',str(tmp_path))
    monkeypatch.setattr(settings,'kakao_rest_key','')
    assert isinstance(get_geocoder(),GazetteerGeocoder)


def test_valid_draft_with_unrepresented_notes_gets_source_review(monkeypatch):
    from app.phase0 import mind_preparation as mp
    source={'notes':[{'id':'N0','text':'30분 걸으면 10분 쉰다.'},
                     {'id':'N1','text':'시장에 사람이 많으면 피한다.'}], 'places':[], 'prepared_initial':{}}
    draft={'source_assessment':'보행 한계 후 휴식', 'rules':[{'action':'rest','goal_place':'','applies_only_at':[],
           'condition':'is_walking and continuous_walk_minutes >= 30','hold_minutes':10,'note_ids':['N0']}],
           'non_action_note_ids':['N1']}
    revised=deepcopy(draft);revised['rules'].append({'action':'avoid_market','goal_place':'','applies_only_at':[],
           'condition':'market.crowded','hold_minutes':0,'note_ids':['N1']});revised['non_action_note_ids']=[]
    calls=[]
    def send(url,body,role,run):
        calls.append((role,json.loads(body['messages'][1]['content'])))
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(draft if len(calls)==1 else revised)}}]}
    monkeypatch.setattr(mp,'_send',send)
    result,audit=mp.interpret(source,'offline-coverage',candidate=guarded)
    assert [x[0] for x in calls]==['draft','interpretation_check']
    assert calls[1][1]['original_notes']==source['notes']
    assert 'N1' in str(calls[1][1]['structural_checks'])
    assert [r['action'] for r in result['rules']]==['rest','avoid']
    assert audit[-1]['adopted'] and not result['unrepresented']


def test_failed_source_reread_is_not_reported_as_fully_prepared(monkeypatch):
    from app import storage
    from app.config import settings
    from app.phase0 import mind_preparation as mp
    from app.llm import mind_policy as m
    from app.schemas.persona import Persona
    source={'notes':[{'id':'N0','text':'30분 걸으면 10분 쉰다.'},
                     {'id':'N1','text':'사람이 많은 시장을 피한다.'}], 'places':[], 'prepared_initial':{}}
    draft={'source_assessment':'휴식', 'rules':[{'action':'rest','goal_place':'','applies_only_at':[],
           'condition':'is_walking and continuous_walk_minutes >= 30','hold_minutes':10,'note_ids':['N0']}],
           'non_action_note_ids':['N1']}
    monkeypatch.setattr(mp,'selected',lambda:guarded)
    monkeypatch.setattr(mp,'enabled',lambda:True)
    monkeypatch.setattr(m,'source',lambda p:deepcopy(source))
    monkeypatch.setattr(m,'revision',lambda p:'coverage-regression')
    for key in ['kexaone_api_key','kexaone_base_url','kexaone_model']:
        monkeypatch.setattr(settings,key,'offline-test')
    calls=[]
    def send(url,body,role,run):
        calls.append(role)
        if len(calls)==2:raise ValueError('invalid reread')
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(draft)}}]}
    monkeypatch.setattr(mp,'_send',send)
    p=Persona(id='coverage-reread-failure',type='dementia',name='합성',age=78,home=HOME)
    storage.personas.save(p.id,p)
    try:
        saved=mp.prepare(p.id,retry=True)
        assert calls==['draft','interpretation_check']
        assert saved.prepared_mind['policy_quality']=='partial'
        assert mp.ready(saved)[1]=='ready_partial'
        assert saved.prepared_mind['interpretation_check_review']=='K_reread_failed_first_policy_kept'
    finally:storage.personas.delete(p.id)
