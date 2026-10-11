"""Product adapter for persisted personal walkers, with explicit fallback quality."""
from copy import deepcopy
import hashlib,json
from app.config import settings
from app import storage
from app.privacy import lifecycle
from app.phase0 import mind_preparation
from app.llm import mind_policy
from app.phase2 import person_walk
from app.phase2.persistent_context_walk import PersistentContextPopulation as Population, VERSION
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


@storage.serialize_case
def run(case,persona,prior,net,hours,*,seed=None,persist=True):
    lifecycle.ensure_not_closed(case)
    policy,status,sequence=_executable_policy(persona)
    if policy is None:return None,{'engine':'legacy','personal_policy_status':status,'continuous_clock':False}
    if net is None or getattr(net,'coverage_bbox',None) is None:
        return None,{'engine':'legacy','personal_policy_status':status,'continuous_clock':False,
                     'reason':'verified_map_coverage_missing'}
    cells,quality=_run_policy(case,persona,prior,net,hours,policy,status,seed=seed,persist=persist)
    quality['sequence_normalization']=sequence
    # Disclosure only: structural interpretation warnings never change execution.
    quality['interpretation_checks']=mind_policy.interpretation_checks(policy)
    return cells,quality


def _executable_policy(persona):
    """Stored policy stays unchanged; ordering is applied for execution only."""
    policy,status=mind_preparation.ready(persona)
    if policy is None:return None,status,None
    policy,report=mind_policy.normalize_sequences(policy)
    return policy,status,report


def _run_policy(case,persona,prior,net,hours,policy,status,*,seed=None,persist=True):
    previous=case.continuous_state
    effective_seed=seed if seed is not None else previous.get('seed',42)
    # Both executor layers version the checkpoint: a walker change must never
    # reuse a checkpoint the walker itself would reject as stale.
    key=digest({'version':VERSION,'walker':person_walk.VERSION,'person':prior_key(case,persona),'prior':prior.model_dump(mode='json'),
        'policy':policy.model_dump(mode='json'),
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
    result['quality'].update(personal_policy_status=status,continuous_clock=True,
        interpretation_contract=persona.prepared_mind.get('interpretation_contract'),
        personal_policy_quality=persona.prepared_mind.get('policy_quality','compiled'),
        quarantined_rule_count=persona.prepared_mind.get('quarantined_rule_count',0),
        unrepresented_note_count=len({x.note_id for x in policy.unrepresented}),
        policy_contract=persona.prepared_mind.get('version'),
        deployment_scope=settings.mind_policy_deployment,
        checkpoint_reused=checkpoint is not None,preview=not persist,
        semantic_validation='synthetic_only_not_clinical')
    # The caller rejects incomplete probability maps. Do not commit their
    # censored particles either: the next retry must start from the last
    # complete checkpoint, not from permanently blocked walkers.
    complete=result['quality']['unresolved_mass']<=1e-9
    result['quality']['checkpoint_committed']=bool(persist and complete)
    if persist and complete:
        case.continuous_state={'key':key,'seed':effective_seed,'checkpoint':pop.checkpoint()}
    return result['cells'],result['quality']


@storage.serialize_case
def run_pair(case,persona,prior,net,hours,*,seed=None,persist=True):
    """Same initial person, two continuous clocks, one atomic checkpoint.

    Both channels retain the same prepared conditional personal policy. Only the
    agent channel receives the updated mind state. Removing personal reactions
    is an experimental ablation, not the second person in a production mixture.
    The statistical name is kept for compatibility; it is not independent of
    personal information. Fixed 0.7:0.3 weights are not retuned here.
    """
    lifecycle.ensure_not_closed(case)
    staged=case.model_copy(deep=True)
    bu,quality=run(staged,persona,prior,net,hours,seed=seed,persist=True)
    quality.update(preview=not persist,checkpoint_committed=False)
    if bu is None or quality.get('unresolved_mass',0)>1e-9:
        return bu,None,quality
    shared_policy,status,_=_executable_policy(persona)
    if shared_policy is None:
        # Never silently replace a policy that became unavailable with an empty
        # program and publish that counterfactual as 30% of the final map.
        quality.update(unresolved_mass=1.,resolved_mass=0.,
            unresolved_reasons={'shared_personal_policy_unavailable':settings.mc_num_walkers},
            personal_policy_status=status)
        return {},{},quality
    statistical=case.model_copy(deep=True)
    statistical.mind=None
    statistical.continuous_state=deepcopy(case.continuous_state.get('statistical',{}))
    # Common initial random numbers make the no-policy contrast interpretable;
    # each channel then persists its own random state independently.
    stat,sq=_run_policy(statistical,persona,prior,net,hours,
        shared_policy,status,
        seed=staged.continuous_state['seed'],persist=True)
    complete=quality.get('unresolved_mass',0)<=1e-9 and sq.get('unresolved_mass',0)<=1e-9
    committed=bool(persist and complete)
    sq.update(preview=not persist,checkpoint_committed=committed)
    quality.update(statistical=sq,checkpoint_committed=committed,
        both_channels_continuous=True,
        statistical_definition='same_initial_person_and_conditional_policy_without_updated_mind',
        personal_policy_shared_between_channels=True,
        policy_free_ablation_included_in_mixture=False,
        mixture_weights_status='fixed_0.7_0.3_not_revalidated_for_continuous_pair')
    if not complete:
        quality['personal_unresolved_mass']=quality.get('unresolved_mass',0)
        quality['unresolved_mass']=.7*quality['personal_unresolved_mass']+.3*sq['unresolved_mass']
        quality['resolved_mass']=.7*sum(bu.values())+.3*sum(stat.values())
        quality['unresolved_reasons']={'statistical:'+k:v for k,v in sq['unresolved_reasons'].items()}
    if committed:
        staged.continuous_state['statistical']=statistical.continuous_state
        case.continuous_state=staged.continuous_state
    return bu,stat,quality


class IncompletePredictionError(RuntimeError):
    """A map boundary/censored walker must not disappear in probability pooling."""
