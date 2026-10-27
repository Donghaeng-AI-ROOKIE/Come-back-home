// 시민 수색지도(AlertSync)의 수색 안내 줄 — "불러오고 있습니다"가 영원히 남지 않는가.
//
// 10/27 운영(사건 c93122664ff2): GET /phase3/cases/{id}/guidance 가 3초 만에 200 으로
// {guidance: "", pending: false} 를 돌려줬고(서버 검증이 템플릿을 거절하면 빈 문자열),
// 화면은 60초 내내 "사건에 맞는 수색 안내를 불러오고 있습니다."였다. 조회가 실패해도
// (retry:false, data 없음) 같은 문구가 남는다.
//
// 화면 파일을 실제로 변환해 그리고(react-dom/server), 안내 조회 상태만 바꿔 본다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

const LOADING=/사건에 맞는 수색 안내를 불러오고 있습니다/;

function load(file,context){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
  const out={exports:{}};
  vm.runInNewContext(source,{...context,exports:out.exports,module:out});
  return out.exports;
}

function render(guidance){
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  class Value{constructor(v){this.v=v}addListener(){return 1}removeListener(){}setValue(){}}
  const native={View:Box,Text,ScrollView:Box,Pressable:Box,ActivityIndicator:()=>null,Platform:{OS:'web'},
    StyleSheet:{create:x=>x},PanResponder:{create:()=>({panHandlers:{}})},
    Animated:{Value,View:Box,timing:()=>({start(){}})}};
  const alert={caseId:'c1',lkp:{lat:37.6652,lng:126.7483},appearance:[],appearanceColors:{}};
  const modules={react:React,'react-native':native,
    '@react-navigation/native':{useNavigation:()=>({navigate(){},canGoBack:()=>true,popToTop(){}}),useRoute:()=>({params:{caseId:'c1'}})},
    '../theme/tokens':{color:{figmaRed:'red'},type:{}},
    '../store/appModeStore':{useAppModeStore:(sel)=>sel({enterSearch(){},closeCase(){},activeCaseId:'c1'})},
    '../hooks/queries':{useActiveAlerts:()=>({data:[alert]}),usePoaPrediction:()=>({data:undefined,ended:false,isLoading:false}),
      usePresenceCount:()=>null,useGuidance:()=>guidance},
    '../data/missingView':{alertToView:()=>({title:'81세 어르신',meta:'내 주변 인근',appearance:[]})},
    '../theme/tabBar':{useTabBarMetrics:()=>({height:80})},
    // 판정 규칙은 진짜를 쓴다 — 이 시험이 보려는 것이 그 규칙이다.
    '../utils/guidanceLine':load('src/utils/guidanceLine.ts',{})};
  // 화면 파일은 React 를 import 하지 않는다(새 JSX 변환) — 변환 결과가 쓰는 React 를 넣어 준다.
  const screen=load('src/screens/AlertSyncScreen.tsx',{React,require:name=>modules[name]??{__esModule:true,default:Box}});
  return renderToStaticMarkup(React.createElement(screen.default));
}

test('while the first guidance request is in flight the loading line is shown',()=>{
  assert.match(render({data:undefined,isLoading:true,isError:false}),LOADING);
});

test('an empty answer from the server does not leave the loading line forever',()=>{
  const html=render({data:{text:'',personalized:true,pending:false},isLoading:false,isError:false});
  assert.doesNotMatch(html,LOADING);
  assert.match(html,/지도에서 색이 진한 곳부터 살펴봐 주세요/);
});

test('a failed request does not leave the loading line forever either',()=>{
  const html=render({data:undefined,isLoading:false,isError:true});
  assert.doesNotMatch(html,LOADING);
  assert.match(html,/지도에서 색이 진한 곳부터 살펴봐 주세요/);
});

test('real guidance text is shown as is',()=>{
  const text='아직 멀리 가지 못하셨을 거예요. 최종 목격 장소에서 걸어서 10분 안쪽을 먼저 봐주세요.';
  const html=render({data:{text,personalized:false,pending:false},isLoading:false,isError:false});
  assert.ok(html.includes(text));
  assert.doesNotMatch(html,LOADING);
});
