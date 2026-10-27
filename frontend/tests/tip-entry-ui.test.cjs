// 제보로 들어가는 길이 하나로 모이는가 — 어느 버튼으로 들어와도 허위 제보 주의사항(TipWarn)을 거치는가.
//
// 10/27 측정: 경보 상세의 '봤어요'는 TipWarn 을 거치는데, 수색지도(AlertSync)의
// '목격 내용 제보하기'는 곧바로 ReportChat 으로 갔다.
//
// 화면 파일을 실제로 변환해 그리고(react-dom/server), 버튼의 onPress 를 직접 눌러 본다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

function load(file,context){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
  const out={exports:{}};
  vm.runInNewContext(source,{...context,exports:out.exports,module:out});
  return out.exports;
}

function renderAlertSync(){
  const navigated=[];const pressables=[];
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  const Pressable=(props)=>{pressables.push(props);return React.createElement('div',{role:'button'},props.children);};
  class Value{constructor(v){this.v=v}addListener(){return 1}removeListener(){}setValue(){}}
  const native={View:Box,Text,ScrollView:Box,Pressable,ActivityIndicator:()=>null,Platform:{OS:'web'},
    StyleSheet:{create:x=>x},PanResponder:{create:()=>({panHandlers:{}})},
    Animated:{Value,View:Box,timing:()=>({start(){}})}};
  const alert={caseId:'c1',lkp:{lat:37.6652,lng:126.7483},appearance:[],appearanceColors:{}};
  const modules={react:React,'react-native':native,
    // 화면이 다른 실행 맥락(vm)에서 만든 객체라 JSON 으로 옮겨 담아 비교한다.
    '@react-navigation/native':{useNavigation:()=>({navigate:(...a)=>navigated.push(JSON.parse(JSON.stringify(a))),canGoBack:()=>true,popToTop(){}}),
      useRoute:()=>({params:{caseId:'c1'}})},
    '../theme/tokens':{color:{figmaRed:'red'},type:{}},
    '../store/appModeStore':{useAppModeStore:(sel)=>sel({enterSearch(){},closeCase(){},activeCaseId:'c1'})},
    '../hooks/queries':{useActiveAlerts:()=>({data:[alert]}),usePoaPrediction:()=>({data:undefined,ended:false,isLoading:false}),
      usePresenceCount:()=>null,useGuidance:()=>({data:undefined,isLoading:false})},
    '../data/missingView':{alertToView:()=>({title:'81세 어르신',meta:'내 주변 인근',appearance:[]})},
    '../theme/tabBar':{useTabBarMetrics:()=>({height:80})},
    '../utils/guidanceLine':{guidanceLine:()=>'지도에서 색이 진한 곳부터 살펴봐 주세요.'}};
  // 화면 파일은 React 를 import 하지 않는다(새 JSX 변환) — 변환 결과가 쓰는 React 를 넣어 준다.
  const screen=load('src/screens/AlertSyncScreen.tsx',{React,require:name=>modules[name]??{__esModule:true,default:Box}});
  renderToStaticMarkup(React.createElement(screen.default));
  const press=(label)=>{
    const hit=pressables.find(p=>renderToStaticMarkup(React.createElement(React.Fragment,null,p.children)).includes(label));
    assert.ok(hit,`no button labelled ${label}`);
    hit.onPress();
  };
  return {press,navigated};
}

test('the search map report button goes through the tip warning, like "봤어요" on the alert detail', () => {
  const ui=renderAlertSync();
  ui.press('목격 내용 제보하기');
  assert.deepEqual(ui.navigated,[['TipWarn',{caseId:'c1'}]]);
});
