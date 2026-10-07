"""Isolated real onboarding functions, live Mi:dm/embedding, synthetic guardian.

Run from a copied source package in a fresh process/container directory. No
HTTP call to the production app, persistent DB, scoring GPU, K preparation,
map/geocoding API, actual guardian, or notification is used. All model calls
are metered before sending. This captures input, not an accuracy verdict.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--site-json',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if not a.execute:
        raise SystemExit('preparation only; --execute required')
    # Set before importing app modules, in this one test subprocess only.
    os.environ.update(PERSIST_STORAGE='false',AXIS_SCORING_ENABLED='false',
                      KEXAONE_API_KEY='',EXAONE_API_KEY='',EXAONE_BASE_URL='',
                      RESEARCH_USAGE_LEDGER_PATH=str(a.output/'usage_events.jsonl'))
    from app.config import settings
    from app.llm import usage_ledger
    from experiments.mind_contract_ab_20261007 import onboarding_fixture as case
    if settings.persist_storage or settings.axis_scoring_enabled or settings.kexaone_api_key:
        raise SystemExit('isolation settings not applied')
    if not all((settings.midm_api_key,settings.midm_base_url,settings.midm_model,
                settings.embed_base_url,settings.embed_model,settings.embed_api_key)):
        raise SystemExit('live Mi:dm/embedding settings missing; do not substitute stubs')
    a.output.mkdir(parents=True,exist_ok=True)
    marker=a.output/'launched.json'
    with marker.open('x') as f:
        json.dump({'started':datetime.now(timezone.utc).isoformat(),'synthetic':True,
                   'paid_retries':False,'caps':{'midm':120,'embedding':200}},f)
    def save(name,value):
        dest=a.output/name;dest.parent.mkdir(parents=True,exist_ok=True)
        tmp=dest.with_suffix(dest.suffix+'.tmp')
        tmp.write_text(json.dumps(value,ensure_ascii=False,indent=1,default=str)+'\n')
        tmp.replace(dest)
    original_request=usage_ledger.logged_json_request
    counts={'midm':0,'embedding':0}
    def logged(url,body,**kw):
        provider=kw.get('provider')
        if provider=='KT Mi:dm':kind='midm';limit=120
        elif provider=='embedding_api':kind='embedding';limit=200
        else:raise RuntimeError('unexpected provider in onboarding capture')
        counts[kind]+=1
        job=f'{kind}_{counts[kind]:03}'
        kw.update(run_id='MIND_actual_onboarding_20261008_'+kind,logical_request_id=job,
                  max_started=limit,ledger_path=a.output/'usage_events.jsonl')
        # Request bodies contain only this fixture. Never write headers/keys.
        save('calls/'+job+'.request.json',{'provider':provider,'model':kw.get('model'),
                                          'role':kw.get('role'),'body':body})
        try:
            result=original_request(url,body,**kw)
        except Exception as exc:
            save('calls/'+job+'.error.json',{'error_type':type(exc).__name__})
            raise
        save('calls/'+job+'.response.json',result)
        return result
    usage_ledger.logged_json_request=logged
    # app.llm.__init__ imports MidmClient before this wrapper is installed.
    # Patch that module's bound alias too; otherwise its common ledger records
    # calls but this fixture counter and cap do not see them.
    import importlib
    importlib.import_module('app.llm.midm').logged_json_request=logged
    # Import only after the global metered request wrapper is installed.
    from app import storage
    from app.phase0 import interview
    from app.geo.geocode import GeoResult
    from app.schemas.common import GeoPoint
    from app.llm import mind_policy
    from app.schemas.persona import PersonaType
    from app.phase0.retrieval import OpenAICompatEmbedder
    if interview.midm.is_stub or not isinstance(interview._EMB,OpenAICompatEmbedder):
        raise RuntimeError('live clients not selected')
    site=json.loads(a.site_json.read_text())
    home=GeoPoint(**site['location'])
    placements={name:GeoPoint(**g['location']) for name,g in
                 zip(('느티공원','해든상가','솔빛쉼터'),site['goals'])}
    class FixtureGeo:
        def locate(self,query,anchor=None):
            for label,point in placements.items():
                if label in query:
                    return GeoResult(point,'poi','synthetic_fixture',matched=label,address=case.HOME)
            if '대화동' in query or query==case.HOME:
                return GeoResult(home,'dong','synthetic_fixture',matched=case.HOME,address=case.HOME)
            return None
        def geocode(self,query):
            value=self.locate(query)
            return value.point if value else None
    interview._GEO=FixtureGeo()
    trace=[];session=None
    try:
        session=interview.start_interview('합성 보호자',PersonaType.dementia)
        for turn in range(48):
            if session.done:break
            question=next((m['text'] for m in reversed(session.messages) if m['role']=='assistant'),'')
            key=session.prev_target_key
            if session.awaiting_confirmation:
                if (str(session.draft_fields.get('name','')).removesuffix('님')!=case.NAME or
                    interview._parse_age(session.draft_fields.get('age'))!=case.AGE):
                    raise ValueError('identity extraction mismatch; no synthetic confirmation sent')
                answer='네, 맞아요.'
                origin='synthetic_confirmation_identity_checked_other_summary_unreviewed'
            elif session.pending_area_label:
                answer=f'{session.pending_area_label}는 {case.HOME}에 있어요.'
                origin='synthetic_area_answer'
            else:
                if key not in case.ANSWERS:
                    raise ValueError('unexpected slot; inspect question before answering')
                answer=case.ANSWERS[key];origin='fixed_synthetic_guardian_answer_for_app_slot'
            trace.append({'turn':turn,'slot':key,'question':question,'answer':answer,'answer_source':origin})
            save('transcript.json',trace)
            session=interview.answer_interview(session.id,answer)
            save('session.json',session.model_dump(mode='json'))
            save('status.json',{'state':'onboarding','turns':len(trace),'calls':counts,
                               'done':session.done,'llm_degraded':session.llm_degraded})
            print(json.dumps({'turn':turn,'slot':key,'calls':counts,'done':session.done}),flush=True)
        if not session.done or not session.persona_id:
            raise RuntimeError('interview_not_finished_within_fixture_turn_cap')
        persona=storage.personas.get(session.persona_id)
        save('persona.json',persona.model_dump(mode='json'))
        personal=mind_policy.source(persona)
        save('personal_source.json',personal)
        save('status.json',{'state':'input_captured_not_quality_verdict','calls':counts,'turns':len(trace),
            'source_notes':len(personal['notes']),'llm_degraded':session.llm_degraded,
            'initial_preparation':persona.initial_preparation_status,
            'limits':['synthetic guardian','synthetic facility coordinates on KINTEX',
                      'summary semantics not independently reviewed','no mind model execution yet']})
    except BaseException as exc:
        save('status.json',{'state':'needs_diagnosis','error_type':type(exc).__name__,
                            'calls':counts,'turns':len(trace)})
        if session:
            save('session.json',session.model_dump(mode='json'))
        raise


if __name__=='__main__':
    main()
