from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
import json
import pytest
from app.geo.roadnet import OSMnxNetwork
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona,AttractionPoint
from app.schemas.prediction import PriorParams,LognormalParams
from app.schemas.environment import EnvironmentObservation

START=datetime(2026,9,28,8)
FIXTURE=Path(__file__).parent/'fixtures/kintex_walk.graphml'
MANIFEST=FIXTURE.with_suffix('.json')
# Contract tests do not simulate geography. Spatial tests require the verified
# KINTEX fixture; there is deliberately no fallback to the old test region.
P=GeoPoint(lat=0,lng=0)

def person(location=P):
    return Persona(id='synthetic',name='합성',age=78,type='dementia',home=location,
        onboarding_turns=[{'slot':'mobility','question':'피곤할 때는 어떻게 하나요?',
                           'answer':'무릎이 아프면 앉아서 쉬고 다시 걸어요.'}],
        behavior_notes=['피곤해도 계속 걷는다'],
        attraction_points=[AttractionPoint(label='등록 목적지',location=location,place_type='market')])

def prior():
    return PriorParams(strategy_probs={'random_walk':1},attraction_weights={'등록 목적지':1},
        radius_lognormal=LognormalParams(mu=0,sigma=1),
        initial_interpretation={'semantic_contract':{'other_traits':[{'type':'rest','condition':'pain'}]},
                                'unrepresented':[{'feature':'trait.rest'}]})

@pytest.fixture(scope='module')
def geography():
    if not FIXTURE.exists() or not MANIFEST.exists():pytest.skip('KINTEX cache required; no alternate geography')
    meta=json.loads(MANIFEST.read_text());assert meta['region']=='KINTEX, Goyang'
    return OSMnxNetwork.from_graphml(FIXTURE),GeoPoint(**meta['center'])
