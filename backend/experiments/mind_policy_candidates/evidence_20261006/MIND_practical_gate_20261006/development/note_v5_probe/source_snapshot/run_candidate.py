"""Dry-run by default. Bounded note-level calls after explicit scope approval.

No automatic resubmission on failure; durable results survive transport loss.
The evaluation phase requires a frozen candidate that passed development.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

D = Path(__file__).resolve().parent
B = D.parents[1] / '개발/cbh-simulation-integration-20261004/backend'
sys.path.insert(0, str(B))
from experiments.mind_policy_candidates import note_policy as candidate, note_policy_eval as evaluator
from app.llm import mind_policy
from app.llm.initial_behavior import decode_json_content
import transport


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def code_hashes():
    files = [Path(x.__file__) for x in (candidate, evaluator, mind_policy)] + [Path(__file__), D/'transport.py']
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def build(rows, name, thinking, repetitions):
    people = {}
    for row in rows:
        pid = row['person_id']
        if pid in people and people[pid] != row['personal']:
            raise ValueError('different source within one person')
        people[pid] = row['personal']
    jobs = []
    for pid, personal in sorted(people.items()):
        for rep in range(1, repetitions+1):
            for note in personal['notes']:
                body = candidate.request(personal, note['id'], transport.model, thinking=thinking)
                jobs.append({'job':f'{name}_{pid}_{note["id"]}_{rep}', 'person_id':pid,
                             'rep':rep, 'note_id':note['id'], 'personal':personal, 'body':body})
    return jobs


def starts():
    ledger = D.parents[1]/'연구지원_사용기록/usage_events.jsonl'
    if not ledger.exists():
        return []
    return [x for line in ledger.read_text().splitlines() if line.strip()
            for x in [json.loads(line)]
            if x.get('run_id') == D.name and x.get('event_type') == 'api_attempt_started']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['development','evaluation'], default='development')
    parser.add_argument('--name', default='note_v1_off')
    parser.add_argument('--thinking', choices=['on','off'], default='off')
    parser.add_argument('--repetitions', type=int, choices=[1,2], default=2)
    parser.add_argument('--probe-note', default=None)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.name.replace('_','').isalnum():
        raise ValueError('invalid candidate name')
    manifest = json.loads((D/'manifest.json').read_text())
    input_path = D/(args.phase+'_inputs.json')
    assert hashlib.sha256(input_path.read_bytes()).hexdigest() == manifest['input_sha256'][input_path.name]
    rows = json.loads(input_path.read_text())
    jobs = build(rows, args.name, args.thinking == 'on', args.repetitions)
    if args.probe_note is not None:
        if args.phase != 'development':
            raise ValueError('evaluation cannot be a probe')
        jobs = [j for j in jobs if j['note_id'] == args.probe_note][:1]
        if not jobs:
            raise ValueError('unknown probe note')
    evidence = {'phase': args.phase, 'candidate': args.name, 'thinking': args.thinking,
                'calls':len(jobs), 'scene_decisions':len(rows)*args.repetitions,
                'input_sha256':manifest['input_sha256'][input_path.name],
                'code_sha256':code_hashes(), 'repetitions':args.repetitions,
                'max_request_bytes':max(len(json.dumps(j['body'],ensure_ascii=False).encode()) for j in jobs),
                'automatic_retries':False, 'probe_note':args.probe_note}
    print(json.dumps({k:v for k,v in evidence.items() if k!='code_sha256'}, ensure_ascii=False), flush=True)
    if not args.execute:
        print('DRY RUN: no SSH, API, GPU, map or embedding calls', flush=True)
        return
    approval = json.loads((D/'authorization.json').read_text())
    if approval.get('status') != 'approved' or not approval.get('human_approval'):
        raise SystemExit('new development/evaluation allocation not approved; no external call')

    # Keep phase reservation and all calls in one local runner. Transport still
    # atomically reserves every attempt in the common ledger before submission.
    with (D/'runner.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        used = starts()
        role = 'mind_state_alignment_'+args.phase
        if len(used)+len(jobs)>128 or sum(x.get('role')==role for x in used)+len(jobs)>64:
            raise SystemExit('approved total or phase budget exceeded')
        if args.phase == 'evaluation':
            selected = json.loads((D/'selected_candidate.json').read_text())
            if (selected['candidate'] != args.name or selected['thinking'] != args.thinking
                or selected['code_sha256'] != evidence['code_sha256'] or args.repetitions != 2):
                raise SystemExit('evaluation candidate differs from frozen selection')
            if not selected['development_gate']['advance_to_integration']:
                raise SystemExit('development gate did not pass')
        outdir = D/args.phase/args.name
        outdir.mkdir(parents=True, exist_ok=False)
        write(outdir/'manifest.json', evidence)
        snapshot = outdir/'source_snapshot'; snapshot.mkdir()
        for source in evidence['code_sha256']:
            (snapshot/Path(source).name).write_bytes(Path(source).read_bytes())
        transport.args.stage = args.phase
        stop = threading.Event()

        def one(job):
            folder = outdir/job['person_id']/str(job['rep'])/job['note_id']
            result = {k:job[k] for k in ('job','person_id','rep','note_id')}
            result.update(output=None, valid=False, error_type=None, submitted=False)
            if stop.is_set():
                result['error_type'] = 'not_submitted_after_transport_failure'
                write(folder/'result.json', result)
                return result
            write(folder/'request.json', job['body'])
            try:
                result['submitted'] = True
                response = transport.invoke(job['body'], job['job'])
                choice = response['choices'][0]
                content = choice['message'].get('content') or ''
                if '</think>' in content:
                    content = content.rsplit('</think>', 1)[-1].strip()
                if '<think>' in content:
                    content = '[no separable final output]'
                write(folder/'response.public.json', {'final_content':content,
                      'finish_reason':choice.get('finish_reason'),'usage':response.get('usage')})
                if choice.get('finish_reason') != 'stop':
                    raise ValueError('incomplete_output')
                value = decode_json_content(content)
                candidate.compile_note(value, job['personal'], job['note_id'])
                result.update(output=value, valid=True)
            except Exception as exc:
                result['error_type'] = type(exc).__name__
                # Missing transport result has an unknown submission outcome.
                # Stop queue launch, preserve markers, investigate; never retry.
                if (type(exc).__name__ == 'TimeoutExpired'
                    or str(exc) == 'K_bridge_transport_failure'
                    or str(exc).startswith('K_API_')):
                    stop.set()
            write(folder/'result.json', result)
            print({k:result[k] for k in ('job','valid','error_type','submitted')}, flush=True)
            return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            outputs = list(pool.map(one, jobs))
        scored = []
        people = {r['person_id']:r['personal'] for r in rows}
        for pid, personal in people.items():
            for rep in range(1,args.repetitions+1):
                group = [r for r in outputs if r['person_id']==pid and r['rep']==rep]
                try:
                    if not all(r['valid'] for r in group):
                        raise ValueError('one_or_more_notes_failed')
                    policy = candidate.merge({r['note_id']:r['output'] for r in group}, personal)
                    write(outdir/pid/str(rep)/'compiled_policy.json', policy.model_dump())
                    problem = None
                except Exception as exc:
                    policy, problem = None, type(exc).__name__
                for row in [r for r in rows if r['person_id']==pid]:
                    result = {'id':row['id'],'person_id':pid,'rep':rep,
                              'label':','.join(row['expected_commands']) or 'unknown',
                              'pass':False,'decision':None,'error_type':problem}
                    if policy is not None:
                        try:
                            result['decision'] = evaluator.decide(policy, personal, row['scene'])
                            result['pass'] = evaluator.score(result['decision'],row['expected_commands'])
                        except Exception as exc:
                            result['error_type'] = type(exc).__name__
                    scored.append(result)
        summary = {'manifest':evidence, 'model_outputs':outputs, 'results':scored,
                   'gate':evaluator.gate(scored,[r['id'] for r in rows],list(range(1,args.repetitions+1))),
                   'clinical_patients':0,'independent_human_raters':0}
        if args.repetitions != 2 or args.probe_note is not None:
            summary['gate']['advance_to_integration'] = False
            summary['gate']['reason'] = 'development diagnostics only; complete both predeclared repetitions'
        write(outdir/'summary.json', summary)
        print(json.dumps(summary['gate'],ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
