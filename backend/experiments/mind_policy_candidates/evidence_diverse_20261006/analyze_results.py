"""Read-only replay of all saved public outputs, including failures.

Writes an explicitly partial report until all128 calls finish. No model calls.
"""
import json, statistics, unicodedata
from collections import Counter
from pathlib import Path
from run_comparison import D, candidate, evaluator, initial_behavior, score, write, events, digest, sources

FAMILY={'environment':'환경의 복합 조건','physical_rest':'보행 한계·휴식','waiting':'기다림과 해제','destination':'목적지 발언·실제 출발','external_state':'비·어둠 등 외부 상태','source_fidelity':'정정·타인·부정 답변','time_context':'시각·보행 시간','multiple_behaviors':'서로 다른 행동의 결합'}

def main():
 profiles=json.loads((D/'profiles.json').read_text());people={r['person_id']:r for r in profiles}
 scenes=json.loads((D/'scenes.json').read_text());results=[];outputs=[]
 manifest=json.loads((D/'manifest.json').read_text())
 normalize=lambda d:{unicodedata.normalize('NFC',str(Path(k).resolve())):v for k,v in d.items()}
 assert normalize(sources())==normalize(manifest['source_sha256'])
 for path in sorted((D/'comparison').glob('*/*/*/result.json')):
  r=json.loads(path.read_text());folder=path.parent;public_path=folder/'response.public.json'
  public=json.loads(public_path.read_text()) if public_path.exists() else {}
  detail=None;policy=None
  if r['valid']:
   policy=candidate.compile_note(r['output'],people[r['person_id']]['personal'],'ALL',whole_person=True)
   assert policy.model_dump()==json.loads((folder/'compiled_policy.json').read_text())
  else:
   if public.get('finish_reason') not in (None,'stop'):detail='output_incomplete_'+public['finish_reason']
   elif public.get('final_content'):
    try:
     value=initial_behavior.decode_json_content(public['final_content'])
     candidate.compile_note(value,people[r['person_id']]['personal'],'ALL',whole_person=True)
     detail='unexpected_replay_valid'
    except Exception as e:detail=type(e).__name__+': '+str(e)[:240]
   else:detail=r['error_type'] or 'no_public_final'
  outputs.append({**r,'failure_detail':detail,'public_path':str(public_path.relative_to(D)) if public_path.exists() else None,'finish_reason':public.get('finish_reason'),'usage':public.get('usage')})
  for s in [s for s in scenes if s['person_id']==r['person_id']]:
   d=evaluator.decide(policy,people[r['person_id']]['personal'],s['scene']) if policy else None
   results.append({**s,'arm':r['arm'],'rep':r['rep'],'decision':d,'pass':score(d,s) if d else False,'output_valid':r['valid'],'failure_detail':detail})
 arms={}
 for a in ('on','off'):
  rs=[r for r in results if r['arm']==a];outs=[r for r in outputs if r['arm']==a]
  arms[a]={'decisions_completed':len(rs),'passed':sum(r['pass'] for r in rs),'planned_decisions':256,'outputs_completed':len(outs),'valid_outputs':sum(r['valid'] for r in outs),'planned_outputs':64,
   'positive_passed':sum(r['pass'] for r in rs if r['expected_status']=='supported'),'positive_completed':sum(r['expected_status']=='supported' for r in rs),
   'families':{f:{'passed':sum(r['pass'] for r in rs if r['family']==f),'completed':sum(r['family']==f for r in rs),'planned':32} for f in FAMILY},
   'output_failures':dict(Counter(r['failure_detail'] for r in outs if not r['valid'])),
   'people':{p:{'passed':sum(r['pass'] for r in rs if r['person_id']==p),'completed':sum(r['person_id']==p for r in rs),'planned':8} for p in people}}
 complete=len(outputs)==128 and all(r['submitted'] for r in outputs)
 def failure_kind(r):
  if r['pass']:return 'pass'
  if not r['output_valid']:return 'output_failure'
  actual=r['decision']['status'];expected=r['expected_status']
  if expected=='supported':return 'missed_required_action' if actual!='supported' else 'wrong_action'
  if expected=='unknown':return 'uncertainty_not_preserved'
  return 'unsupported_personal_action' if actual=='supported' else 'invented_uncertainty'
 for r in results:r['failure_kind']=failure_kind(r)
 for a in arms:
  rs=[r for r in results if r['arm']==a]
  arms[a]['failure_kinds']=dict(Counter(r['failure_kind'] for r in rs if not r['pass']))
  arms[a]['fully_correct_people']=sum(v['completed']==8 and v['passed']==8 for v in arms[a]['people'].values())
  pairs=[]
  for pid in people:
   aa=sorted([r for r in rs if r['person_id']==pid and r['rep']==1],key=lambda r:r['id'])
   bb=sorted([r for r in rs if r['person_id']==pid and r['rep']==2],key=lambda r:r['id'])
   if len(aa)==len(bb)==4:
    pairs.append({'person_id':pid,'both_valid':all(r['output_valid'] for r in aa+bb),
      'all_decisions_same':all(r['output_valid'] for r in aa+bb) and all(all(x['decision'][k]==y['decision'][k] for k in ('status','commands','possible_commands')) for x,y in zip(aa,bb))})
  arms[a]['repetition_pairs']=pairs
 replay={'complete':complete,'outputs_completed':len(outputs),'planned_outputs':128,'arms':arms,'results':results,'outputs':outputs}
 write(D/'replayed_results.json',replay)
 if (D/'comparison/summary.json').exists():
  original=json.loads((D/'comparison/summary.json').read_text())
  key=lambda r:(r['id'],r['arm'],r['rep'])
  assert {key(r):(r['decision'],r['pass']) for r in original['results']}=={key(r):(r['decision'],r['pass']) for r in results}
  write(D/'verification_summary.json',{'saved_decisions_reproduced':len(results),'exact_match':True,'model_calls':0,'source_sha256':sources()})
 ledger=list({r['event_id']:r for r in events()}.values())
 starts={r['attempt_id']:r for r in ledger if r['event_type']=='api_attempt_started'}
 ends={r['attempt_id']:r for r in ledger if r['event_type']=='api_attempt_finished'}
 usage={'run_id':D.name,'comparison_limit':128,'conditional_evaluation_limit':64,'total_limit':192,
  'started':len(starts),'finished':len(ends),'pending':len(set(starts)-set(ends)),
  'finish_reasons':dict(Counter(r.get('finish_reason') for r in ends.values())),
  'known_token_subtotals':{k:sum((r.get('usage') or {}).get(k) or 0 for r in ends.values()) for k in ('prompt_tokens','completion_tokens','total_tokens')},
  'missing_usage_responses':sum(not r.get('usage') for r in ends.values()),'unit_price':None,'actual_cost':None,'support_round':None,
  'new_map_calls':0,'new_RAG_calls':0,'new_GPU_training':False,'deployment':False,
  'by_arm':{a:{'completed':len(rs),'median_seconds':statistics.median([r['duration_seconds'] for r in rs]) if rs else None,
     'known_token_subtotals':{k:sum((r.get('usage') or {}).get(k) or 0 for r in rs) for k in ('prompt_tokens','completion_tokens','total_tokens')}}
    for a in ('on','off') for rs in [[r for r in ends.values() if '_'+a+'_' in r.get('logical_request_id','')]]}}
 write(D/'usage_summary.json',usage)
 spatial=[json.loads(p.read_text()) for p in (D/'spatial').glob('P*.json')] if (D/'spatial').exists() else []
 valid=[r for r in spatial if r['status']=='executed']
 for r in valid:
  scores=[s for s in results if (s['person_id'],s['arm'],s['rep'])==(r['person_id'],r['arm'],r['rep'])]
  r['interpretation_passed_scenes']=sum(s['pass'] for s in scores);r['interpretation_total_scenes']=len(scores)
 spatial_summary={'planned_slots':384,'saved_slots':len(spatial),'status_counts':dict(Counter(r['status'] for r in spatial)),
  'engineering':{k:{'passed':sum(r['engineering'][k] is True for r in valid),'total':sum(r['engineering'][k] is not None for r in valid)} for k in ('mass_conserved','clock_accounting','distance_matches_walk_time','full_horizon_resolved','checkpoint_equal')},
  'by_person_arm':{pid+'_'+a:{'executed':len(rs),'all_authored_checks_passed':sum(all(r['authored_behavior_checks'].values()) for r in rs),'checks':{k:{'passed':sum(r['authored_behavior_checks'].get(k) is True for r in rs),'total':sum(k in r['authored_behavior_checks'] for r in rs)} for k in sorted({k for r in rs for k in r['authored_behavior_checks']})}} for pid in json.loads((D/'spatial_plan.json').read_text())['representatives'] for a in ('on','off') for rs in [[r for r in valid if r['person_id']==pid and r['arm']==a]]},
  'clinical_accuracy_measured':False,'new_model_calls':0}
 write(D/'spatial_summary.json',spatial_summary)
 title='최종 비교 결과' if complete else '진행 중인 중간 집계'
 lines=['# K-EXAONE 마음모델 확대 비교', '',f'**{title}: 모델 응답 {len(outputs)}/128, 공간 검사 {len(spatial)}/384칸.**','',
  '## 왜 이번 실험을 했나','',
  '직전 8장면×2응답의 작은 비교만으로, 새 보호자 표현과 여러 환경에서도 그 사람의 행동을 보존한다고 판단하기 어려웠다. 최신 후보를 고정하고 새 합성 32명·8개 행동군으로 늘려 Thinking 켬/끔을 같은 조건에서 비교했다. 공간은 기존 고양 KINTEX OSMnx 지도 안의 6개 출발 구역을 사용했다.','',
  '## 무엇을 검증했나','',
  '보호자의 원문을 K-EXAONE이 조건과 행동으로 해석하고, 코드가 현재 관측과 대조해 행동을 선택하는 부분이다. 시뮬레이션 단계에서는 선택된 행동이 실제 도로 보행·대기·휴식으로 이어지는지 따로 검사한다. 전체 온보딩 파이프라인을 새로 호출하거나 실제 실종 위치 정답과 비교한 실험은 아니다.','',
  '```mermaid','flowchart LR','  A["합성 보호자 원문 32명"] --> B["K-EXAONE 켬/끔 · 각 2응답"]','  B --> C["완성 여부·고정 계약 검사"]','  C --> D["미리 정한 장면의 기대 행동과 대조"]','  C --> E["사전 지정 8명의 실행 가능한 정책"]','  E --> F["KINTEX 6구역 · 1·2·4·6시간 보행"]','  C --> G["실패 출력도 전체 모수에 포함"]','```','',
  '32명×4장면×2응답=설정별 256판정이다. Thinking 켬/끔을 합하면 512판정이며, 서로 다른 환자 512명을 검증했다는 뜻은 아니다. 모든 사례와 기대 행동은 연구자가 작성한 합성 자료다. P02 한 명은 미리 작성한 환경 규칙을 기존 컴파일러로 재사용하는 조건이다. 이 사람의 결과를 K가 원문에서 새로 추출한 성능으로 해석하지 않는다.','',
  '`baseline`은 개인 반응을 확정하지 않고 기존 이동 prior에 맡긴다는 뜻이다. 멈춤을 뜻하지 않는다. 따라서 보호자가 관찰한 `walk`를 누락하고 baseline으로 남긴 경우는 이 검사에서 근거 보존 실패지만, 실제 보행자가 걷지 않았다는 뜻은 아니다. `unknown`은 가능한 행동이 둘 이상이며, 그 가능 행동까지 맞아야 통과한다. 실제 보행 결과는 공간 검사와 함께 읽어야 한다.','',
  '## 개인 행동 해석 결과','',
  '| 항목 | Thinking 켬 | Thinking 끔 |','|---|---:|---:|',
  f"| 응답 계약 통과 / 완료 응답 | {arms['on']['valid_outputs']}/{arms['on']['outputs_completed']} | {arms['off']['valid_outputs']}/{arms['off']['outputs_completed']} |",
  f"| 행동 일치 / 완료 판정 | {arms['on']['passed']}/{arms['on']['decisions_completed']} | {arms['off']['passed']}/{arms['off']['decisions_completed']} |",
  f"| 실제 행동을 요구한 장면 일치 | {arms['on']['positive_passed']}/{arms['on']['positive_completed']} | {arms['off']['positive_passed']}/{arms['off']['positive_completed']} |",'',
  '전체 231/256, 행동군별 26/32, 실제 반응 장면 76/84, 유효 응답 61/64를 모두 충족해야 다음 별도 평가로 넘어간다. 실행 전에 정한 내부 단계 기준이며 임상 배포 기준은 아니다. 실패 출력도 행동 판정의 실패에 포함한다.','',
  '| 행동군 | Thinking 켬 | Thinking 끔 |','|---|---:|---:|']
 for f,label in FAMILY.items():lines.append(f"| {label} | {arms['on']['families'][f]['passed']}/{arms['on']['families'][f]['completed']} | {arms['off']['families'][f]['passed']}/{arms['off']['families'][f]['completed']} |")
 lines+=['','## 실제 출력과 예상 행동','',
  '아래는 사전에 고정한 인물의 첫 번째 응답이다. 공개 최종 출력만 사용하며 내부 Thinking 원문은 포함하지 않는다. 원문·모델 해석·장면별 결과를 함께 보아, JSON 형식 성공을 의미 해석 성공으로 오해하지 않도록 했다.','']
 for pid in ('P05','P09','P14','P25','P29'):
  lines+=['### '+pid+' · '+FAMILY[people[pid]['family']],'']
  lines += ['> '+n['text'].replace('\n','\n> ')+'\n' for n in people[pid]['personal']['notes'][1:]]
  for a in ('on','off'):
   r=next((r for r in outputs if r['person_id']==pid and r['arm']==a and r['rep']==1),None)
   lines+=['Thinking '+('켬' if a=='on' else '끔')+':']
   if r is None:lines+=['아직 응답 완료 전.',''];continue
   if not r['valid']:lines+=['출력 실패: `'+str(r['failure_detail'])+'`',''];continue
   lines+=['```json',json.dumps(r['output'],ensure_ascii=False,indent=2),'```','',
     '| 장면 | 기대 행동 | 선택 행동 | 일치 |','|---|---|---|---|']
   for s in [s for s in results if s['person_id']==pid and s['arm']==a and s['rep']==1]:
    action=', '.join(s['decision']['commands']) or '미확정: '+', '.join(s['decision']['possible_commands'])
    expected=', '.join(s['expected_commands']) or '미확정: '+', '.join(s['expected_possible_commands'] or [])
    lines.append(f"| {s['rationale']} | {expected} | {action} | {'일치' if s['pass'] else '불일치'} |")
   lines+=['']
 lines+=['## KINTEX에서 행동이 보행으로 이어졌나','',
  '환경·휴식·대기·목적지·비·원문 정정·시각·복합 반응의 8명, 설정 2개, 응답 2개, 출발 구역 6개, 보행 시드 2개로 384칸을 고정했다. 각 집단은 100보행자이며 1·2·4·6시간을 끊지 않고 이어 계산한다. 형식 오류는 실행 불가로 남기고, 의미 오류가 있는 유효 정책도 그대로 진단한다.','',
  '도로는 실제 KINTEX OSMnx 캐시다. 시설 위치, 소음·혼잡·비·가족 도착은 명시적인 합성 관측이다. 일반 치매 persona와 같은 초기 이동 prior를 쓰므로, 새 온보딩 해석까지 포함한 전체 파이프라인 성능을 뜻하지 않는다.','',
  '| 공학 검사 | 통과 / 실시 |','|---|---:|']
 for k,label in [('mass_conserved','확률 질량 보존'),('clock_accounting','보행·휴식·대기 시간 합계'),('distance_matches_walk_time','보행 시간과 누적 거리'),('full_horizon_resolved','6시간 내 지도 범위·막힘 없이 계산'),('checkpoint_equal','저장 후 재개와 연속 실행 일치')]:
  r=spatial_summary['engineering'][k];lines.append(f"| {label} | {r['passed']}/{r['total']} |")
 lines+=['','지도 색이 시간마다 달라지는 것만으로 성공 판정하지 않는다. 계속 기다리는 조건이면 같은 위치가 정상일 수 있다. 반대로 조건이 풀렸는데 계속 멈추거나 원문에 없는 이동을 만들면 문제다.','',
  '## 사용량과 재현 자료','',
  f"K-EXAONE 시작 {usage['started']}회, 완료 {usage['finished']}회. 제공된 usage의 토큰 합계 {usage['known_token_subtotals']['total_tokens']:,}. 단가·실청구액·지원 차수는 미확인이다. 새 SAR·Mi:dm·RAG·임베딩·지도·GPU 학습 호출은 없다.",'',
  '- `profiles.json`: 새 합성 32명과 원문.','- `scenes.json`: 고정된 128장면과 기대 행동. 모델에 전달하지 않음.',
  '- `comparison/`: 각 요청·공개 최종 출력·실행 정책.','- `replayed_results.json`: 실패를 포함한 전체 재현 판정.',
  '- `spatial_plan.json`, `sites.json`, `spatial/`: 고정 관측·지도 출발점·시간별 경로와 점검 결과.',
  '- `usage_summary.json`: 비용 원장 집계.','',
  '## 결과 해석의 한계','',
  '이번 결과는 주어진 개인 원문과 합성 관측에서 기대한 행동을 보존했는지에 관한 근거다. 실제 치매 어르신의 이동·심리를 맞혔다는 비율, 발견율, 실제 수색 안전성을 입증하는 수치가 아니다. 독립 전문가 채점과 실제 비식별 사례의 검증은 이번 자료에 없다.']
 (D/'확대비교_결과보고서.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps({'complete':complete,'outputs':len(outputs),'spatial_saved':len(spatial),'arms':{a:{k:arms[a][k] for k in ('passed','decisions_completed','valid_outputs','outputs_completed')} for a in arms}},ensure_ascii=False))
if __name__=='__main__':main()
