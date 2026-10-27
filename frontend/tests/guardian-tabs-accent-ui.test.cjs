// 보호자 하단 4탭 — 진행 중 사건이 있는 동안 강조가 빨강인가.
//
// 10/27 화면흐름 보드 의견: 실종이 발생해 수색이 진행 중인데 보호자 탭(홈·사전등록·알림·내 정보)이
// 평소처럼 초록이라, 지금이 긴급 상황인지 탭바로는 알 수 없었다. 진행 중 사건(intake·predicted·
// searching)이 1건 이상이면 빨강, 모두 종결·철회되면 초록으로 돌아온다(utils/tabAccent).
//
// 탭 내비게이터를 대역으로 바꿔 화면 파일이 넘기는 옵션을 받아 보고, 각 탭의 아이콘을 직접 그려 본다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

// utils 는 진짜를 읽는다 — 진행 중 판정(activeCases)과 색 판정이 이 시험의 대상이다.
function load(file,modules){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
  const out={exports:{}};
  const util=(name)=>/^\.\.\/utils\//.test(name)?load(path.join(path.dirname(file),`${name}.ts`),{}):undefined;
  vm.runInNewContext(source,{exports:out.exports,module:out,require:name=>modules[name]??util(name)??{__esModule:true,default:()=>null}});
  return out.exports;
}

const caseOf=(id,status)=>({id,status,created_at:'2026-10-27T03:00:00',tips:[]});

function mount(cases){
  const nav={};const screens=[];
  const Box=({children})=>React.createElement('div',null,children);
  const Tabs=load('src/navigation/GuardianTabs.tsx',{react:React,
    'react-native':{View:Box,Text:Box,Alert:{alert(){}},StyleSheet:{create:x=>x}},
    'react-native-safe-area-context':{SafeAreaView:Box},
    '@react-navigation/bottom-tabs':{createBottomTabNavigator:()=>({
      Navigator:(p)=>{nav.screenOptions=p.screenOptions;return React.createElement('div',null,p.children);},
      Screen:(p)=>{screens.push(p);return null;}})},
    '@react-navigation/elements':{PlatformPressable:Box},
    '../theme/tokens':{color:{guardian:'GREEN',figmaRed:'RED',brand:'BRAND',figmaGray:'GRAY',surface:'#fff',border:'#ddd'},radius:{},space:{},type:{size:{}}},
    '../theme/tabBar':{useTabBarMetrics:()=>({height:80,paddingBottom:20,showFakeIndicator:false})},
    '../hooks/useKeyboardVisible':{useKeyboardVisible:()=>false},
    '../hooks/queries':{useGuardianCases:()=>({data:cases}),usePersonas:()=>({data:[],isLoading:false})},
    '../store/guardianCaseStore':{useGuardianCaseStore:(sel)=>sel({markTipsSeen(){}})},
    '../components/FigmaTabIcon':{__esModule:true,default:()=>null}}).default;
  renderToStaticMarkup(React.createElement(Tabs));
  // 각 탭의 아이콘을 켜진 상태로 그려, 화면이 넘긴 강조색을 읽는다.
  const icons=screens.map((s)=>s.options.tabBarIcon({focused:true,color:'',size:24}).props.activeColor);
  return {tint:nav.screenOptions.tabBarActiveTintColor,icons,names:screens.map((s)=>s.name)};
}

test('all four guardian tabs are red while a case is ongoing', () => {
  for (const status of ['intake','predicted','searching']) {
    const tabs=mount([caseOf('done','found'),caseOf('c1',status)]);
    assert.deepEqual(tabs.names,['GuardianHome','GuardianReg','GuardianAlerts','GuardianMy']);
    assert.equal(tabs.tint,'RED',status);
    assert.deepEqual(tabs.icons,['RED','RED','RED','RED'],status);
  }
});

test('with no ongoing case (none yet, or all found, closed or withdrawn) the tabs are guardian green', () => {
  for (const cases of [undefined,[],[caseOf('a','found'),caseOf('b','closed'),caseOf('c','withdrawn')]]) {
    const tabs=mount(cases);
    assert.equal(tabs.tint,'GREEN');
    assert.deepEqual(tabs.icons,['GREEN','GREEN','GREEN','GREEN']);
  }
});
