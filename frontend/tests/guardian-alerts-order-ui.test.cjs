// 보호자 알림 탭 — 제보가 사건 카드에 밀려나지 않는가, 종결 확인 동작은 그대로인가.
//
// 10/27 측정: 진행 중·종결 사건 관리 카드가 모두 "제보 알림" 목록 위에 쌓여, 사건이 쌓일수록
// 제보가 시트 아래로 밀려났다. 순서를 지도 → 제보 알림 → 사건 관리 → 종결된 사건(접힘)으로 바꾼다.
//
// 화면 파일을 실제로 변환해 그리고(react-dom/server), 버튼의 onPress 를 직접 눌러 본다.
// useState 는 렌더 사이에 값을 이어 주는 작은 대역으로 바꾼다 — 정적 렌더는 상태를 들고 있지 않는다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

function load(file,modules){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
  const out={exports:{}};
  vm.runInNewContext(source,{exports:out.exports,module:out,React,
    require:name=>modules[name]??{__esModule:true,default:()=>null}});
  return out.exports;
}

/** 렌더 사이에 상태를 이어 주는 훅 대역과, 눌러 볼 수 있게 Pressable 을 모아 두는 react-native 대역. */
function harness(){
  const slots=[];let cursor=0;let pressables=[];
  const hooks={...React,
    useState:init=>{const k=cursor++;if(!(k in slots))slots[k]=typeof init==='function'?init():init;
      return [slots[k],v=>{slots[k]=typeof v==='function'?v(slots[k]):v;}];},
    useEffect:()=>{},useMemo:fn=>fn(),useRef:v=>({current:v})};
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  const Pressable=(props)=>{pressables.push(props);return React.createElement('div',{role:'button'},props.children);};
  class Value{constructor(v){this.v=v}addListener(){return 1}removeListener(){}setValue(){}}
  const native={View:Box,Text,ScrollView:Box,Pressable,ActivityIndicator:()=>null,Platform:{OS:'web'},
    StyleSheet:{create:x=>x},PanResponder:{create:()=>({panHandlers:{}})},Animated:{Value,View:Box,timing:()=>({start(){}})}};
  const render=(element)=>{cursor=0;pressables=[];return renderToStaticMarkup(element);};
  const press=async(match)=>{
    const hit=pressables.find(p=>match.test(p.accessibilityLabel??'')||match.test(renderToStaticMarkup(React.createElement(React.Fragment,null,p.children))));
    assert.ok(hit,`no button matching ${match}`);
    await hit.onPress();
  };
  return {hooks,native,render,press};
}

const tokens={color:{guardian:'green',figmaRed:'red'},type:{}};
const ACTIVE={id:'live',status:'searching',created_at:'2026-10-27T03:00:00',lkp:{lat:37.6652,lng:126.7483},
  tips:[{id:'t1',text:'킨텍스 제2전시장 앞에서 봤어요',created_at:'2026-10-27T03:30:00',location:{lat:37.6652,lng:126.7483}}]};
const CLOSED={id:'done',status:'found',created_at:'2026-10-26T03:00:00',lkp:{lat:37.5,lng:127},tips:[]};

function mountAlerts(cases){
  const h=harness();
  const guardianTips=load('src/utils/guardianTips.ts',{});
  const modules={react:h.hooks,'react-native':h.native,'h3-js':{latLngToCell:()=>'cell-a'},
    '../theme/tokens':tokens,
    '../hooks/queries':{useGuardianCases:()=>({data:cases,isLoading:false,isError:false,refetch(){}}),
      useAreaLabels:()=>({data:['[고양시 일산서구] 킨텍스로']}),usePoaPrediction:()=>({data:undefined,isLoading:false,refetch(){}})},
    // 판정 규칙은 진짜를 쓴다 — 이 시험이 보려는 것이 그 규칙이다.
    '../utils/guardianTips':guardianTips,
    // 사건 카드 안쪽은 아래 시험이 따로 본다. 여기서는 자리만 표시한다.
    '../components/LifecycleControls':{CaseLifecycleCard:({item})=>React.createElement('i',null,`CASE:${item.id}`)}};
  const screen=load('src/screens/GuardianAlertsScreen.tsx',modules);
  return {render:()=>h.render(React.createElement(screen.default)),press:h.press};
}

test('tips come first, then the ongoing case card, then the closed cases', () => {
  const html=mountAlerts([ACTIVE,CLOSED]).render();
  const tips=html.indexOf('제보 알림');
  const manage=html.indexOf('사건 관리');
  const live=html.indexOf('CASE:live');
  const closedHead=html.indexOf('종결된 사건 1건');
  assert.ok(tips>=0&&manage>=0&&live>=0&&closedHead>=0,html);
  assert.ok(html.indexOf('[고양시 일산서구] 킨텍스로')<manage,'the tip card sits above case management');
  assert.ok(tips<manage&&manage<live&&live<closedHead,'order: 제보 알림 → 사건 관리 → 종결된 사건');
});

test('closed cases are folded by default and open on press', async () => {
  const ui=mountAlerts([ACTIVE,CLOSED]);
  assert.doesNotMatch(ui.render(),/CASE:done/);
  await ui.press(/종결된 사건 1건/);
  assert.match(ui.render(),/CASE:done/);
  await ui.press(/종결된 사건 1건/);
  assert.doesNotMatch(ui.render(),/CASE:done/);
});

test('without cases there is no case section at all', () => {
  const html=mountAlerts([]).render();
  assert.doesNotMatch(html,/사건 관리|종결된 사건/);
  assert.match(html,/진행 중인 실종 신고가 없습니다/);
});

test('closing a case still takes two presses and calls the same close request', async () => {
  const h=harness();
  const closed=[];let refreshed=0;
  const modules={react:h.hooks,'react-native':h.native,'../theme/tokens':tokens,
    '@tanstack/react-query':{useQueryClient:()=>({})},
    '../api/guardian':{closeCase:async(...a)=>{closed.push(a);},deleteCase:async()=>{},deletePersona:async()=>{},confirmPersona:async()=>{}},
    '../store/authStore':{useAuthStore:sel=>sel({userId:'owner-1'})},
    '../store/guardianCaseStore':{useGuardianCaseStore:{getState:()=>({removeCase(){}})}},
    '../store/guardianStore':{useGuardianStore:{getState:()=>({caseId:null,reset(){}})}},
    '../utils/caseRefresh':{refreshAfterCaseChange:async()=>{refreshed++;}},
    '../utils/walkFormat':load('src/utils/walkFormat.ts',{})};
  const {CaseLifecycleCard}=load('src/components/LifecycleControls.tsx',modules);
  const card=React.createElement(CaseLifecycleCard,{item:ACTIVE});
  h.render(card);
  await h.press(/^<span>가족을 찾았어요<\/span>$/);
  assert.equal(closed.length,0,'first press only asks');
  const asking=h.render(card);
  assert.match(asking,/수색을 종결하고 시민 알림과 지도 제공을 중단해요/);
  await h.press(/^<span>가족을 찾았어요 확인<\/span>$/);
  assert.deepEqual(JSON.parse(JSON.stringify(closed)),[['live','owner-1','found']]);
  assert.equal(refreshed,1);
});

test('the case date reads the server time as UTC: a 08:30 KST report is not shown as the day before', () => {
  process.env.TZ='Asia/Seoul';
  const h=harness();
  const modules={react:h.hooks,'react-native':h.native,'../theme/tokens':tokens,
    '@tanstack/react-query':{useQueryClient:()=>({})},'../api/guardian':{},
    '../store/authStore':{useAuthStore:sel=>sel({userId:'owner-1'})},
    '../utils/caseRefresh':{refreshAfterCaseChange:async()=>{}},
    '../utils/walkFormat':load('src/utils/walkFormat.ts',{})};
  const {CaseLifecycleCard}=load('src/components/LifecycleControls.tsx',modules);
  // 10/27 08:30 KST 신고 = 서버 "2026-10-26T23:30:00"(오프셋 없음).
  const html=h.render(React.createElement(CaseLifecycleCard,{item:{...ACTIVE,created_at:'2026-10-26T23:30:00'}}));
  assert.match(html,/2026\. 10\. 27\./);
});

test('tips are grouped and titled by the place the citizen named, road name only without one', () => {
  // 10/29 팀 점검(군포 7d20c6614579): "수리초등학교 앞"·"수리중학교 앞" 제보가 둘 다 "수리산로" 묶음이었다.
  const at=(lat,lng)=>({lat,lng});
  const GUNPO={...ACTIVE,tips:[
    {id:'a',text:'5분전에 수리초등학교 앞에서 봤어요',place:'수리초등학교',created_at:'2026-10-28T16:19:37',location:at(37.36018,126.91802)},
    {id:'b',text:'2분 전에 수리중학교 앞에서 봤어요',place:'수리중학교',created_at:'2026-10-28T16:20:27',location:at(37.36093,126.91843)},
    {id:'c',text:'수리중학교 정문에서 봤어요',place:' 수리중학교 ',created_at:'2026-10-28T16:22:00',location:at(37.36094,126.91844)},
    {id:'d',text:'비슷한 분이 지나갔어요',created_at:'2026-10-28T16:23:00',location:at(37.3606,126.9182)}]};
  const html=mountAlerts([GUNPO]).render();
  assert.equal((html.match(/해당 위치에서 총/g)||[]).length,3,html);
  assert.match(html,/>수리초등학교</);
  assert.match(html,/>수리중학교</);
  assert.match(html,/수리중학교<\/span><span>해당 위치에서 총 2건/,'same place with different spacing is one group');
  // 장소를 말하지 않은 제보만 도로명 묶음이다(useAreaLabels 대역의 첫 이름).
  assert.equal((html.match(/\[고양시 일산서구\] 킨텍스로/g)||[]).length,1);
});
