"""Compile personal conditional behavior once; never during a walker update.

Two public K outputs, no retry. Lifecycle is persisted with the persona and deleted
with it. A failure here must not invalidate already prepared initial traits.
"""
import json
import uuid
from datetime import datetime
from app import storage
from app.config import settings
from app.llm import mind_policy, mind_policy_candidate
from app.llm.initial_behavior import decode_json_content
from app.llm.usage_ledger import logged_json_request


def ready(persona):
    if persona is None:return None,'no_persona'
    if not mind_policy.RELEASE_QUALIFIED:return None,'candidate_not_qualified'
    saved=persona.prepared_mind;state=persona.mind_preparation_status.get('state','not_prepared')
    if state!='ready':return None,state
    if saved.get('revision')!=mind_policy.revision(persona):return None,'stale'
    try:return mind_policy.validate(saved['policy'],mind_policy.source(persona)),'ready'
    except (ValueError,KeyError,TypeError):return None,'invalid'


def interpret(personal,run_id):
    base=settings.kexaone_base_url.rstrip('/')
    url=base if base.endswith('/chat/completions') else base+('/chat/completions' if base.endswith('/v1') else '/v1/chat/completions')
    draft=None;audit=[]
    for role in ('draft','review'):
        body=mind_policy_candidate.request(personal,settings.kexaone_model,draft=draft)
        if len(json.dumps(body,ensure_ascii=False).encode())>40000:raise ValueError('input byte cap')
        response=logged_json_request(url,body,
            headers={'Authorization':'Bearer '+settings.kexaone_api_key,'Content-Type':'application/json'},
            provider='FriendliAI',model=settings.kexaone_model,role='mind_policy_'+role,run_id=run_id,
            logical_request_id=run_id+':'+role,timeout=max(420,settings.kexaone_timeout),
            ledger_path=settings.research_usage_ledger_path,max_started=2)
        choice=response['choices'][0]
        if choice.get('finish_reason')!='stop':raise ValueError('incomplete policy output')
        content=choice['message'].get('content','')
        valid=True
        try:
            draft=decode_json_content(content)
            parsed=mind_policy_candidate.compile(draft,personal)
        except (ValueError,TypeError,KeyError,AssertionError,AttributeError):
            if role=='review':raise
            # The scheduled second source review may read a malformed public
            # draft. Never coerce its action or treat syntax repair as truth.
            draft=content;valid=False
        audit.append({'role':role,'request_id':response.get('id'),'usage':response.get('usage'),
                      'schema_valid':valid})
    return parsed.model_dump(mode='json'),audit


def prepare(persona_id,*,retry=False):
    """Called by the existing background onboarding worker after initial prep."""
    job='mind-policy:'+str(uuid.uuid4())
    def start(p):
        key=mind_policy.revision(p);old=p.mind_preparation_status
        if old.get('revision')==key and (old.get('state') in ('ready','running') or
              (old.get('state') in ('failed','interrupted') and not retry)):return None
        state='running'
        if not mind_policy.RELEASE_QUALIFIED:state='candidate_not_qualified'
        if not all((settings.kexaone_api_key,settings.kexaone_base_url,settings.kexaone_model)):state='unconfigured'
        if not mind_policy.source(p)['notes']:state='no_person_evidence'
        return p.model_copy(deep=True,update={'prepared_mind':{},'mind_preparation_status':{
            'state':state,'revision':key,'job_id':job,'updated_at':datetime.now().isoformat()}})
    snapshot=storage.personas.update_existing(persona_id,start)
    if snapshot is None or snapshot.mind_preparation_status['state']!='running':return
    key=mind_policy.revision(snapshot)
    try:
        policy,audit=interpret(mind_policy.source(snapshot),job)
        prepared={'version':mind_policy.VERSION,'revision':key,'policy':policy,'audit':audit,
                  'semantic_review':'K_original_source_repair_not_independent_human_validation',
                  'quote_source':'exact_source_copied_from_named_note_when_unspecified'}
        state='ready';error=None
    except Exception as e:prepared={};state='failed';error=type(e).__name__
    def finish(p):
        if p.mind_preparation_status.get('job_id')!=job or mind_policy.revision(p)!=key:return None
        return p.model_copy(deep=True,update={'prepared_mind':prepared,'mind_preparation_status':{
            **p.mind_preparation_status,'state':state,'error_type':error,'updated_at':datetime.now().isoformat()}})
    return storage.personas.update_existing(persona_id,finish)


def recover():
    # A crash may have happened after a billable request: never silently retry.
    for p in storage.personas.list():
        if p.mind_preparation_status.get('state')!='running':continue
        job=p.mind_preparation_status.get('job_id')
        def interrupt(current):
            if current.mind_preparation_status.get('job_id')!=job:return None
            return current.model_copy(deep=True,update={'mind_preparation_status':{
                **current.mind_preparation_status,'state':'interrupted'}})
        storage.personas.update_existing(p.id,interrupt)
