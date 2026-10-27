// 시민 홈 — 주변에 진행 중 경보가 있으면 홈에서 바로 보이는가, 이번 달 문구가 지금 달을 말하는가.
//
// 10/27 측정: 주변에 진행 중 경보가 있어도 홈에는 아무 표시가 없었고(긴급 알림 탭을 알아서
// 눌러야 보임), 10월 캡처에서 "8월에는 총 …km를 걸었네요!"로 월이 고정돼 있었다.
//
// 화면 파일을 실제로 변환해 그리고(react-dom/server), 카드의 onPress 를 직접 눌러 본다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

function load(file,modules){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
  const out={exports:{}};
  vm.runInNewContext(source,{exports:out.exports,module:out,Date,
    require:name=>modules[name]??{__esModule:true,default:()=>null}});
  return out.exports;
}

const KINTEX={caseId:'a',area:'[고양시 일산서구] 킨텍스로',age:81,targetCells:['x']};
const MAPO={caseId:'b',area:'[서울특별시 마포구] 월드컵로',age:79,targetCells:['y']};

function render({alerts=[],dismissed={},now=Date.UTC(2026,9,27,4,0),monthKm=3.4}={}){
  const navigated=[];const pressables=[];
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  const Pressable=(props)=>{pressables.push(props);return React.createElement('div',{role:'button'},props.children);};
  const native={Platform:{OS:'web'},Alert:{alert(){}},View:Box,ScrollView:Box,Text,Pressable,RefreshControl:()=>null,
    ActivityIndicator:()=>null,StyleSheet:{create:x=>x}};
  const tokens={color:{brand:'green',figmaRed:'red',figmaGray:'gray'},type:{}};
  const modules={react:React,'react-native':native,'react-native-safe-area-context':{SafeAreaView:Box},
    'expo-status-bar':{StatusBar:()=>null},
    // 화면이 다른 실행 맥락(vm)에서 만든 객체라 JSON 으로 옮겨 담아 비교한다.
    '@react-navigation/native':{useNavigation:()=>({navigate:(...a)=>navigated.push(JSON.parse(JSON.stringify(a)))})},
    '../theme/tokens':tokens,
    '../hooks/queries':{useActiveAlerts:()=>({data:alerts}),useActiveWalk:()=>({}),
      useWalkStats:()=>({data:{month_km:monthKm},refetch(){}}),useNearbyWalks:()=>({data:[],refetch(){}}),useStartWalk:()=>({mutate(){}})},
    '../hooks/useMyLocation':{useMyLocation:()=>({status:'granted'}),isLocationSettled:()=>true,retryLocation(){}},
    '../store/appModeStore':{useAppModeStore:sel=>sel({dismissedCases:dismissed})},
    'react-native-maps':{Polyline:()=>null},
    // 판정 규칙과 카드는 진짜를 쓴다 — 이 시험이 보려는 것이 그것이다.
    '../utils/alertTitle':load('src/utils/alertTitle.ts',{}),
    '../utils/walkFormat':load('src/utils/walkFormat.ts',{}),
    '../components/AlertCard':load('src/components/AlertCard.tsx',{react:React,'react-native':native,'../theme/tokens':tokens})};
  const screen=load('src/screens/CitizenHomeScreen.tsx',modules);
  const realNow=Date.now;Date.now=()=>now;
  let html;
  try{html=renderToStaticMarkup(React.createElement(screen.default));}finally{Date.now=realNow;}
  const press=(match)=>{
    const hit=pressables.find(p=>match.test(p.accessibilityLabel??''));
    assert.ok(hit,`no button matching ${match}`);
    hit.onPress();
  };
  return {html,press,navigated};
}

test('one nearby alert shows a red card at the top that opens that alert', () => {
  const ui=render({alerts:[KINTEX]});
  assert.match(ui.html,/내 주변 수색 중/);
  assert.match(ui.html,/\[고양시 일산서구 킨텍스로\] 81세 실종 어르신/);
  assert.match(ui.html,/봤다면 바로 제보해 주세요/);
  assert.ok(ui.html.indexOf('내 주변 수색 중')<ui.html.indexOf('이번 달 나의 산책 기록'),'the card sits above the walk section');
  ui.press(/내 주변 수색 중/);
  assert.deepEqual(ui.navigated,[['AlertDetail',{caseId:'a'}]]);
});

test('two or more alerts add "외 N건" and open the alerts tab', () => {
  const ui=render({alerts:[KINTEX,MAPO]});
  assert.match(ui.html,/내 주변 수색 중 · 외 1건/);
  ui.press(/외 1건/);
  assert.deepEqual(ui.navigated,[['CitizenTabs',{screen:'Alerts'}]]);
});

test('no alerts, or only dismissed ones, leave the home as it was', () => {
  assert.doesNotMatch(render({alerts:[]}).html,/내 주변 수색 중/);
  assert.doesNotMatch(render({alerts:[KINTEX],dismissed:{a:1}}).html,/내 주변 수색 중/);
  // 하나를 끄면 남은 한 건이 바로 열리는 카드가 된다.
  const ui=render({alerts:[KINTEX,MAPO],dismissed:{a:1}});
  assert.doesNotMatch(ui.html,/외 \d건/);
  ui.press(/내 주변 수색 중/);
  assert.deepEqual(ui.navigated,[['AlertDetail',{caseId:'b'}]]);
});

test('the walk headline names the current month in Korea instead of a fixed August', () => {
  assert.match(render({now:Date.UTC(2026,9,27,4,0)}).html,/10월에는 총 3\.4km를 걸었네요!/);
  // 11/1 00:30 KST(= 10/31 15:30 UTC) — 한국에서는 이미 11월이다.
  assert.match(render({now:Date.UTC(2026,9,31,15,30)}).html,/11월에는 총/);
  assert.doesNotMatch(render().html,/8월에는/);
});
