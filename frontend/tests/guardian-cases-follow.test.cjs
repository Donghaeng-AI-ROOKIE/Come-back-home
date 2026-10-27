// 보호자 사건 목록(useGuardianCases) — 하단 탭바가 같은 목록을 읽어도 요청이 늘지 않는가.
//
// 탭바(components/FigmaFlowTabBar)가 진행 중 사건을 보고 빨강을 고르려면 이 목록이 필요하다.
// 그런데 TanStack Query 의 주기 조회(refetchInterval)는 관찰자마다 자기 타이머로 돈다 — 같은 쿼리
// 키라도 탭바가 주기를 걸면, 보호자 탭(GuardianTabs)의 타이머와 엇갈려 15초마다 한 번씩 더 묻는다.
// 탭바는 'follow'(따라 읽기만), 시민 화면에서는 'off'(묻지 않음)로 부른다.
//
// 훅 파일을 실제로 변환해 읽고, useQuery 에 넘기는 옵션을 받아 본다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');

function loadQueries(){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..','src/hooks/queries.ts'),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const seen=[];
  const modules={
    '@tanstack/react-query':{useQuery:(options)=>{seen.push(options);return {data:undefined};},useMutation:()=>({}),useQueryClient:()=>({})},
    '../store/authStore':{useAuthStore:(sel)=>sel({userId:'u1'})},
    '../store/guardianCaseStore':{useGuardianCaseStore:(sel)=>sel({caseIds:['c1','c2']})},
  };
  const out={exports:{}};
  vm.runInNewContext(source,{exports:out.exports,module:out,require:name=>modules[name]??{__esModule:true,default:()=>null}});
  // 훅을 그냥 함수로 불러, useQuery 에 넘긴 옵션 하나를 돌려받는다.
  return (...args)=>{seen.length=0;out.exports.useGuardianCases(...args);return seen[0];};
}

const useGuardianCases=loadQueries();
const key=(o)=>JSON.stringify(o.queryKey);

test('the guardian screens keep polling every 15 seconds as before', () => {
  const o=useGuardianCases();
  assert.equal(o.enabled,true);
  assert.equal(o.refetchInterval,15_000);
  assert.equal(o.refetchOnWindowFocus,true);
  assert.equal(key(o),'["guardianCases","u1",["c1","c2"]]');
});

test('the tab bar follows the same list without a timer of its own', () => {
  const o=useGuardianCases('follow');
  // 같은 키 — 보호자 탭이 받아 둔 목록을 그대로 읽는다. 비어 있을 때만 묻는다(enabled).
  assert.equal(key(o),key(useGuardianCases()));
  assert.equal(o.enabled,true);
  assert.equal(o.refetchInterval,false);
  assert.equal(o.refetchOnMount,false);
  assert.equal(o.refetchOnWindowFocus,false);
});

test('citizen screens do not ask for the guardian case list at all', () => {
  assert.equal(useGuardianCases('off').enabled,false);
});
