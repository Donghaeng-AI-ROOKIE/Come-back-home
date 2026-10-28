// 탭 내비게이터 밖 화면의 하단 탭바 — 긴급 모드인 동안 강조가 빨강인가.
//
// 10/27 측정: 실종 신고 접수 완료 화면(ReportSent)에서 탭바의 "홈"이 초록으로 강조돼 있었다.
// #338 은 강조를 없앴는데(active={null}), 10/27 화면흐름 보드 의견은 반대였다 — 실종이 발생한
// 화면은 초록이 아니라 빨강으로 강조해야 한다. 보호자는 신고 흐름에 있거나 진행 중 사건이 있으면,
// 시민은 긴급 알림 흐름(제보 완료 포함)이면 빨강이다(utils/tabAccent).
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

// utils 는 대역을 두지 않고 진짜를 읽는다 — 이 시험이 보려는 것이 그 판정이다.
// 화면이 부를 때만 읽으므로, 그 utils 를 쓰지 않는 화면에는 아무 영향이 없다.
function load(file,modules){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
  const out={exports:{}};
  const util=(name)=>/^\.\.\/utils\//.test(name)?load(path.join(path.dirname(file),`${name}.ts`),{}):undefined;
  vm.runInNewContext(source,{exports:out.exports,module:out,require:name=>modules[name]??util(name)??{__esModule:true,default:()=>null}});
  return out.exports;
}

const tokens={color:{guardian:'GREEN',figmaRed:'RED',brand:'BRAND',figmaGray:'GRAY'},type:{}};
const caseOf=(id,status)=>({id,status,created_at:'2026-10-27T03:00:00',tips:[]});

function renderBar(props,{cases=[]}={}){
  const icons=[];const pressables=[];const navigated=[];const asked=[];
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children,style})=>React.createElement('span',{'data-color':[].concat(style).filter(Boolean).map(s=>s.color).filter(Boolean).pop()??''},children);
  const Pressable=(p)=>{pressables.push(p);return React.createElement('div',{role:'button'},p.children);};
  const Bar=load('src/components/FigmaFlowTabBar.tsx',{react:React,
    'react-native':{View:Box,Text,Pressable,StyleSheet:{create:x=>x,hairlineWidth:1}},
    '@react-navigation/native':{useNavigation:()=>({navigate:(...a)=>navigated.push(JSON.parse(JSON.stringify(a)))})},
    '../theme/tokens':tokens,
    '../theme/tabBar':{FLOW_TAB_PADDING_TOP:12,useTabBarMetrics:()=>({height:80,paddingBottom:20,showFakeIndicator:false})},
    '../hooks/useKeyboardVisible':{useKeyboardVisible:()=>false},
    '../hooks/queries':{useGuardianCases:(use='poll')=>{asked.push(use);return {data:use==='off'?undefined:cases};}},
    './FigmaTabIcon':{__esModule:true,default:(p)=>{icons.push(p);return null;}}}).default;
  const html=renderToStaticMarkup(React.createElement(Bar,props));
  return {html,icons,pressables,navigated,asked};
}

test('without an active tab no icon and no label is highlighted', () => {
  const bar=renderBar({mode:'guardian',active:null});
  assert.deepEqual(bar.icons.map((i)=>i.focused),[false,false,false,false]);
  assert.doesNotMatch(bar.html,/data-color="GREEN"/);
});

test('tabs still work from a flow screen', () => {
  const bar=renderBar({mode:'guardian',active:'home',emergency:true});
  bar.pressables[2].onPress();
  assert.deepEqual(bar.navigated,[['GuardianTabs',{screen:'GuardianAlerts'}]]);
});

test('a guardian with no ongoing case keeps the green highlight', () => {
  const bar=renderBar({mode:'guardian',active:'home'},{cases:[caseOf('done','found'),caseOf('gone','withdrawn')]});
  assert.deepEqual(bar.icons.map((i)=>i.focused),[true,false,false,false]);
  assert.equal(bar.icons[0].activeColor,'GREEN');
  assert.match(bar.html,/data-color="GREEN">홈</);
});

test('a guardian with an ongoing case sees the highlight in red (PersonaDetail, RegDone)', () => {
  for (const active of ['home','register']) {
    const bar=renderBar({mode:'guardian',active},{cases:[caseOf('c1','searching')]});
    // 목록은 보호자 탭이 주기 조회하는 것을 따라 읽기만 한다 — 탭바가 따로 주기를 걸면 요청이 는다.
    assert.deepEqual(bar.asked,['follow'],active);
    assert.ok(bar.icons.every((i)=>i.activeColor==='RED'),active);
    assert.doesNotMatch(bar.html,/data-color="GREEN"/,active);
    assert.match(bar.html,/data-color="RED">/,active);
  }
});

test('the report flow is an emergency even before the new case is in the list', () => {
  const bar=renderBar({mode:'guardian',active:'home',emergency:true},{cases:[]});
  assert.deepEqual(bar.icons.map((i)=>i.focused),[true,false,false,false]);
  assert.equal(bar.icons[0].activeColor,'RED');
  assert.match(bar.html,/data-color="RED">홈</);
});

test('citizen flow screens: the alert tab is red, other tabs keep the brand colour, and no guardian cases are asked for', () => {
  const alert=renderBar({mode:'citizen',active:'alert'});
  assert.match(alert.html,/data-color="RED">긴급 알림</);
  const walk=renderBar({mode:'citizen',active:'register'},{cases:[caseOf('c1','searching')]});
  assert.match(walk.html,/data-color="BRAND">산책하기</);
  // 시민 기기가 보호자 사건 목록을 묻지 않는다 — 훅을 부르더라도 꺼 둔 채로 부른다.
  assert.ok([...alert.asked,...walk.asked].every((use)=>use==='off'));
});

test('the report flow screens (Report, ReportSent) highlight home as an emergency', () => {
  // 두 화면은 의존이 많아(지도·예측 조회·키보드) 탭바에 넘기는 값만 원본에서 읽는다.
  for (const file of ['src/screens/ReportScreen.tsx','src/screens/ReportSentScreen.tsx']) {
    const src=fs.readFileSync(path.join(__dirname,'..',file),'utf8');
    const uses=[...src.matchAll(/<FigmaFlowTabBar\b([^>]*?)\/>/g)].map((m)=>m[1].trim().split(/\s+/).sort());
    assert.deepEqual(uses,[['active="home"','emergency','mode="guardian"']],file);
  }
});

test('the citizen tip-done screen (ReportDone) belongs to the alert flow, not to the home tab', () => {
  const bars=[];
  const Box=({children})=>React.createElement('div',null,children);
  const screen=load('src/screens/ReportDoneScreen.tsx',{react:React,
    'react-native':{View:Box,Text:Box,Image:()=>null,Pressable:Box,StyleSheet:{create:x=>x}},
    'react-native-safe-area-context':{SafeAreaView:Box},'expo-status-bar':{StatusBar:()=>null},
    'expo-linear-gradient':{LinearGradient:Box},
    '@react-navigation/native':{useNavigation:()=>({navigate(){},popTo(){}}),useRoute:()=>({params:{caseId:'c1'}})},
    '../theme/tokens':tokens,
    '../components/FigmaFlowTabBar':{__esModule:true,default:(p)=>{bars.push({...p});return null;}}});
  renderToStaticMarkup(React.createElement(screen.default));
  assert.deepEqual(bars,[{mode:'citizen',active:'alert'}]);
});
