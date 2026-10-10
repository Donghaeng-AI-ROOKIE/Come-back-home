"""Re-run the product mind-policy preparation with RECORDED K responses.

No model call: mind_preparation.logged_json_request is replaced by a lookup of
the saved draft/review responses for the same person. The request body built
by the backend on PYTHONPATH is compared with the recorded request body, so a
mismatch (different prompt/model/source) is reported instead of hidden.

Usage: python reprepare.py <experiment_root> <out_dir> <label>
Writes <out_dir>/<label>/<pid>.json for every person whose saved D policy was
produced with K calls, plus <out_dir>/<label>/summary.json.
"""
import json, os, socket, sys, glob
from pathlib import Path


def _blocked(*a, **k):
    raise RuntimeError('network disabled in offline re-preparation')


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked

R = Path(sys.argv[1]); OUT = Path(sys.argv[2]) / sys.argv[3]; OUT.mkdir(parents=True, exist_ok=True)
people = sorted(p.name for p in (R / 'output/people').iterdir() if p.is_dir())


def recorded_calls(pid, audit):
    ids = {a.get('request_id') for a in audit}
    calls = {}
    for f in glob.glob(str(R / 'output/public_outputs' / pid / 'K_EXAONE-*.json')):
        d = json.loads(Path(f).read_text())
        if d.get('request_id') in ids and d.get('role', '').startswith('mind_policy_'):
            calls[d['role']] = d
    return calls


first = None
for pid in people:
    prepared = json.loads((R / 'output/people' / pid / 'prepared.json').read_text())
    spec = prepared['arms'].get('D_full_prepared')
    if not spec:
        continue
    pm = spec['persona'].get('prepared_mind') or {}
    calls = recorded_calls(pid, pm.get('audit') or [])
    if calls:
        first = first or calls
model = next(iter(first.values()))['requested_model']
os.environ.update(PERSIST_STORAGE='false', PUSH_ENABLED='false', PRIVACY_SCHEDULER_ENABLED='false',
                  POA_REFRESH_ENABLED='false', EXAONE_WARMUP_ENABLED='false',
                  MIND_POLICY_CONTRACT='guarded_core', MIND_POLICY_DEPLOYMENT='staging',
                  KEXAONE_MODEL=model, KEXAONE_BASE_URL='http://offline.invalid/v1', KEXAONE_API_KEY='offline',
                  RESEARCH_USAGE_LEDGER_PATH=str(OUT / 'no_calls.ledger.jsonl'))
import app
from app.schemas.persona import Persona
from app.llm import mind_policy
from app.llm import mind_policy_guarded_core as guarded
from app.phase0 import mind_preparation

summary = []
for pid in people:
    prepared = json.loads((R / 'output/people' / pid / 'prepared.json').read_text())
    spec = prepared['arms'].get('D_full_prepared')
    if not spec:
        continue
    persona = Persona.model_validate(spec['persona'])
    pm = persona.prepared_mind or {}
    calls = recorded_calls(pid, pm.get('audit') or [])
    if not calls:
        summary.append({'person_id': pid, 'status': 'no_recorded_mind_policy_calls'})
        continue
    matches = []

    def fake(url, body, **kw):
        rec = calls[kw['role']]
        matches.append({'role': kw['role'], 'request_body_equal': body == rec['request_body']})
        # Public records store choices as {finish_reason, content}; restore the API shape.
        choices = [c if 'message' in c else {'finish_reason': c.get('finish_reason'),
                   'message': {'content': c.get('content', '')}} for c in rec['choices']]
        return {'id': rec['request_id'], 'usage': rec.get('usage'), 'choices': choices}

    mind_preparation.logged_json_request = fake
    source = mind_policy.source(persona)
    try:
        policy, audit = mind_preparation.interpret(source, 'offline-reprepare:' + pid, candidate=guarded)
        error = None
    except Exception as e:  # recorded as a failure, never replaced
        policy, audit, error = None, [], type(e).__name__ + ': ' + str(e)[:300]
    stored = pm.get('policy')
    row = {'person_id': pid, 'backend': app.__file__, 'roles_replayed': [m['role'] for m in matches],
           'request_bodies_equal': all(m['request_body_equal'] for m in matches) and bool(matches),
           'stored_revision': pm.get('revision'), 'current_revision': mind_policy.revision(persona),
           'revision_unchanged': pm.get('revision') == mind_policy.revision(persona),
           'error': error, 'policy_equal_to_stored': policy == stored,
           'scope_restored': [a.get('scope_restored_from_draft') for a in audit if a.get('scope_restored_from_draft')],
           'policy': policy, 'stored_policy': stored, 'audit': audit}
    (OUT / f'{pid}.json').write_text(json.dumps(row, ensure_ascii=False, indent=1) + '\n')
    summary.append({k: v for k, v in row.items() if k not in ('policy', 'stored_policy', 'audit')})
(OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')
print(json.dumps([{k: s.get(k) for k in ('person_id', 'roles_replayed', 'request_bodies_equal', 'revision_unchanged',
                                          'policy_equal_to_stored', 'scope_restored', 'error', 'status')}
                  for s in summary], ensure_ascii=False))
