"""Product adapter for persisted personal walkers, with explicit fallback quality."""
from copy import deepcopy
import hashlib,json
from app.config import settings
from app import storage
from app.privacy import lifecycle
from app.phase0 import mind_preparation
from app.llm import mind_policy
from app.phase2 import person_walk, walker_traces
from app.phase2.persistent_context_walk import PersistentContextPopulation as Population, VERSION
from app.schemas.prediction import MindState, PriorParams


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def prior_key(case,persona):
    return digest({'numeric_snapshot_contract':'sar-before-personal-v1',
        'report':case.report.model_dump(mode='json'),'anchor':case.lkp.model_dump(),
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
    cells,quality=_run_policy(case,persona,prior,net,hours,policy,status,seed=seed,persist=persist,
        record_traces=persist)
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


def _start_traces(pop,key,previous):
    """Representative-path recorder for the personal channel, or None.

    A replay aid must never change or stop a prediction: any failure here only
    drops the traces of this run.
    """
    if settings.walker_trace_count<=0:return None
    try:
        recorder=walker_traces.Recorder(pop,settings.walker_trace_count,key=key,previous=previous,
            strategy_order=person_walk.STRATEGIES)
    except Exception:  # noqa: BLE001  a replay aid never stops a prediction
        walker_traces.log.warning('walker trace recording unavailable for this run',exc_info=True)
        return None
    pop.trace_hook=recorder
    return recorder


def _run_policy(case,persona,prior,net,hours,policy,status,*,seed=None,persist=True,record_traces=False):
    """One continuous channel. Only the personal channel records walker traces."""
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
        # Selection reads the strategies the walkers actually received. Traces
        # continue only on the same key's reused checkpoint; otherwise restart.
        recorder=(_start_traces(pop,key,previous.get('walker_traces') if checkpoint is not None else None)
                  if record_traces else None)
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
        state={'key':key,'seed':effective_seed,'checkpoint':pop.checkpoint()}
        traces=recorder.result(pop,hours*60) if recorder is not None else None
        if traces is not None:state['walker_traces']=traces
        case.continuous_state=state
    return result['cells'],result['quality']


def statistical_prior(prior):
    """Original SAR numbers before K adjustments, with a visible legacy limit."""
    if prior.sar_numeric_baseline:
        return PriorParams.model_validate(prior.sar_numeric_baseline), 'original_sar_numeric_snapshot'
    # Do not reverse-engineer an unrecorded radius or pretend the old snapshot
    # existed. Existing persisted priors stay usable with explicit disclosure.
    return prior, ('legacy_prepared_numbers_raw_sar_snapshot_missing'
                   if prior.persona_adjustments or prior.initial_interpretation.get('status')=='applied'
                   else 'unadjusted_prior_without_snapshot')


@storage.serialize_case
def run_pair(case,persona,prior,net,hours,*,seed=None,persist=True):
    """Separate onboarded SAR statistical walking from sourced personal mind walking.

    Shared physical observations and roads; separate conditional programs,
    numeric priors, direction states, RNG/checkpoints. A legacy definition can
    reproduce the previous comparison, without becoming the default mixture.
    """
    lifecycle.ensure_not_closed(case)
    staged=case.model_copy(deep=True)
    bu,quality=run(staged,persona,prior,net,hours,seed=seed,persist=True)
    quality.update(preview=not persist,checkpoint_committed=False)
    if quality.get('unresolved_mass',0)>1e-9:
        return bu,None,quality
    definition=settings.statistical_channel_definition
    if definition=='literature_distance_prior':
        from app.phase2.literature_distance import distance_map
        try:
            stat,sq=distance_map(case.lkp.lat,case.lkp.lng,hours,
                coverage_bbox=getattr(net,'coverage_bbox',None))
        except ValueError:
            quality.update(unresolved_mass=1-settings.personal_channel_weight,
                resolved_mass=settings.personal_channel_weight,checkpoint_committed=False,
                unresolved_reasons={'literature_distance_support_invalid':1},
                statistical_definition=definition)
            return bu,{},quality
        committed=bool(persist and bu is not None)
        quality.update(statistical=sq,checkpoint_committed=committed,
            both_channels_continuous=False,channel_contract='personal-mind-literature-distance-v1',
            statistical_definition=definition,statistical_uses_onboarding_prior=False,
            statistical_prior_source='ISRID_urban_lognormal_approximation',
            statistical_uses_conditional_mind_program=False,statistical_policy_free=True,
            personal_policy_shared_between_channels=False,
            personal_channel_weight=settings.personal_channel_weight,
            channels_identical=bu==stat,
            channel_total_variation=(.5*sum(abs(bu.get(c,0)-stat.get(c,0))
                for c in set(bu)|set(stat))) if bu is not None else None)
        if committed:
            staged.continuous_state.pop('statistical',None)
            case.continuous_state=staged.continuous_state
        return bu,stat,quality
    if bu is None:
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
    statistical_policy=shared_policy
    statistical_status=status
    statistical_numbers=prior
    statistical_prior_source="shared_prepared_prior"
    if definition=='onboarded_population_prior':
        statistical_policy=mind_policy.Policy(rules=[],unrepresented=[])
        statistical_status='onboarded_population_prior_without_personal_mind_program'
        statistical_numbers,statistical_prior_source=statistical_prior(prior)
        if statistical_prior_source=='legacy_prepared_numbers_raw_sar_snapshot_missing':
            # Old cases cannot truthfully supply the independent numeric channel
            # in a preview. A normal prediction refresh obtains the new snapshot
            # because prior_key versions this contract; preserve published state.
            quality.update(unresolved_mass=1.,resolved_mass=0.,checkpoint_committed=False,
                statistical_prior_source=statistical_prior_source,
                unresolved_reasons={'raw_sar_numeric_snapshot_missing':settings.mc_num_walkers})
            return {},{},quality
    stat,sq=_run_policy(statistical,persona,statistical_numbers,net,hours,
        statistical_policy,statistical_status,
        seed=staged.continuous_state['seed'],persist=True)
    complete=quality.get('unresolved_mass',0)<=1e-9 and sq.get('unresolved_mass',0)<=1e-9
    committed=bool(persist and complete)
    sq.update(preview=not persist,checkpoint_committed=committed)
    quality.update(statistical=sq,checkpoint_committed=committed,
        both_channels_continuous=True,
        channel_contract='independent-statistical-prior-personal-mind-v1',
        statistical_uses_onboarding_prior=True,
        statistical_prior_source=statistical_prior_source,
        statistical_uses_conditional_mind_program=definition=='shared_personal_policy',
        statistical_definition=definition,
        personal_policy_shared_between_channels=definition=='shared_personal_policy',
        statistical_policy_free=definition=='onboarded_population_prior',
        mixture_weights_status='configured_pending_development_validation',
        personal_channel_weight=settings.personal_channel_weight,
        channels_identical=bu==stat,
        channel_total_variation=.5*sum(abs(bu.get(c,0)-stat.get(c,0)) for c in set(bu)|set(stat)))
    if not complete:
        quality['personal_unresolved_mass']=quality.get('unresolved_mass',0)
        quality['unresolved_mass']=settings.personal_channel_weight*quality['personal_unresolved_mass']+(1-settings.personal_channel_weight)*sq['unresolved_mass']
        quality['resolved_mass']=settings.personal_channel_weight*sum(bu.values())+(1-settings.personal_channel_weight)*sum(stat.values())
        quality['unresolved_reasons']={'statistical:'+k:v for k,v in sq['unresolved_reasons'].items()}
    if committed:
        staged.continuous_state['statistical']=statistical.continuous_state
        case.continuous_state=staged.continuous_state
    return bu,stat,quality


class IncompletePredictionError(RuntimeError):
    """A map boundary/censored walker must not disappear in probability pooling."""
