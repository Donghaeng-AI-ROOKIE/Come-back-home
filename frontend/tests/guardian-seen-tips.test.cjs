// 보호자 기기가 "알림 탭에서 이미 본 제보"를 어떻게 적어 두는가 — 홈 "수색 중" 카드의 새 제보 수 기준.
// 실제 스토어 파일을 실제 zustand 로 띄우고, 저장소만 메모리로 바꾼다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');

function freshStore(){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..','src/store/guardianCaseStore.ts'),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const memory=new Map();const writes=[];
  const safeStorage={getItem:async k=>memory.get(k)??null,setItem:async(k,v)=>{writes.push(v);memory.set(k,v);},removeItem:async k=>{memory.delete(k);}};
  const modules={zustand:require('zustand'),'zustand/middleware':require('zustand/middleware'),'./safeStorage':{safeStorage}};
  const out={exports:{}};
  vm.runInNewContext(source,{exports:out.exports,module:out,require:n=>modules[n]});
  return {store:out.exports.useGuardianCaseStore,writes};
}
const plain=v=>JSON.parse(JSON.stringify(v));

test('seen tips accumulate per case without duplicates',()=>{
  const {store}=freshStore();
  store.getState().markTipsSeen('c1',['t1','t2']);
  store.getState().markTipsSeen('c1',['t2','t3']);
  assert.deepEqual(plain(store.getState().seenTips),{c1:['t1','t2','t3']});
});

test('marking the same tips again does not write to storage again',()=>{
  const {store,writes}=freshStore();
  store.getState().markTipsSeen('c1',['t1']);
  const after=writes.length;
  store.getState().markTipsSeen('c1',['t1']);
  store.getState().markTipsSeen('c1',[]);
  assert.equal(writes.length,after);
});

test('only the ten most recently marked cases are kept, and a deleted case drops its record',()=>{
  const {store}=freshStore();
  for(let i=0;i<12;i++)store.getState().markTipsSeen(`c${i}`,['t']);
  // 열두 건을 적으면 가장 먼저 적은 c0·c1 이 밀려난다.
  assert.deepEqual(Object.keys(store.getState().seenTips),['c2','c3','c4','c5','c6','c7','c8','c9','c10','c11']);
  // c0 을 다시 적으면 가장 최근이 되어 남고, 그때 가장 오래된 c2 가 빠진다.
  store.getState().markTipsSeen('c0',['t','u']);
  assert.deepEqual(Object.keys(store.getState().seenTips),['c3','c4','c5','c6','c7','c8','c9','c10','c11','c0']);
  store.getState().removeCase('c0');
  assert.ok(!('c0' in store.getState().seenTips));
});

test('sign-out clear forgets what was seen',()=>{
  const {store}=freshStore();
  store.getState().markTipsSeen('c1',['t1']);
  store.getState().clear();
  assert.deepEqual(plain(store.getState().seenTips),{});
});
