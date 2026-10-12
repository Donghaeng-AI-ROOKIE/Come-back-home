// 제보 직후 사용자가 기다리지 않는다: 제보 전송은 제보 요청 1건만 보낸다.
// 2026-10-12 운영: 제보 전후로 지도를 한 번씩 더 읽어(완료 화면은 그 값을 쓰지
// 않음) 같은 계산 줄에서 세 요청이 차례로 기다렸다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');

function load(apiImpl,{cloud=true,mock=false}={}){
  const src=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/api/client.ts'),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const deps={
    '../data/missing':{DEMO_CASE_ID:'demo'},'../theme/poa':{tierForProb:()=> 'low'},
    '../utils/targetingPolicy':{targetingResolution:()=>9},
    '../data/mock':{buildAlert(){},buildPoaGrid(){}},
    './supabase':{CLOUD_TRANSPORT:cloud},
    './config':{DEMO_USER_ID:'u',SLOW_TIMEOUT_MS:90000,USE_MOCK:mock,api:apiImpl,API_BASE:'',ApiError:Error},
  };
  const out={exports:{}};
  vm.runInNewContext(src,{exports:out.exports,module:out,require:n=>{if(!(n in deps))throw Error('unmocked '+n);return deps[n]},setTimeout,Promise,Math,Date,JSON,Number,String});
  return out.exports;
}

const tipRow={id:'t1',case_id:'c1',text:'망원역 2번 출구에서 봤어요',location:{lat:37.55,lng:126.91},seen_at:null,p:0.88,decision:'layer2',created_at:'2026-10-12T21:52:47'};

test('tip submission sends only the tip request and returns the accepted tip',async()=>{
  const calls=[];
  const client=load(async(p,init)=>{calls.push([init?.method??'GET',p]);if(p.endsWith('/tips'))return tipRow;throw Error('unexpected '+p)});
  const res=await client.submitTip('c1',{text:'망원역 2번 출구에서 봤어요'},{reporterUserId:'u1'});
  assert.deepEqual(calls,[['POST','/phase3/cases/c1/tips']],'지도 조회가 제보 앞뒤에 끼면 제보자가 그만큼 기다린다');
  assert.equal(res.tip.id,'t1');assert.equal(res.tip.decision,'layer2');
  assert.deepEqual(Object.keys(res),['tip']);
});

test('need_more is still returned to the chat without extra requests',async()=>{
  const calls=[];
  const client=load(async(p,init)=>{calls.push(p);return {status:'need_more',missing:['location']}});
  const res=await client.submitTip('c1',{text:'봤어요'});
  assert.equal(res.status,'need_more');assert.equal(calls.length,1);
});

test('screens no longer promise an immediate recompute or a 2-minute map download',()=>{
  const chat=fs.readFileSync(path.join(__dirname,'../src/screens/ReportChatScreen.tsx'),'utf8');
  const done=fs.readFileSync(path.join(__dirname,'../src/screens/ReportDoneScreen.tsx'),'utf8');
  assert.doesNotMatch(chat,/예상 경로를 다시 계산하고 있어요|최대 2분/);
  assert.match(done,/뒤에서 다시 계산해 잠시 뒤 지도에 반영돼요/);
  assert.doesNotMatch(done,/즉시 반영됩니다/);
});
