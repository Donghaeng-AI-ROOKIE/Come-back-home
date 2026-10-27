// 신고 흐름의 하단 탭바 — 신고 중인데 "홈"이 켜져 있지 않은가.
//
// 10/27 측정: 실종 신고 접수 완료 화면(ReportSent)에서 탭바의 "홈"이 강조돼 있었다. 신고 흐름은
// 어느 탭에도 속하지 않으므로 아무 탭도 강조하지 않는다. 탭은 그대로 눌러 이동할 수 있다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

function load(file,modules){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
  const out={exports:{}};
  vm.runInNewContext(source,{exports:out.exports,module:out,require:name=>modules[name]??{__esModule:true,default:()=>null}});
  return out.exports;
}

function renderBar(props){
  const icons=[];const pressables=[];const navigated=[];
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children,style})=>React.createElement('span',{'data-color':[].concat(style).filter(Boolean).map(s=>s.color).filter(Boolean).pop()??''},children);
  const Pressable=(p)=>{pressables.push(p);return React.createElement('div',{role:'button'},p.children);};
  const Bar=load('src/components/FigmaFlowTabBar.tsx',{react:React,
    'react-native':{View:Box,Text,Pressable,StyleSheet:{create:x=>x,hairlineWidth:1}},
    '@react-navigation/native':{useNavigation:()=>({navigate:(...a)=>navigated.push(JSON.parse(JSON.stringify(a)))})},
    '../theme/tokens':{color:{guardian:'GREEN',figmaRed:'RED',brand:'BRAND',figmaGray:'GRAY'},type:{}},
    '../theme/tabBar':{FLOW_TAB_PADDING_TOP:12,useTabBarMetrics:()=>({height:80,paddingBottom:20,showFakeIndicator:false})},
    '../hooks/useKeyboardVisible':{useKeyboardVisible:()=>false},
    './FigmaTabIcon':{__esModule:true,default:(p)=>{icons.push(p);return null;}}}).default;
  const html=renderToStaticMarkup(React.createElement(Bar,props));
  return {html,icons,pressables,navigated};
}

test('without an active tab no icon and no label is highlighted', () => {
  const bar=renderBar({mode:'guardian',active:null});
  assert.deepEqual(bar.icons.map((i)=>i.focused),[false,false,false,false]);
  assert.doesNotMatch(bar.html,/data-color="GREEN"/);
});

test('tabs still work from a flow screen with nothing highlighted', () => {
  const bar=renderBar({mode:'guardian',active:null});
  bar.pressables[2].onPress();
  assert.deepEqual(bar.navigated,[['GuardianTabs',{screen:'GuardianAlerts'}]]);
});

test('screens that belong to a tab keep their highlight', () => {
  const bar=renderBar({mode:'guardian',active:'home'});
  assert.deepEqual(bar.icons.map((i)=>i.focused),[true,false,false,false]);
  assert.match(bar.html,/data-color="GREEN">홈</);
});

test('the report flow screens (Report, ReportSent) pass no active tab', () => {
  // 두 화면은 의존이 많아(지도·예측 조회·키보드) 탭바에 넘기는 값만 원본에서 읽는다.
  for (const file of ['src/screens/ReportScreen.tsx','src/screens/ReportSentScreen.tsx']) {
    const src=fs.readFileSync(path.join(__dirname,'..',file),'utf8');
    const uses=[...src.matchAll(/<FigmaFlowTabBar\b[^>]*\bactive=(\{null\}|"[a-z]+")/g)].map((m)=>m[1]);
    assert.deepEqual(uses,['{null}'],file);
  }
});
