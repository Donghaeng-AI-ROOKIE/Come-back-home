// 제보 완료 뒤 — 수색 맥락으로 돌아갈 수 있는가, 돌아갈 때 지도가 두 번 쌓이지 않는가.
//
// 10/27 측정: 제보 완료 화면에 "홈으로 돌아가기"만 있어, 제보한 시민이 그 사건의 수색지도로
// 돌아갈 길이 없었다(수색 맥락이 끊김).
//
// 화면은 react-dom/server 로 그리고 버튼의 onPress 를 직접 누른다. 스택이 어떻게 바뀌는지는
// 앱이 쓰는 실제 StackRouter(@react-navigation/routers)에 같은 동작을 넣어 확인한다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
const {StackRouter,StackActions}=require('@react-navigation/routers');

function renderDone(){
  const calls=[];const pressables=[];
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  const Pressable=(props)=>{pressables.push(props);return React.createElement('div',{role:'button'},props.children);};
  // 화면이 다른 실행 맥락(vm)에서 만든 객체라 JSON 으로 옮겨 담아 비교한다.
  const record=(name)=>(...a)=>calls.push([name,...JSON.parse(JSON.stringify(a))]);
  const modules={react:React,
    'react-native':{View:Box,Text,Image:()=>null,Pressable,StyleSheet:{create:x=>x}},
    'react-native-safe-area-context':{SafeAreaView:Box},'expo-status-bar':{StatusBar:()=>null},
    'expo-linear-gradient':{LinearGradient:Box},
    '@react-navigation/native':{useNavigation:()=>({navigate:record('navigate'),popTo:record('popTo'),push:record('push')}),
      useRoute:()=>({params:{caseId:'c1'}})},
    '../theme/tokens':{color:{brand:'green'},type:{}}};
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..','src/screens/ReportDoneScreen.tsx'),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
  const out={exports:{}};
  vm.runInNewContext(source,{exports:out.exports,module:out,require:name=>modules[name]??{__esModule:true,default:()=>null}});
  const html=renderToStaticMarkup(React.createElement(out.exports.default));
  const press=(label)=>{
    const hit=pressables.find(p=>renderToStaticMarkup(React.createElement(React.Fragment,null,p.children)).includes(`<span>${label}</span>`));
    assert.ok(hit,`no button labelled ${label}`);
    hit.onPress();
  };
  return {html,press,calls};
}

test('the main button returns to the search map of the same case, the second one goes home', () => {
  const ui=renderDone();
  assert.ok(ui.html.indexOf('수색지도로 돌아가기')<ui.html.indexOf('홈으로'),'map first, home second');
  ui.press('수색지도로 돌아가기');
  ui.press('홈으로');
  assert.deepEqual(ui.calls,[['popTo','AlertSync',{caseId:'c1'}],['navigate','CitizenTabs',{screen:'Home'}]]);
});

test('the hint added in the first round stays', () => {
  assert.match(renderDone().html,/본 장소와 시각을 함께 알려 주시면\s*수색지도에 반영돼요/);
});

// ── 스택: 실제 라우터로 ──────────────────────────────────────────────
const ROUTES=['CitizenTabs','AlertDetail','AlertSync','Appearance','TipWarn','ReportChat','ReportDone'];
const router=StackRouter({});
const options={routeNames:ROUTES,routeParamList:{},routeGetIdList:{}};
function stackOf(...names){
  let state=router.getInitialState({...options,routeNames:ROUTES});
  state={...state,routes:names.map((name,i)=>({key:`${name}-${i}`,name,params:name==='CitizenTabs'?undefined:{caseId:'c1'}})),index:names.length-1};
  return state;
}
const names=(state)=>state.routes.map((r)=>r.name);

test('coming from the search map, the map underneath is reused — no second map on the stack', () => {
  // 지도 → 주의사항 → (replace) 제보 대화 → (replace) 완료. 제보 화면들은 replace 로 이어져 남지 않는다.
  const state=stackOf('CitizenTabs','AlertDetail','AlertSync','ReportDone');
  const next=router.getStateForAction(state,StackActions.popTo('AlertSync',{caseId:'c1'}),options);
  assert.deepEqual(names(next),['CitizenTabs','AlertDetail','AlertSync']);
  assert.equal(next.routes[2].key,'AlertSync-2','the same map screen, not a new one');
});

test('coming straight from the alert detail, the map takes the place of the done screen', () => {
  const state=stackOf('CitizenTabs','AlertDetail','ReportDone');
  const next=router.getStateForAction(state,StackActions.popTo('AlertSync',{caseId:'c1'}),options);
  assert.deepEqual(names(next),['CitizenTabs','AlertDetail','AlertSync']);
  assert.deepEqual(next.routes[2].params,{caseId:'c1'});
});

test('plain navigate would stack a second map — the reason the screen uses popTo', () => {
  const state=stackOf('CitizenTabs','AlertDetail','AlertSync','ReportDone');
  const next=router.getStateForAction(state,{type:'NAVIGATE',payload:{name:'AlertSync',params:{caseId:'c1'}}},options);
  assert.deepEqual(names(next),['CitizenTabs','AlertDetail','AlertSync','ReportDone','AlertSync']);
});

// ── 그사이 사건이 종결됐다면 ──────────────────────────────────────────
test('if the case ended meanwhile, the map says so and its home button clears the stack', () => {
  const calls=[];const pressables=[];
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  const Pressable=(props)=>{pressables.push(props);return React.createElement('div',{role:'button'},props.children);};
  class Value{constructor(v){this.v=v}addListener(){return 1}removeListener(){}setValue(){}}
  const native={View:Box,Text,ScrollView:Box,Pressable,ActivityIndicator:()=>null,Platform:{OS:'web'},
    StyleSheet:{create:x=>x},PanResponder:{create:()=>({panHandlers:{}})},Animated:{Value,View:Box,timing:()=>({start(){}})}};
  const modules={react:React,'react-native':native,
    '@react-navigation/native':{useNavigation:()=>({navigate:()=>calls.push('navigate'),canGoBack:()=>true,
      popToTop:()=>calls.push('popToTop'),reset:()=>calls.push('reset')}),useRoute:()=>({params:{caseId:'c1'}})},
    '../theme/tokens':{color:{figmaRed:'red'},type:{}},
    '../store/appModeStore':{useAppModeStore:Object.assign((sel)=>sel({enterSearch(){},closeCase(){}}),{getState:()=>({activeCaseId:'c1'})})},
    // 종결된 사건: 경보 목록에서 빠지고, 지도 조회가 "끝난 사건"을 알린다.
    '../hooks/queries':{useActiveAlerts:()=>({data:[]}),usePoaPrediction:()=>({data:undefined,ended:true,isLoading:false}),
      usePresenceCount:()=>null,useGuidance:()=>({data:undefined,isLoading:false})},
    '../data/missingView':{alertToView:()=>({title:'',meta:'',appearance:[]})},
    '../theme/tabBar':{useTabBarMetrics:()=>({height:80})},
    '../utils/guidanceLine':{guidanceLine:()=>''}};
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..','src/screens/AlertSyncScreen.tsx'),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
  const out={exports:{}};
  vm.runInNewContext(source,{React,exports:out.exports,module:out,require:name=>modules[name]??{__esModule:true,default:Box}});
  const html=renderToStaticMarkup(React.createElement(out.exports.default));
  assert.match(html,/종료된 사건이에요/);
  assert.doesNotMatch(html,/목격 내용 제보하기/);
  pressables.find(p=>p.accessibilityLabel==='홈으로 돌아가기').onPress();
  assert.deepEqual(calls,['popToTop']);
});
