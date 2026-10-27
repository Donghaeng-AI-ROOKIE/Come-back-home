// 제보 접수 완료 화면 — 위치 없는 제보는 수색지도에 반영되지 않는다는 것을 시민이 알 수 있는가.
// 화면 파일을 실제로 변환해 그리고(react-dom/server), 문구를 확인한다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

function render(){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..','src/screens/ReportDoneScreen.tsx'),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  const modules={react:React,
    'react-native':{View:Box,Text,Image:()=>null,Pressable:Box,StyleSheet:{create:x=>x}},
    'react-native-safe-area-context':{SafeAreaView:Box},'expo-status-bar':{StatusBar:()=>null},
    'expo-linear-gradient':{LinearGradient:Box},'@react-navigation/native':{useNavigation:()=>({navigate(){},popTo(){}}),useRoute:()=>({params:{caseId:'c1'}})},
    '../theme/tokens':{color:{brand:'green'},type:{}}};
  const out={exports:{}};
  vm.runInNewContext(source,{exports:out.exports,module:out,require:name=>modules[name]??{__esModule:true,default:()=>null}});
  return renderToStaticMarkup(React.createElement(out.exports.default));
}

test('the done screen says that place and time are what put a tip on the search map',()=>{
  const html=render();
  assert.match(html,/본 장소와 시각을 함께 알려 주시면\s*수색지도에 반영돼요/);
});

test('the hint is general — the screen does not claim this tip was or was not used',()=>{
  // 판정은 접수 뒤 서버에서 돈다(ReportChatScreen → 접수 응답 → 뒤에서 분석). 완료 화면은 결과를 모른다.
  const html=render();
  assert.doesNotMatch(html,/반영되지 않았|반영됐어요|반영되었/);
  assert.match(html,/제보 접수 완료/);
});
