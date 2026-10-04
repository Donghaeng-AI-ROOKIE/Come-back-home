"""Closed-loop research run. Recorded onboarding, fresh decisions, real KINTEX roads."""
import argparse, copy, json, os, sys, time
from datetime import datetime,timedelta
from pathlib import Path
from bootstrap import D,FINALS,BACK,MODEL,candidate,sha
from app.geo.roadnet import OSMnxNetwork
from app.geo.h3grid import haversine_km
from app.phase0.person_preparation import fingerprint
from app.llm import mind_handoff
from app.schemas.persona import Persona
from app.schemas.prediction import PriorParams
from app.schemas.environment import EnvironmentObservation
from experiments.mind_upgrade.runtime import WalkingSession,RuntimePolicy
from experiments.mind_closed_loop.bridge import MeteredDecisionBridge,probability_snapshot

START=datetime(2026,10,5,8)
HOURS=(60,120,240,360)
MAP=FINALS/'지도캐시/KINTEX_20260928/kintex_walk.graphml'
EXTRA='''\ncurrent_scene.locomotion은 이번 시뮬레이션에서 실제로 누적한 보행·휴식·대기 시간이다. continuous_walking_minutes는 마지막 정지 이후 실제 연속 보행 시간이며 실종 경과 시간으로 대체하지 않는다. 초기 누적 기록이 없는 과거 이동은 추측하지 않는다. 피로 수치는 임상 증상이나 환자의 발언이 아니다. 관측에 명시된 기간과 범위를 벗어난 사실을 유지하지 않는다. 기억한 목적지와 현재 회피는 양립할 수 있다. 보호자 설명의 장소 한정·조건 한정을 보존한다. 지금 이 사람이 선택할 행동을 읽으며, 보호자의 부탁을 당사자의 행동으로 바꾸지 않는다. 명령과 공개 설명은 같은 현재 행동을 가리킨다.'''


def payload(c):
    body=candidate.payload(c,'separate_motion_and_goal',MODEL)
    data=json.loads(body['messages'][1]['content'])
    data['current_scene']['locomotion']=c['locomotion']
    data['current_scene']['observation_provenance']=c.get('observation_provenance')
    body['messages'][1]['content']=json.dumps(data,ensure_ascii=False)
    body['messages'][0]['content']+=EXTRA
    if len(json.dumps(body,ensure_ascii=False).encode())>32768:
        raise ValueError('input_byte_limit')
    return body


def decode(raw,c):
    if raw.get('finish_reason')=='length':raise ValueError('output_limit')
    value=json.loads(raw['content'])
    d=candidate.validate(value,c)
    return None if d['status']=='insufficient_information' else {k:v for k,v in d.items() if k!='status'}


def load():
    meta=json.loads(MAP.with_suffix('.json').read_text());assert sha(MAP)==meta['sha256']
    net=OSMnxNetwork.from_graphml(MAP)
    rows=[json.loads(x) for x in (D.parent/'MIND_release_gate_20260930/frontend.jsonl').read_text().splitlines()]
    selected=rows[::2];assert len(selected)==8
    people=[]
    for row in selected:
        path=Path(row['persona_source']);p=Persona.model_validate_json(path.read_text())
        assert fingerprint(p)==p.prepared_initial['fingerprint'],row['id']
        source=path.parent.parent/'outputs'/path.name
        prior=PriorParams.model_validate(json.loads(source.read_text())['prior'])
        people.append((row,p,prior,path,source))
    # Authored test facilities only. They are NOT real OSM POIs or patient locations.
    locations={a.label:a.location for a in people[0][1].attraction_points}
    features={'market':locations['푸른시장'],'park':locations['다온공원']}
    net.node_env={n:{f+'_m':haversine_km(net.node_location(n),point)*1000
                    for f,point in features.items()} for n in net.graph.nodes}
    return net,meta,people,locations


def session(net,item,locations,request):
    row,p,prior,*_=item
    market=locations['푸른시장']
    observations=[EnvironmentObservation(feature='market',location=market,radius_m=250,
        valid_from=START+timedelta(minutes=a),valid_until=START+timedelta(minutes=b),
        noisy=noisy,crowded=crowded,source='synthetic_scenario')
        for a,b,noisy,crowded in [(0,60,True,True),(60,120,False,False),(120,240,True,False),(240,360,False,True)]]
    def context(*args,**kwargs):
        c=mind_handoff.context_for(*args,**kwargs)
        # Explicit author-provided initial sighting, never map-derived visibility.
        if c['state']['elapsed_minutes']==0 and row['id'].startswith('E'):
            c['environment']['observed_place_labels']=['푸른시장']
        c['observation_provenance']='synthetic spatial observations on real cached roads; fake facility locations'
        return c
    bridge=MeteredDecisionBridge(payload,decode,request,max_calls=12)
    s=WalkingSession(net,p,prior,market if row['id'].startswith('E') else p.home,START,
        bridge,policy=RuntimePolicy(5,30),case_id=row['id'],observations=observations,seed=104,
        context_builder=context,decision_validator=mind_handoff.validate_decision,allow_abstention=True)
    s.action=row['context']['state']['current_action']
    s.travel_action=row['context']['execution']['previous_travel_action']
    s.avoid_feature=row['context']['execution']['previous_avoid_feature']
    s.target=row['context']['state']['target_label']
    s.g.F=.1;s.g.C=.2
    for event in row['context']['state']['recent_events']:
        s.history.append(dict(event,elapsed_minutes=0.,provenance='authored initial probe observation'))
    return s,bridge


def prepare():
    net,meta,people,locations=load();files={};inputs=[]
    for item in people:
        row,p,prior,ps,qs=item
        s,_=session(net,item,locations,lambda b: (_ for _ in ()).throw(RuntimeError('no live calls in preparation')))
        c=s.context('initial');body=payload(c)
        assert c['person']['prepared_person_interpretation']['core']==p.prepared_initial['core']
        inputs.append({'id':row['id'],'persona':p.model_dump(mode='json'),'prior':prior.model_dump(mode='json'),
            'context':c,'initial_request':body,'original_persona_sha256':sha(ps),'original_prior_sha256':sha(qs)})
        files[str(ps)]=sha(ps);files[str(qs)]=sha(qs)
    (D/'prepared_inputs.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n')
    manifest={'scope':'onboarding-to-continuous-walk diagnostic','created_on':'2026-10-04',
      'call_cap':96,'per_person_cap':12,'max_output_tokens':12000,'input_byte_cap':32768,
      'retry_count':0,'concurrency':1,'model':MODEL,'actual_cost':None,'support_round':None,
      'new_map_calls':0,'new_embedding_calls':0,'new_gpu_training':0,
      'prepared_inputs_sha256':sha(D/'prepared_inputs.json'),'map':meta,
      'source_files':files,'code':{str(p.relative_to(D)):sha(p) for p in [D/'run.py',D/'bootstrap.py',D/'transport.py']},
      'limits':['8 synthetic people with recorded K interpretations, not independent held-out clinical subjects',
                'Cached initial priors used, no incident SAR/Mi:dm recall',
                'Fake named facilities and authored observations; not live KINTEX noise/crowd',
                'Research walker does not replace calibrated production displacement prior',
                'Abstention or exhausted budget yields unresolved mass, never inferred staying']}
    (D/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'prepared_people':len(inputs),'all_saved_K_fingerprints_match':True,'max_initial_input_bytes':max(len(json.dumps(r['initial_request'],ensure_ascii=False).encode()) for r in inputs)},ensure_ascii=False))


def execute():
    import transport
    manifest=json.loads((D/'manifest.json').read_text())
    assert sha(D/'prepared_inputs.json')==manifest['prepared_inputs_sha256']
    for name,digest in manifest['code'].items():assert sha(D/name)==digest,name
    lock=D/'LIVE_STARTED';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    net,meta,people,locations=load();all_results=[];total=[0]
    for item in people:
        row=item[0];case_dir=D/'live'/row['id'];case_dir.mkdir(parents=True)
        count=[0]
        def request(body):
            assert total[0]<96 and count[0]<12
            count[0]+=1;total[0]+=1;job=f"loop_{row['id']}_{count[0]:02d}"
            record={'id':job,'body':body,'request_sha256':__import__('hashlib').sha256(json.dumps(body,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
            (case_dir/(job+'.request.json')).write_text(json.dumps(record,ensure_ascii=False)+'\n')
            answer=transport.invoke(body,job)
            choice=answer.get('choices',[{}])[0]
            public={'content':choice.get('message',{}).get('content',''),'finish_reason':choice.get('finish_reason'),
                    'usage':answer.get('usage'),'model':answer.get('model')}
            (case_dir/(job+'.public.json')).write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
            return public
        s,bridge=session(net,item,locations,request);snaps={};error=None
        try:
            for t in HOURS:
                snap=s.advance_to(t);snaps[str(t)]=snap
                if s.terminated:break
        except Exception as exc:
            error=type(exc).__name__;s.terminated=True;s.termination_reason='provider_or_runtime_error'
        result={'id':row['id'],'calls':count[0],'snapshots':snaps,'last_snapshot':s.snapshot(),
                'decisions':s.decisions,'bridge_audit':bridge.audit,'error_type':error,
                'complete_to_360':not s.terminated and abs(s.g.elapsed_min-360)<1e-7}
        (case_dir/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        all_results.append(result)
        print(json.dumps({'id':row['id'],'calls':count[0],'simulated_minutes':s.g.elapsed_min,
                          'stop_reason':s.termination_reason,'error':error},ensure_ascii=False),flush=True)
    summaries=[]
    for t in HOURS:
        snapshots=[r['snapshots'].get(str(t),r['last_snapshot']) for r in all_results]
        summaries.append(probability_snapshot(net,snapshots,t))
    report={'calls':total[0],'people':len(all_results),'completed_6h':sum(r['complete_to_360'] for r in all_results),
            'hourly_diagnostic_mass':summaries,'clinical_accuracy_measured':False,
            'note':'These eight distinct people are not a single missing-person probability population.'}
    (D/'live_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    execute() if args.execute else prepare()
