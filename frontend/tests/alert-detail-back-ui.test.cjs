// 경보 상세(AlertDetail) — 회색 버튼이 하는 일 그대로 [이전 화면으로 돌아가기]라고 쓰는가.
//
// 10/28 팀 점검: [못 봤어요]는 실제로 뒤로 가기만 한다. 인상착의 화면의 [비슷한 사람을 보지
// 못했어요]를 #340 에서 [이전 화면으로 돌아가기]로 바꿨는데, 경보 상세의 같은 버튼은 그대로였다.
//
// 화면 파일을 실제로 변환해 그리고(react-dom/server), 버튼의 onPress 를 직접 눌러 본다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

function transpile(file){
  return ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
}

function loadUtil(file){
  const out={exports:{}};
  vm.runInNewContext(transpile(file),{exports:out.exports,module:out});
  return out.exports;
}

function render(){
  const calls=[];const pressables=[];
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  const Pressable=(props)=>{pressables.push(props);return React.createElement('div',{role:'button'},props.children);};
  const nav={navigate:(...a)=>calls.push(['navigate',...JSON.parse(JSON.stringify(a))]),goBack:()=>calls.push(['goBack'])};
  const store=(state)=>(select)=>select(state);
  // 이 화면은 React 기본 내보내기를 import 하지 않는다(새 JSX 변환) — jsx-runtime 을 넘긴다.
  const modules={react:React,'react/jsx-runtime':require('react/jsx-runtime'),'react-native':{View:Box,Text,Pressable,StyleSheet:{create:x=>x}},
    '@react-navigation/native':{useNavigation:()=>nav,useRoute:()=>({params:{caseId:'c1'}})},
    '../theme/tokens':{color:{figmaRed:'red',figmaGray:'gray'},type:{}},
    '../store/appModeStore':{useAppModeStore:store({enterSearch:()=>{},dismissCase:()=>{}})},
    '../store/engagementStore':{useEngagementStore:store({recordDismissed:()=>{}})},
    '../hooks/queries':{useActiveAlerts:()=>({data:[]}),useGoldenTime:()=>null,usePresenceCount:()=>null},
    '../data/missingView':{alertToView:()=>({appearance:[]})},
    '../utils/bodyNotes':loadUtil('src/utils/bodyNotes.ts')};
  const out={exports:{}};
  vm.runInNewContext(transpile('src/screens/AlertDetailScreen.tsx'),{exports:out.exports,module:out,require:name=>modules[name]??{__esModule:true,default:()=>null}});
  const html=renderToStaticMarkup(React.createElement(out.exports.default));
  const press=(label)=>{
    const hit=pressables.find(p=>renderToStaticMarkup(React.createElement(React.Fragment,null,p.children))===`<span>${label}</span>`);
    assert.ok(hit,`no button labelled ${label}`);
    hit.onPress();
  };
  return {html,press,calls};
}

test('the grey button on the alert detail says what it does: go back', () => {
  const ui=render();
  assert.match(ui.html,/<span>봤어요<\/span>/);
  assert.match(ui.html,/<span>이전 화면으로 돌아가기<\/span>/);
  assert.doesNotMatch(ui.html,/못 봤어요/);
});

test('"봤어요" still leads to the warning and the grey button only goes back', () => {
  const ui=render();
  ui.press('봤어요');
  ui.press('이전 화면으로 돌아가기');
  assert.deepEqual(ui.calls,[['navigate','TipWarn',{caseId:'c1'}],['goBack']]);
});
