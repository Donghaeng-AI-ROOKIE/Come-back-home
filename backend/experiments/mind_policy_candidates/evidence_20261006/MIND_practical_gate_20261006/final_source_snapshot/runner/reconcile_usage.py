"""Aggregate recorded usage without treating missing provider usage as zero."""
from collections import Counter
import json
from pathlib import Path

D=Path(__file__).resolve().parent
ledger=D.parents[1]/'연구지원_사용기록/usage_events.jsonl'
rows=[json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
rows=list({r['event_id']:r for r in rows if r.get('run_id')==D.name}.values())
starts={r['attempt_id']:r for r in rows if r['event_type']=='api_attempt_started'}
ends={r['attempt_id']:r for r in rows if r['event_type']=='api_attempt_finished'}
out={'run_id':D.name,'approved_total':128,'approved_development':64,'approved_evaluation':64,
     'reserved_attempts':len(starts),'finished_attempts':len(ends),
     'pending_attempts':sorted(set(starts)-set(ends)),
     'started_by_role':dict(Counter(r['role'] for r in starts.values())),
     'outcomes':dict(Counter(r.get('outcome') for r in ends.values())),
     'http_status':dict(Counter(str(r.get('http_status')) for r in ends.values())),
     'finish_reasons':dict(Counter(str(r.get('finish_reason')) for r in ends.values())),
     'known_usage_subtotals':{k:sum((r.get('usage') or {}).get(k,0) for r in ends.values())
                            for k in ('prompt_tokens','completion_tokens','total_tokens')},
     'responses_with_usage':sum(bool(r.get('usage')) for r in ends.values()),
     'responses_without_usage':sum(not bool(r.get('usage')) for r in ends.values()),
     'missing_usage_is_zero':False,'unit_price':None,'actual_cost':None,
     'support_round':None,'gpu_billed_hours':None,'automatic_retries':False,
     'new_training':False,'new_SAR':0,'new_Midm':0,'new_RAG_queries':0,
     'new_embeddings':0,'new_maps':0,'deployed':False}
(D/'usage_summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
