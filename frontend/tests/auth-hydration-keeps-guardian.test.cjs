// 앱을 다시 열 때 보호자 기록(사건 ID·본 제보)이 지워지지 않는가 — 그러면서 계정이 바뀌면 지워지는가.
//
// authStore 는 로그인한 사람(userId)이 바뀌면 기기의 보호자 기록을 지운다(다른 계정에 남의
// 사건이 보이지 않게). 그런데 앱을 열 때 저장소에서 로그인 상태를 되살리는 순간도
// "null → 같은 사람"이라 바뀐 것으로 셌다. 두 저장소가 비동기로 되살아나는 순서상 보호자
// 기록이 먼저 되살아나고, 곧이어 로그인 상태가 되살아나며 그 기록을 지웠다
// (웹 빌드 실측 10/27: guardian-case-v2 가 열 때마다 빈 값). 홈 "새 제보" 수가 앱을 열
// 때마다 처음부터 다시 세어졌다.
//
// 실제 스토어 파일을 실제 zustand 로 띄우고, 저장소만 메모리로 바꾼다. 불러오는 순서는 앱과
// 같다(authStore 가 guardianCaseStore 를 import 하므로 보호자 기록이 먼저 만들어진다).
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');

function load(file,modules){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const out={exports:{}};
  vm.runInNewContext(source,{exports:out.exports,module:out,setTimeout,require:n=>{
    if(!(n in modules))throw Error('unmocked '+n);return modules[n];}});
  return out.exports;
}

async function boot({me}={}){
  const memory=new Map([
    ['auth-v2',JSON.stringify({state:{token:'tok',role:'guardian',user:'demo',userId:'u1'},version:0})],
    ['guardian-case-v2',JSON.stringify({state:{caseIds:['c1'],seenTips:{c1:['t1']}},version:0})],
  ]);
  // AsyncStorage 처럼 한 박자 늦게 돌려준다.
  const safeStorage={getItem:k=>new Promise(r=>setTimeout(()=>r(memory.get(k)??null),0)),
    setItem:async(k,v)=>{memory.set(k,v);},removeItem:async k=>{memory.delete(k);}};
  const zustand={zustand:require('zustand'),'zustand/middleware':require('zustand/middleware'),'./safeStorage':{safeStorage}};
  const cases=load('src/store/guardianCaseStore.ts',zustand);
  let guardianResets=0;
  const auth=load('src/store/authStore.ts',{...zustand,'react-native':{Platform:{OS:'ios'}},
    '../api/auth':{me:async()=>me??{token:'tok',role:'guardian',login_id:'demo',user_id:'u1'},logout:async()=>{}},
    './guardianStore':{useGuardianStore:{getState:()=>({reset:()=>{guardianResets++;}})}},
    './guardianCaseStore':cases});
  for(let i=0;i<5;i++)await new Promise(r=>setTimeout(r,0));
  return {cases:cases.useGuardianCaseStore,auth:auth.useAuthStore,resets:()=>guardianResets};
}
const plain=v=>JSON.parse(JSON.stringify(v));

test('reopening the app keeps the same guardian\'s cases and seen tips', async () => {
  const app=await boot();
  assert.equal(app.auth.getState().userId,'u1');
  assert.deepEqual(plain(app.cases.getState().caseIds),['c1']);
  assert.deepEqual(plain(app.cases.getState().seenTips),{c1:['t1']});
  assert.equal(app.resets(),0);
  // 서버 확인(restore)이 같은 사람을 돌려줘도 그대로다.
  await app.auth.getState().restore();
  assert.deepEqual(plain(app.cases.getState().seenTips),{c1:['t1']});
});

test('signing out still wipes the device records', async () => {
  const app=await boot();
  app.auth.getState().signOut();
  assert.deepEqual(plain(app.cases.getState().caseIds),[]);
  assert.deepEqual(plain(app.cases.getState().seenTips),{});
  assert.equal(app.resets(),1);
});

test('a token that now belongs to another account wipes them too', async () => {
  const app=await boot({me:{token:'tok2',role:'guardian',login_id:'other',user_id:'u2'}});
  await app.auth.getState().restore();
  assert.equal(app.auth.getState().userId,'u2');
  assert.deepEqual(plain(app.cases.getState().caseIds),[]);
  assert.deepEqual(plain(app.cases.getState().seenTips),{});
});
