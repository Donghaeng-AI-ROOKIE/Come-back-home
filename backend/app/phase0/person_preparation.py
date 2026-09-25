"""Prepare typed personal behavior after onboarding, never in prediction requests.

Queued state and ready result are persisted with Persona. Restarted running work is
marked interrupted (no automatic paid retry). Old-version completions are discarded.
"""
import copy
import hashlib
import json
import logging
import queue
import threading
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from app import storage
from app.config import settings
from app.llm import initial_behavior, person_evidence

VERSION = "onboarding-person-v2"
_jobs = queue.Queue()
_start_lock = threading.Lock()
_started = False


def fingerprint(persona):
    payload=initial_behavior.build_payload(persona,None,[],None)
    # Legacy scoring can finish later; derived numerical axes are not K source facts.
    payload.pop('existing_compiled_features');payload.pop('SAR_reference')
    return hashlib.sha256(json.dumps({'version':VERSION,'model':settings.kexaone_model,
        'persona_version':persona.version,'payload':payload},ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def _worker():
    while True:
        job=_jobs.get()
        try:
            run_job(*job)
        except Exception as exc:
            # One broken persisted job must not kill the queue worker or log PII.
            logging.getLogger(__name__).error("Preparation worker failed: %s", type(exc).__name__)
        finally:
            _jobs.task_done()


def _dispatch(persona_id, job_id):
    global _started
    with _start_lock:
        if not _started:
            for i in range(2):
                threading.Thread(target=_worker,name=f'person-preparation-{i}',daemon=True).start()
            _started=True
    _jobs.put((persona_id,job_id))


def enqueue(persona_id, *, retry=False):
    job_id=str(uuid.uuid4())
    def mark(current):
        key=fingerprint(current);status=current.initial_preparation_status
        if status.get('fingerprint')==key and (status.get('state') in {'queued','running','ready'} or (not retry and status.get('state') in {'failed','interrupted'})):
            return None
        state='queued' if all((settings.kexaone_api_key,settings.kexaone_base_url,settings.kexaone_model)) else 'unconfigured'
        if not initial_behavior.build_payload(current,None,[],None)['notes']:state='no_person_evidence'
        return current.model_copy(deep=True,update={'prepared_initial':{},'initial_preparation_status':{
            'state':state,'job_id':job_id,'fingerprint':key,'version':VERSION,'updated_at':datetime.now().isoformat()}})
    updated=storage.personas.update_existing(persona_id,mark)
    if updated and updated.initial_preparation_status['state']=='queued':_dispatch(persona_id,job_id)
    return updated


def run_job(persona_id, job_id):
    from app.phase2 import initial_person
    def start(p):
        state=p.initial_preparation_status
        if state.get('job_id')!=job_id or state.get('state')!='queued':return None
        return p.model_copy(deep=True,update={'initial_preparation_status':dict(state,state='running')})
    snapshot=storage.personas.update_existing(persona_id,start)
    if snapshot is None:return
    key=fingerprint(snapshot)
    try:
        research=initial_person.cached_research(snapshot,None)
        payload=initial_behavior.build_payload(snapshot,None,research,None)
        parsed=initial_person.interpret(payload)
        prepared={'version':VERSION,'fingerprint':key,'core':parsed['core'],'scope':parsed['context'],
                  'retrieval_audit':payload['retrieval_audit'],'prepared_at':datetime.now().isoformat(),
                  'profile_snapshot_at':snapshot.initial_preparation_status['updated_at'],'persona_version':snapshot.version}
        state='ready';error=None
    except Exception as exc:
        prepared={};state='failed';error=type(exc).__name__
    def finish(current):
        if current.initial_preparation_status.get('job_id')!=job_id or fingerprint(current)!=key:return None
        return current.model_copy(deep=True,update={'prepared_initial':prepared,
            'initial_preparation_status':dict(current.initial_preparation_status,state=state,
                error_type=error,updated_at=datetime.now().isoformat())})
    saved=storage.personas.update_existing(persona_id,finish)
    if saved and state=='ready':
        # Existing active cases can now use prepared traits without another K call.
        from app.phase0.persona_events import notify_persona_updated
        notify_persona_updated(persona_id,saved.version)


def recover():
    for p in storage.personas.list():
        status=p.initial_preparation_status
        if status.get('state')=='queued':_dispatch(p.id,status['job_id'])
        elif status.get('state')=='running':
            def interrupt(current):
                if current.initial_preparation_status.get('job_id')!=status.get('job_id'):return None
                return current.model_copy(deep=True,update={'initial_preparation_status':dict(status,state='interrupted')})
            storage.personas.update_existing(p.id,interrupt)


def _local_naive(dt):
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def apply_prepared(persona, report, sar, default):
    try:
        return _apply_prepared(persona, report, sar, default)
    except (KeyError, ValueError, TypeError, AttributeError):
        return sar.model_copy(update={'initial_interpretation':{'status':'preparation_invalid',
            'version':VERSION,'K_called_during_prediction':False}})


def _apply_prepared(persona, report, sar, default):
    """Local compilation only. Prepared day/night rules stay separate until incident."""
    from app.phase2.person_projection import compile_person
    if persona is None:
        return sar.model_copy(update={'initial_interpretation':{'status':'no_persona',
            'version':VERSION,'K_called_during_prediction':False}})
    saved=persona.prepared_initial;state=persona.initial_preparation_status.get('state','not_prepared')
    if state!='ready' or saved.get('fingerprint')!=fingerprint(persona):
        return sar.model_copy(update={'initial_interpretation':{'status':'preparation_'+(state if state!='ready' else 'stale'),
            'version':VERSION,'K_called_during_prediction':False}})
    core=copy.deepcopy(saved['core']);scope=copy.deepcopy(saved['scope']);rules=scope.pop('behavior_rules',[])
    baseline_direction=scope.pop('baseline_direction',None)
    if baseline_direction is not None:
        core['direction']={**baseline_direction,'explanation':'조건 과업의 무조건 방향 판단.'}
    # Stored naive timestamps follow server-local time; evaluate Korean clock rules
    # in the service region even when the container itself runs in UTC.
    incident_hour = report.lkp_time.astimezone(ZoneInfo('Asia/Seoul')).hour
    period='clock_day' if 6 <= incident_hour < 18 else 'clock_night'
    # One statement or trip describes the registration time; months later it is not the
    # incident's intention. Recurring habits persist, but only in the clock period they
    # occur. A profile first created after the incident (urgent report) describes the
    # incident itself, so its single reports are not demoted.
    registered_before_incident=_local_naive(persona.created_at)<_local_naive(report.lkp_time)
    for label,leaf in core['goals'].items():
        if leaf['value'] in person_evidence.PERSISTENT_GOALS:
            if leaf.get('period','unspecified') not in ('unspecified',period):
                leaf['value']='historical_only'
                leaf['explanation']='다른 시간대의 반복 목적. 이번 사건 시간대에는 적용하지 않음.'
        elif registered_before_incident and leaf['value'] in {'current_statement','recent_action','explicit_rejection'}:
            leaf['value']='historical_only'
            leaf['explanation']='사전등록 당시 보고. 이번 사건의 현재 의도는 미확인.'
    # Supported clock-period rules are typed K output, never parsed guardian words.
    for dimension in ('persistence','direction'):
        candidates=[r for r in rules if r['dimension']==dimension and r['period']==period]
        if any(r['dimension']==dimension for r in rules):
            values={r['value'] for r in candidates};value=next(iter(values)) if len(values)==1 else 'unknown'
            ids=sorted({n for r in candidates for n in r['note_ids']})
            core[dimension]={'value':value,'note_ids':ids,'explanation':'저장된 시간대별 개인 관찰의 적용.'}
            if dimension=='persistence':scope['persistence']={'value':value,'note_ids':ids,
                'evidence':'supported' if candidates else 'missing','pattern':'conditional' if candidates else 'unresolved',
                'explanation':'저장된 시간대별 개인 관찰의 적용.'}
    payload=initial_behavior.build_payload(persona,report,[],sar);payload['retrieval_audit']=saved.get('retrieval_audit',[])
    try:
        result=compile_person(core,scope,payload,persona,sar,default)
    except (ValueError,KeyError,TypeError):
        return sar.model_copy(update={'initial_interpretation':{'status':'preparation_invalid','version':VERSION,'K_called_during_prediction':False}})
    prepared_at = datetime.fromisoformat(saved['prepared_at']) if saved.get('prepared_at') else None
    result.initial_interpretation.update(
        prepared_before_incident=(prepared_at < report.lkp_time if prepared_at is not None else None),
        prepared_outside_prediction=True,K_called_during_prediction=False,
        preparation_fingerprint=saved['fingerprint'],profile_snapshot_at=saved.get('profile_snapshot_at'),
        goal_temporality='recurring goals kept in their clock period; single reports before the incident treated as historical',
        registered_before_incident=registered_before_incident,behavior_rules=rules,selected_clock_period=period,
        clock_period_definition='Asia/Seoul 06:00–18:00 clock_day; otherwise clock_night; not observed brightness')
    return result
