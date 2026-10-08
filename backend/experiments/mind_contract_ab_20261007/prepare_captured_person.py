"""Isolated production initial interpretation on a saved synthetic app onboarding.

Directly calls the real retrieval/interpret/claim-check functions in a fresh
process; does not enqueue jobs, touch the production DB, notify cases or deploy.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import threading


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--persona', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--rag-index', type=Path, required=True); p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if not a.execute: raise SystemExit('explicit execution flag required')
    a.output.mkdir(parents=True, exist_ok=True)
    with (a.output / 'launched.json').open('x') as f:
        json.dump({'started': datetime.now(timezone.utc).isoformat(), 'synthetic': True,
                   'caps': {'k': 4, 'midm': 80, 'embedding': 2}, 'automatic_retries': False}, f)
    os.environ.update(PERSIST_STORAGE='false', AXIS_SCORING_ENABLED='false',
        EXAONE_API_KEY='', EXAONE_BASE_URL='', RAG_INDEX_PATH=str(a.rag_index),
        KEXAONE_TIMEOUT='600', RESEARCH_USAGE_LEDGER_PATH=str(a.output / 'usage_events.jsonl'))
    from app.config import settings
    from app.llm import usage_ledger
    from app.schemas.persona import Persona
    from app.llm import initial_behavior, mind_policy
    if settings.persist_storage or settings.axis_scoring_enabled:
        raise RuntimeError('isolation not active')
    if not all((settings.kexaone_api_key, settings.midm_api_key, settings.embed_api_key)):
        raise RuntimeError('required live credentials not configured')
    original = usage_ledger.logged_json_request
    lock = threading.Lock(); counts = {'k': 0, 'midm': 0, 'embedding': 0}
    failures = []; refused = []; caps = {'k': 4, 'midm': 80, 'embedding': 2}
    def save(name, value):
        path = a.output / name; path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + '.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=1, default=str) + '\n'); temp.replace(path)
    def logged(url, body, **kwargs):
        provider = kwargs.get('provider')
        kind = {'FriendliAI': 'k', 'KT Mi:dm': 'midm', 'embedding_api': 'embedding'}.get(provider)
        if kind is None: raise RuntimeError('unexpected provider')
        with lock:
            if counts[kind] >= caps[kind]:
                refused.append({'kind': kind, 'reason': 'call_cap', 'submitted': False})
                raise RuntimeError('registered call cap exceeded')
            counts[kind] += 1; job = f'{kind}_{counts[kind]:03}'
        if len(json.dumps(body, ensure_ascii=False).encode()) > 120000:
            refused.append({'kind': kind, 'reason': 'input_byte_cap', 'submitted': False})
            raise RuntimeError('registered input cap exceeded')
        if kind in ('k', 'midm'):
            bound = 28000 if kind == 'k' else 40
            if body.get('max_tokens', 0) > bound: raise RuntimeError('registered output cap exceeded')
        kwargs.update(run_id='MIND_captured_initial_20261008_' + kind,
            logical_request_id=job, max_started=caps[kind], ledger_path=a.output / 'usage_events.jsonl')
        save('calls/' + job + '.request.json', {'role': kwargs.get('role'), 'body': body})
        try:
            result = original(url, body, **kwargs)
        except Exception as e:
            with lock: failures.append({'job': job, 'error_type': type(e).__name__})
            save('calls/' + job + '.error.json', {'error_type': type(e).__name__}); raise
        if kind == 'k':
            c = result['choices'][0]
            content = c['message'].get('content') or ''
            if '</think>' in content: content = content.rsplit('</think>', 1)[-1].strip()
            if '<think>' in content: content = '[no separable final output]'
            stored = {'final_content': content, 'finish_reason': c.get('finish_reason'), 'usage': result.get('usage')}
        elif kind == 'embedding': stored = {'usage': result.get('usage'), 'vector_count': len(result.get('data', []))}
        else: stored = result
        save('calls/' + job + '.response.json', stored)
        return result
    usage_ledger.logged_json_request = logged
    importlib.import_module('app.llm.midm').logged_json_request = logged
    from app.phase2 import initial_person, claim_check
    initial_person.logged_json_request = logged
    from app.phase0.person_preparation import fingerprint, VERSION
    from app.rag import get_retriever
    persona = Persona.model_validate_json(a.persona.read_text())
    try:
        save('status.json', {'state': 'retrieving', 'calls': counts})
        retriever = get_retriever()
        if retriever is None or not retriever.available: raise RuntimeError('existing RAG unavailable')
        research = initial_person.cached_research(persona, None)
        save('research.json', research)
        if not research or failures: raise RuntimeError('existing RAG retrieval failed')
        payload = initial_behavior.build_payload(persona, None, research, None)
        save('payload.json', payload)
        save('input_manifest.json', {'persona_sha256': hashlib.sha256(a.persona.read_bytes()).hexdigest(),
            'rag_index_sha256': hashlib.sha256(a.rag_index.read_bytes()).hexdigest(),
            'source_notes': len(initial_behavior.evidence_notes(payload)),
            'rag_excerpts': len(research), 'schema_version': VERSION, 'timeout_seconds': settings.kexaone_timeout})
        save('status.json', {'state': 'initial_interpretation', 'calls': counts})
        parsed = initial_person.interpret(payload); save('before_claim_check.json', parsed)
        save('status.json', {'state': 'claim_check', 'calls': counts})
        checked = claim_check.verify(parsed, payload); save('after_claim_check.json', checked)
        persona.prepared_initial = {'version': VERSION, 'fingerprint': fingerprint(persona),
            'core': checked['core'], 'scope': checked['context'], 'audit': checked.get('audit', {}),
            'retrieval_audit': payload['retrieval_audit'], 'prepared_at': datetime.now(timezone.utc).isoformat(),
            'profile_snapshot_at': persona.initial_preparation_status['updated_at'], 'persona_version': persona.version}
        persona.initial_preparation_status = dict(persona.initial_preparation_status, state='ready', version=VERSION)
        save('persona_prepared.json', persona.model_dump(mode='json'))
        save('personal_source_prepared.json', mind_policy.source(persona))
        save('status.json', {'state': 'prepared_for_source_review_not_quality_verdict', 'calls': counts,
            'transport_failures': failures, 'refused_before_submission': refused,
            'not_deployed': True, 'synthetic_guardian': True,
            'note': 'uses real initial interpretation and claim check; axes scoring not included in original capture'})
    except BaseException as e:
        save('status.json', {'state': 'needs_diagnosis', 'error_type': type(e).__name__,
                            'calls': counts, 'transport_failures': failures, 'refused_before_submission': refused}); raise


if __name__ == '__main__': main()
