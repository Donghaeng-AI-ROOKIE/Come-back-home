"""Compile personal conditional behavior once; never during a walker update.

At most two public K outputs, no transport retry. A research contract may request
correction only after an invalid first output. Lifecycle is persisted with the
persona and deleted with it. Failure must not invalidate prepared initial traits.
"""
import json
import uuid
from datetime import datetime
from app import storage
from app.config import settings
from app.llm import mind_policy
from app.llm.mind_policy_profiles import selected
from app.llm.initial_behavior import decode_json_content
from app.llm.usage_ledger import logged_json_request


def enabled():
    return mind_policy.RELEASE_QUALIFIED or settings.mind_policy_deployment == 'staging'


def ready(persona):
    if persona is None:return None,'no_persona'
    if not enabled():return None,'candidate_not_qualified'
    saved=persona.prepared_mind;state=persona.mind_preparation_status.get('state','not_prepared')
    if state!='ready':
        old_revision=persona.mind_preparation_status.get('revision')
        if old_revision and old_revision!=mind_policy.revision(persona):return None,'stale'
        return None,state
    if saved.get('revision')!=mind_policy.revision(persona):return None,'stale'
    try:return mind_policy.validate(saved['policy'],mind_policy.source(persona)),('ready_partial' if saved.get('policy_quality')=='partial' else 'ready')
    except (ValueError,KeyError,TypeError):return None,'invalid'


def interpret(personal,run_id,*,candidate=None):
    candidate = candidate or selected()
    base=settings.kexaone_base_url.rstrip('/')
    url=base if base.endswith('/chat/completions') else base+('/chat/completions' if base.endswith('/v1') else '/v1/chat/completions')
    draft=None;audit=[];problem=None;draft_value=None
    for role in ('draft','review'):
        conditional=getattr(candidate,'REVIEW_POLICY',None)=='on_validation_failure'
        body=(candidate.repair_request(personal,settings.kexaone_model,draft,problem)
              if role=='review' and conditional else
              candidate.request(personal,settings.kexaone_model,draft=draft))
        if len(json.dumps(body,ensure_ascii=False).encode())>40000:raise ValueError('input byte cap')
        response=logged_json_request(url,body,
            headers={'Authorization':'Bearer '+settings.kexaone_api_key,'Content-Type':'application/json'},
            provider='FriendliAI',model=settings.kexaone_model,role='mind_policy_'+role,run_id=run_id,
            logical_request_id=run_id+':'+role,timeout=max(420,settings.kexaone_timeout),
            ledger_path=settings.research_usage_ledger_path,max_started=2)
        choice=response['choices'][0]
        finish=choice.get('finish_reason')
        if finish!='stop' and not (conditional and role=='draft' and finish=='length'):
            raise ValueError('incomplete policy output')
        content=choice['message'].get('content','')
        valid=True;recovery=None
        try:
            if finish!='stop':raise ValueError('incomplete policy output: '+str(finish))
            draft=decode_json_content(content)
            if role=='draft':draft_value=draft
            parsed=candidate.compile(draft,personal)
        except (ValueError,TypeError,KeyError,AssertionError,AttributeError,SyntaxError) as error:
            if role=='review':
                recover=getattr(candidate,'recover',None)
                if not conditional or recover is None:raise
                # A decoded, complete envelope is required. Invalid source or
                # no surviving rules still raises; never recover truncated JSON.
                parsed,recovery=recover(draft,personal)
            # The scheduled second source review may read a malformed public
            # draft. Never coerce its action or treat syntax repair as truth.
            draft=content;valid=False;problem=type(error).__name__+': '+str(error)[:1200]
        restored=[]
        restore=getattr(candidate,'restore_draft_scope',None)
        if role=='review' and restore is not None and (valid or recovery):
            parsed,restored=restore(draft_value,parsed,personal)
        audit.append({'role':role,'request_id':response.get('id'),'usage':response.get('usage'),
                      'schema_valid':valid,'finish_reason':finish,
                      **({'recovery':recovery} if recovery else {}),
                      **({'scope_restored_from_draft':restored} if restored else {})})
        if recovery:
            return parsed.model_dump(mode='json'),audit
        if valid and conditional:
            return parsed.model_dump(mode='json'),audit
    return parsed.model_dump(mode='json'),audit


def prepare(persona_id,*,retry=False,job_id=None):
    """Called by the existing background onboarding worker after initial prep."""
    candidate=selected()
    job=job_id or 'mind-policy:'+str(uuid.uuid4())
    def start(p):
        key=mind_policy.revision(p);old=p.mind_preparation_status
        if job_id is not None:
            if old.get('job_id')!=job_id or old.get('state')!='queued' or old.get('revision')!=key:return None
        elif old.get('state')=='queued' and old.get('revision')==key:return None
        if old.get('revision')==key and (old.get('state') in ('ready','running') or
              (old.get('state') in ('failed','interrupted') and not retry)):return None
        state='running'
        if not enabled():state='candidate_not_qualified'
        if not all((settings.kexaone_api_key,settings.kexaone_base_url,settings.kexaone_model)):state='unconfigured'
        if not mind_policy.source(p)['notes']:state='no_person_evidence'
        return p.model_copy(deep=True,update={'prepared_mind':{},'mind_preparation_status':{
            'state':state,'revision':key,'job_id':job,'updated_at':datetime.now().isoformat()}})
    snapshot=storage.personas.update_existing(persona_id,start)
    if snapshot is None or snapshot.mind_preparation_status['state']!='running':return
    key=mind_policy.revision(snapshot)
    try:
        policy,audit=interpret(mind_policy.source(snapshot),job,candidate=candidate)
        prepared={'version':mind_policy.VERSION,'revision':key,'policy':policy,'audit':audit,
                  'deployment_scope':settings.mind_policy_deployment,
                  'interpretation_contract':candidate.VERSION,
                  'semantic_review':('not_independently_validated' if
                      getattr(candidate,'REVIEW_POLICY',None)=='on_validation_failure' else
                      'K_original_source_repair_not_independent_human_validation'),
                  'public_output_count':len(audit),
                  'invalid_first_output_corrected':bool(audit and not audit[0]['schema_valid'] and audit[-1]['schema_valid']),
                  'policy_quality':'partial' if any(x.get('recovery') for x in audit) else 'compiled',
                  'quarantined_rule_count':sum(x.get('recovery',{}).get('quarantined_rule_count',0) for x in audit),
                  'quote_source':'exact_source_copied_from_named_note_when_unspecified'}
        state='ready';error=None
    except Exception as e:prepared={};state='failed';error=type(e).__name__
    def finish(p):
        if p.mind_preparation_status.get('job_id')!=job or mind_policy.revision(p)!=key:return None
        return p.model_copy(deep=True,update={'prepared_mind':prepared,'mind_preparation_status':{
            **p.mind_preparation_status,'state':state,'error_type':error,'updated_at':datetime.now().isoformat()}})
    return storage.personas.update_existing(persona_id,finish)


def enqueue(persona_id, *, retry=False):
    """Queue only the mind stage when initial preparation is current and ready."""
    from app.phase0 import person_preparation as pp
    job='mind-policy:'+str(uuid.uuid4())
    def mark(p):
        if (p.initial_preparation_status.get('state')!='ready' or
                p.prepared_initial.get('fingerprint')!=pp.fingerprint(p)):return None
        key=mind_policy.revision(p);old=p.mind_preparation_status
        current_ready=old.get('state')=='ready' and (not retry or ready(p)[0] is not None)
        if old.get('revision')==key and (old.get('state') in ('queued','running') or current_ready or
                (not retry and old.get('state') in ('failed','interrupted'))):return None
        state='queued'
        if not enabled():state='candidate_not_qualified'
        elif not all((settings.kexaone_api_key,settings.kexaone_base_url,settings.kexaone_model)):state='unconfigured'
        elif not mind_policy.source(p)['notes']:state='no_person_evidence'
        return p.model_copy(deep=True,update={'prepared_mind':{},'mind_preparation_status':{
            'state':state,'revision':key,'job_id':job,'updated_at':datetime.now().isoformat()}})
    saved=storage.personas.update_existing(persona_id,mark)
    if saved and saved.mind_preparation_status['state']=='queued':pp._dispatch(persona_id,job,'mind')
    return saved


def run_queued(persona_id,job_id):
    saved=prepare(persona_id,job_id=job_id)
    if saved and saved.mind_preparation_status.get('state')=='ready':
        from app.phase0.persona_events import notify_persona_updated
        notify_persona_updated(persona_id,saved.version)


def status(persona):
    """Public lifecycle only; no quotes, prompt, policy, request IDs or keys."""
    from app.phase0 import person_preparation as pp
    initial=persona.initial_preparation_status.get('state','not_prepared')
    if initial=='ready' and persona.prepared_initial.get('fingerprint')!=pp.fingerprint(persona):initial='stale'
    policy,mind=ready(persona)
    if initial!='ready' and mind in ('ready','ready_partial'):policy,mind=None,'stale'
    busy=initial in ('queued','running') or mind in ('queued','running')
    retryable={'failed','interrupted','stale','invalid','not_prepared'}
    if enabled() and all((settings.kexaone_api_key,settings.kexaone_base_url,settings.kexaone_model)):
        retryable.add('unconfigured')
    return {'initial_state':initial,'mind_state':mind,
        'can_retry':not busy and (initial in retryable or (initial=='ready' and mind in retryable)),
        'partial':mind=='ready_partial',
        'quarantined_rule_count':persona.prepared_mind.get('quarantined_rule_count',0) if policy else 0,
        'unrepresented_note_count':len(policy.unrepresented) if policy else 0,
        'contract':selected().VERSION}


def recover():
    # A crash may have happened after a billable request: never silently retry.
    for p in storage.personas.list():
        if p.mind_preparation_status.get('state')=='queued':
            from app.phase0.person_preparation import _dispatch
            _dispatch(p.id,p.mind_preparation_status['job_id'],'mind')
            continue
        if p.mind_preparation_status.get('state')!='running':continue
        job=p.mind_preparation_status.get('job_id')
        def interrupt(current):
            if current.mind_preparation_status.get('job_id')!=job:return None
            return current.model_copy(deep=True,update={'mind_preparation_status':{
                **current.mind_preparation_status,'state':'interrupted'}})
        storage.personas.update_existing(p.id,interrupt)
