// 허위 제보 주의사항(TipWarn) — "봤어요"를 누르고 온 사람에게 다시 봤는지 묻지 않는가.
//
// 10/27 측정: 경보 상세에서 '봤어요'를 누르면 주의사항 화면이 "비슷한 사람을 봤어요 / 보지
// 못했어요"를 다시 물었다. 인상착의 화면의 [비슷한 사람을 봤어요]는 인상착의를 보고 판단하는 자리라
// 그대로 두고, 아래 회색 버튼은 하는 일대로 [이전 화면으로 돌아가기]라고 쓴다(10/27 팀 점검).
//
// 화면 파일을 실제로 변환해 그리고(react-dom/server), 버튼의 onPress 를 직접 눌러 본다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

function transpile(file){
  return ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
}

function loadUtil(file){
  const out={exports:{}};
  vm.runInNewContext(transpile(file),{exports:out.exports,module:out});
  return out.exports;
}

function render(file){
  const calls=[];const pressables=[];
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  const Pressable=(props)=>{pressables.push(props);return React.createElement('div',{role:'button'},props.children);};
  const nav={replace:(...a)=>calls.push(['replace',...JSON.parse(JSON.stringify(a))]),
    navigate:(...a)=>calls.push(['navigate',...JSON.parse(JSON.stringify(a))]),goBack:()=>calls.push(['goBack'])};
  const modules={react:React,'react-native':{View:Box,Text,Pressable,StyleSheet:{create:x=>x}},
    'react-native-safe-area-context':{SafeAreaView:Box},'expo-status-bar':{StatusBar:()=>null},
    '@react-navigation/native':{useNavigation:()=>nav,useRoute:()=>({params:{caseId:'c1'}})},
    '../theme/tokens':{color:{figmaRed:'red',figmaGray:'gray'},type:{}},
    '../hooks/queries':{useActiveAlerts:()=>({data:[]})},
    '../data/missingView':{alertToView:()=>({appearance:[]})},
    '../utils/bodyNotes':loadUtil('src/utils/bodyNotes.ts')};
  const source=transpile(file);
  const out={exports:{}};
  vm.runInNewContext(source,{exports:out.exports,module:out,require:name=>modules[name]??{__esModule:true,default:()=>null}});
  const html=renderToStaticMarkup(React.createElement(out.exports.default));
  const press=(label)=>{
    const hit=pressables.find(p=>renderToStaticMarkup(React.createElement(React.Fragment,null,p.children))===`<span>${label}</span>`);
    assert.ok(hit,`no button labelled ${label}`);
    hit.onPress();
  };
  return {html,press,calls};
}

test('the warning screen asks for consent to the notice, not whether the person was seen again', () => {
  const ui=render('src/screens/TipWarnScreen.tsx');
  assert.match(ui.html,/주의사항 확인하고 제보하기/);
  assert.match(ui.html,/<span>취소<\/span>/);
  assert.doesNotMatch(ui.html,/비슷한 사람을 봤어요|비슷한 사람을 보지 못했어요/);
});

test('confirming opens the tip chat in place of the warning, cancelling goes back', () => {
  const ui=render('src/screens/TipWarnScreen.tsx');
  ui.press('주의사항 확인하고 제보하기');
  ui.press('취소');
  assert.deepEqual(ui.calls,[['replace','ReportChat',{caseId:'c1'}],['goBack']]);
});

test('the appearance screen keeps its "seen a similar person" question and leads to the warning', () => {
  const ui=render('src/screens/AppearanceScreen.tsx');
  assert.match(ui.html,/비슷한 사람을 봤어요/);
  assert.match(ui.html,/이전 화면으로 돌아가기/);
  assert.doesNotMatch(ui.html,/비슷한 사람을 보지 못했어요/);
  ui.press('비슷한 사람을 봤어요');
  assert.deepEqual(ui.calls,[['navigate','TipWarn',{caseId:'c1'}]]);
});
