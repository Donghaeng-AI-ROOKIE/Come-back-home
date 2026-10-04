"""Product adapter for persisted personal walkers, with explicit fallback quality."""
from copy import deepcopy
import hashlib,json
from app.config import settings
from app.phase0 import mind_preparation
from app.phase2.person_walk import Population,VERSION
from app.schemas.prediction import MindState


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def prior_key(case,persona):
    return digest({'report':case.report.model_dump(mode='json'),'anchor':case.lkp.model_dump(),
        'time':case.lkp_time,'person':persona.model_dump(mode='json') if persona else None})


def graph_key(net):
    # Cache identity includes actual geometry and roads, not just file names/counts.
    marker=getattr(net,'continuous_graph_key',None)
    if marker:return marker
    marker=digest({'nodes':sorted((str(n),d['x'],d['y']) for n,d in net.graph.nodes(data=True)),
        'edges':sorted((str(u),str(v),str(k),str(d)) for u,v,k,d in net.graph.edges(keys=True,data=True)),
        'coverage':getattr(net,'coverage_bbox',None)})
    net.continuous_graph_key=marker
    return marker


def run(case,persona,prior,net,hours,*,seed=None,persist=True):
    policy,status=mind_preparation.ready(persona)
    if policy is None:return None,{'engine':'legacy','personal_policy_status':status,'continuous_clock':False}
    if net is None or getattr(net,'coverage_bbox',None) is None:
        return None,{'engine':'legacy','personal_policy_status':status,'continuous_clock':False,
                     'reason':'verified_map_coverage_missing'}
    previous=case.continuous_state
    effective_seed=seed if seed is not None else previous.get('seed',42)
    key=digest({'version':VERSION,'person':prior_key(case,persona),'prior':prior.model_dump(mode='json'),
        'mind':(case.mind or MindState()).model_dump(mode='json'),
        'graph':graph_key(net),'environment':net.node_env,'seed':effective_seed,'walkers':settings.mc_num_walkers})
    checkpoint=None
    if previous.get('key')==key:
        candidate=previous['checkpoint']
        if all(p['minute']<=hours*60+1e-8 for p in candidate['particles']):checkpoint=candidate
    try:
        pop=Population(net,persona,prior,policy,case.lkp,case.lkp_time,count=settings.mc_num_walkers,
            seed=effective_seed,environment_observations=case.report.environment_observations,
            behavior_observations=case.report.behavior_observations,mind=case.mind,
            checkpoint=deepcopy(checkpoint))
        result=pop.advance_to(hours*60)
    except ValueError:
        # Unsupported context/uncertainty cannot turn into a stationary patient
        # or a successful empty map. Keep the last checkpoint and published map.
        return {},{'engine':VERSION,'unresolved_mass':1.,'resolved_mass':0.,
            'unresolved_reasons':{'invalid_simulation_context':settings.mc_num_walkers},
            'personal_policy_status':status,'continuous_clock':True,
            'preview':not persist,'error_type':'ValueError'}
    result['quality'].update(personal_policy_status='ready',continuous_clock=True,
        checkpoint_reused=checkpoint is not None,preview=not persist,
        semantic_validation='synthetic_only_not_clinical')
    if persist:
        case.continuous_state={'key':key,'seed':effective_seed,'checkpoint':pop.checkpoint()}
    return result['cells'],result['quality']


class IncompletePredictionError(RuntimeError):
    """A map boundary/censored walker must not disappear in probability pooling."""
