// 끝난(삭제·종결) 사건을 시민 앱이 계속 묻던 문제(2026-10-12 운영: 지워진 사건 1건에
// 5분간 404 21회)의 회귀 검사. 훅 옵션은 실제 queries.ts 에서 꺼내고, 그 옵션을 실제
// @tanstack/query-core 관찰자에 물려 가짜 시계로 요청 횟수를 센다.
const {test,mock}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

const load=(file,deps,extra={})=>{
  const src=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
  const out={exports:{}};
  vm.runInNewContext(src,{exports:out.exports,module:out,require:n=>{if(!(n in deps))throw Error('unmocked '+n);const d=deps[n];return d&&'default' in d?{__esModule:true,...d}:d},...extra});
  return out.exports;
};
const errors=load('src/api/errors.ts',{});
const {ApiError,isCaseEnded}=errors;

test('ended classification: deleted/closed stop, not-yet-predicted and outages do not',()=>{
  assert.equal(isCaseEnded(new ApiError(404,'/p','사건을 찾을 수 없습니다.')),true);
  assert.equal(isCaseEnded(new ApiError(409,'/p','종결된 케이스 (found) — 예측·알림·제보 불가')),true);
  assert.equal(isCaseEnded(new ApiError(409,'/p','삭제된 사건 — 작업 불가')),true);
  assert.equal(isCaseEnded(new ApiError(409,'/p','POA 없음 — Phase 2 예측을 먼저 실행하세요')),false);
  assert.equal(isCaseEnded(new ApiError(503,'/p','완료 여부를 확인할 수 없습니다.')),false);
  assert.equal(isCaseEnded(new ApiError(0,'/p','서버 응답이 없어 요청을 중단했습니다')),false);
  assert.equal(isCaseEnded(new Error('사건을 찾을 수 없습니다.')),false);
});

// queries.ts 를 실제로 읽어 useQuery 에 넘기는 옵션을 붙잡는다.
const captured=[];
const queries=load('src/hooks/queries.ts',{
  react:React,
  '@tanstack/react-query':{useQuery:o=>{captured.push(o);return {data:undefined,error:null,isError:false}},useMutation:()=>({}),useQueryClient:()=>({})},
  '../api/client':{getPoaPrediction:async()=>({}),getGuidance:async()=>({}),touchPresence:async()=>0,getActiveAlerts:async()=>[],getResolvedAlerts:async()=>[],getNearbyWalks:async()=>[]},
  '../api/errors':errors,'../api/walk':{},'../api/guardian':{},
  '../store/appModeStore':{useAppModeStore:()=>null},'../store/authStore':{useAuthStore:()=>null},
  '../store/debugStore':{useDebugStore:()=>false},'../store/guardianCaseStore':{useGuardianCaseStore:()=>[]},
  './useMyLocation':{useMyLocation:()=>({})},'../data/missing':{LAST_SEEN:{lat:0,lng:0}},
  '../utils/h3cell':{cellOf:()=>null},'./useTargetingPolicy':{useTargetingPolicy:()=>({})},
});
function optionsOf(call){captured.length=0;call();return captured[0];}

// query-core 는 window 가 없으면 서버로 보고 주기 조회를 아예 끈다 — 브라우저처럼 보이게 한다.
globalThis.window={addEventListener(){},removeEventListener(){}};
globalThis.document={visibilityState:'visible',addEventListener(){},removeEventListener(){}};
mock.timers.enable({apis:['setTimeout','setInterval','Date']});
const {QueryClient,QueryObserver}=require('@tanstack/query-core');

async function countCalls(options,error,seconds){
  let calls=0;const client=new QueryClient();
  const observer=new QueryObserver(client,{...options,queryFn:async()=>{calls++;throw error}});
  const unsubscribe=observer.subscribe(()=>{});
  for(let s=0;s<seconds;s++){
    mock.timers.tick(1000);
    for(let i=0;i<5;i++)await new Promise(r=>process.nextTick(r));
  }
  unsubscribe();client.clear();
  return calls;
}

test('map polling stops after one 404 instead of retrying every 15s',async()=>{
  const poa=optionsOf(()=>queries.usePoaPrediction('gone',0));
  const gone=await countCalls(poa,new ApiError(404,'/poa','사건을 찾을 수 없습니다.'),300);
  assert.equal(gone,1);
  const closed=await countCalls(poa,new ApiError(409,'/poa','종결된 케이스 (closed) — 예측·알림·제보 불가'),300);
  assert.equal(closed,1);
});

test('transient map failures keep retrying and polling so the map can recover',async()=>{
  const poa=optionsOf(()=>queries.usePoaPrediction('live',0));
  const outage=await countCalls(poa,new ApiError(503,'/poa','완료 여부를 확인할 수 없습니다.'),120);
  assert.ok(outage>=8,`expected repeated retries, got ${outage}`);
  const notYet=await countCalls(poa,new ApiError(409,'/poa','POA 없음 — Phase 2 예측을 먼저 실행하세요'),120);
  assert.ok(notYet>=8,`prediction-not-ready must keep polling, got ${notYet}`);
});

test('presence heartbeat and guidance refinement stop on an ended case',async()=>{
  const presence=optionsOf(()=>queries.usePresence('gone'));
  assert.equal(await countCalls(presence,new ApiError(404,'/presence','사건을 찾을 수 없습니다.'),300),1);
  assert.ok(await countCalls(presence,new ApiError(503,'/presence','x'),300)>=9,'heartbeat keeps going through outages');
  const guidance=optionsOf(()=>queries.useGuidance('gone'));
  const stale={state:{data:{pending:true},error:new ApiError(404,'/g','사건을 찾을 수 없습니다.')}};
  assert.equal(guidance.refetchInterval(stale),false);
  assert.equal(guidance.refetchInterval({state:{data:{pending:true},error:null}}),3000);
});

// 화면: 끝난 사건이면 안내를 바꾸고, 하트비트·안내 조회를 끄고, 그 사건의 수색 모드만 닫는다.
function screen({ended,activeCaseId}){
  const calls={presence:[],guidance:[],closed:0,entered:0,nav:[]};
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  const buttons=[];
  const native={Platform:{OS:'web'},View:Box,ScrollView:Box,Text,ActivityIndicator:()=>null,StyleSheet:{create:x=>x},
    Pressable:p=>{buttons.push(p);return React.createElement('button',null,p.children)},
    Animated:{Value:class{addListener(){return 1}removeListener(){}setValue(){}},View:Box,timing:()=>({start(){}})},
    PanResponder:{create:()=>({panHandlers:{}})}};
  const store={activeCaseId,enterSearch:()=>calls.entered++,closeCase:()=>calls.closed++};
  const useAppModeStore=sel=>sel(store);useAppModeStore.getState=()=>store;
  const nav={navigate:(...a)=>calls.nav.push(['navigate',...a]),canGoBack:()=>false,popToTop:()=>calls.nav.push(['popToTop']),reset:a=>calls.nav.push(['reset',a.routes[0].name])};
  const R={...React,useEffect:f=>f()};
  const out=load('src/screens/AlertSyncScreen.tsx',{
    react:R,'react-native':native,'@react-navigation/native':{useNavigation:()=>nav,useRoute:()=>({params:{caseId:'gone'}})},
    '../theme/tokens':{color:{figmaRed:'red'},type:{}},'../store/appModeStore':{useAppModeStore},
    '../hooks/queries':{useActiveAlerts:()=>({data:[]}),usePoaPrediction:()=>({data:undefined,isLoading:false,ended}),
      usePresenceCount:(id,en)=>{calls.presence.push(en);return null},useGuidance:(id,en)=>{calls.guidance.push(en);return {data:undefined}}},
    '../data/missingView':{alertToView:()=>({appearance:[],title:'',meta:''})},
    '../components/FigmaStatusBar':{default:()=>null},'../components/FigmaFlowTabBar':{default:()=>null},
    '../components/BaseMap':{default:Box},'../components/PoaHeatmap':{default:()=>null},'../components/MapPin':{default:()=>null},
    '../components/WebMap':{default:()=>null},'../components/PersonSilhouette':{default:()=>null},
    '../theme/tabBar':{useTabBarMetrics:()=>({height:80})},
  },{React:R});
  const html=renderToStaticMarkup(React.createElement(out.default));
  return {html,calls,buttons};
}

test('ended alert screen tells the citizen, stops background queries and closes only its own search',()=>{
  const s=screen({ended:true,activeCaseId:'gone'});
  assert.match(s.html,/종료된 사건이에요/);assert.doesNotMatch(s.html,/목격 내용 제보하기/);
  assert.deepEqual([s.calls.presence,s.calls.guidance],[[false],[false]]);
  assert.equal(s.calls.closed,1);assert.equal(s.calls.entered,0);
  s.buttons.find(b=>b.accessibilityLabel==='홈으로 돌아가기').onPress();
  assert.deepEqual(s.calls.nav,[['reset','CitizenTabs']]);
  const other=screen({ended:true,activeCaseId:'another-live-case'});
  assert.equal(other.calls.closed,0,'a newer case search mode must not be closed');
});

test('live alert screen is unchanged',()=>{
  const s=screen({ended:false,activeCaseId:null});
  assert.match(s.html,/목격 내용 제보하기/);assert.doesNotMatch(s.html,/종료된 사건/);
  assert.deepEqual([s.calls.presence,s.calls.guidance],[[true],[true]]);
  assert.equal(s.calls.entered,1);assert.equal(s.calls.closed,0);
});
