// 보호자 홈 — 신고 뒤에 홈이 "수색 중"임을 알려 주는가, 같은 가족을 바로 두 번 신고하게 두지 않는가.
//
// 10/27 측정: 신고 뒤에도 홈이 신고 전과 같았고(지도·제보는 "알림" 탭을 알아서 눌러야 보임),
// "실종 신고" 버튼이 그대로라 곧바로 두 번째 신고 화면이 열렸다.
//
// 화면 파일을 실제로 변환해 그리고(react-dom/server), 버튼의 onPress 를 직접 눌러 본다.
// useState 는 렌더 사이에 값을 이어 주는 작은 대역으로 바꾼다 — 정적 렌더는 상태를 들고 있지 않는다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

function load(file,modules){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
  const out={exports:{}};
  vm.runInNewContext(source,{exports:out.exports,module:out,Date,setInterval,clearInterval,
    require:name=>modules[name]??{__esModule:true,default:()=>null}});
  return out.exports;
}

// 서버 시각(오프셋 없는 UTC): 03:00 신고, 화면 시각 04:20 → 경과 1시간 20분.
const NOW=Date.UTC(2026,9,27,4,20);
const ACTIVE={id:'c1',status:'searching',created_at:'2026-10-27T03:00:00',area_label:'[고양시 일산서구] 킨텍스로',
  report:{persona_id:'p1'},tips:[{id:'t1'},{id:'t2'}]};

function mount({cases,seenTips={}}){
  const navigated=[];
  let slots=[];let cursor=0;
  const hooks={...React,
    useState:init=>{const k=cursor++;if(!(k in slots))slots[k]=typeof init==='function'?init():init;
      return [slots[k],v=>{slots[k]=typeof v==='function'?v(slots[k]):v;}];},
    useEffect:()=>{},useCallback:fn=>fn};
  let pressables=[];
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  const Pressable=(props)=>{pressables.push(props);return React.createElement('div',{role:'button'},props.children);};
  const native={View:Box,Text,ScrollView:Box,Pressable,ActivityIndicator:()=>null,StyleSheet:{create:x=>x}};
  const tokens={color:{guardian:'green',critical:'red',figmaRed:'red',figmaField:'#eee',figmaGray:'gray'},type:{}};
  const AlertCard=load('src/components/AlertCard.tsx',{react:React,'react-native':native,'../theme/tokens':tokens});
  const modules={react:hooks,'react-native':native,
    'react-native-safe-area-context':{SafeAreaView:Box},'expo-status-bar':{StatusBar:()=>null},
    // 화면이 다른 실행 맥락(vm)에서 만든 객체라 JSON 으로 옮겨 담아 비교한다.
    '@react-navigation/native':{useNavigation:()=>({navigate:(...a)=>navigated.push(JSON.parse(JSON.stringify(a)))}),useFocusEffect:()=>{}},
    '../theme/tokens':tokens,
    '../store/guardianStore':{useGuardianStore:sel=>sel({persona:null})},
    '../store/guardianCaseStore':{useGuardianCaseStore:sel=>sel({seenTips})},
    '../hooks/queries':{usePersonas:()=>({data:[{id:'p1',name:'김영희',age:81}],isLoading:false,isError:false,refetch(){}}),
      usePersonaStatus:()=>({data:{persona_status:'complete'}}),useGuardianCases:()=>({data:cases})},
    // 판정 규칙은 진짜를 쓴다 — 이 시험이 보려는 것이 그 규칙이다.
    '../utils/guardianSearchCard':load('src/utils/guardianSearchCard.ts',{}),
    '../components/AlertCard':AlertCard};
  const realNow=Date.now;Date.now=()=>NOW;
  let screen;
  try{screen=load('src/screens/GuardianHomeScreen.tsx',modules);}finally{Date.now=realNow;}
  const render=()=>{
    cursor=0;pressables=[];
    Date.now=()=>NOW;
    try{return renderToStaticMarkup(React.createElement(screen.default));}finally{Date.now=realNow;}
  };
  const press=(match)=>{
    const hit=pressables.find(p=>match.test(p.accessibilityLabel??'')||match.test(renderToStaticMarkup(React.createElement(React.Fragment,null,p.children))));
    assert.ok(hit,`no button matching ${match}`);
    hit.onPress();
  };
  return {render,press,navigated};
}

test('with an ongoing case the home shows a "searching" card that opens the alerts tab',()=>{
  const ui=mount({cases:[ACTIVE],seenTips:{c1:['t1']}});
  const html=ui.render();
  assert.match(html,/수색 중/);
  assert.match(html,/김영희 님 수색 중 · 경과 1시간 20분/);
  assert.match(html,/새 제보 1건 · 지도는 15초마다 갱신돼요/);
  ui.press(/김영희 님 수색 중/);
  assert.deepEqual(ui.navigated,[['GuardianTabs',{screen:'GuardianAlerts'}]]);
});

test('with an ongoing case "실종 신고" asks first instead of opening a second report',()=>{
  const ui=mount({cases:[ACTIVE]});
  ui.render();
  ui.press(/긴급 실종 신고/);
  assert.deepEqual(ui.navigated,[],'the report screen must not open straight away');
  const html=ui.render();
  assert.match(html,/이미 수색 중인 사건이 있어요\./);
  ui.press(/^<span>수색 화면 보기<\/span>$/);
  assert.deepEqual(ui.navigated,[['GuardianTabs',{screen:'GuardianAlerts'}]]);
  // 확인을 닫았으므로 다시 그리면 안내가 없다.
  assert.doesNotMatch(ui.render(),/이미 수색 중인 사건이 있어요/);
});

test('"새로 신고하기" still opens the report screen — another family member may be missing',()=>{
  const ui=mount({cases:[ACTIVE]});
  ui.render();
  ui.press(/긴급 실종 신고/);
  ui.render();
  ui.press(/^<span>새로 신고하기<\/span>$/);
  assert.deepEqual(ui.navigated,[['Report']]);
});

test('without an ongoing case nothing changes: no card, and "실종 신고" opens the report screen',()=>{
  const closed={...ACTIVE,status:'found'};
  const ui=mount({cases:[closed]});
  const html=ui.render();
  assert.doesNotMatch(html,/수색 중/);
  ui.press(/긴급 실종 신고/);
  assert.deepEqual(ui.navigated,[['Report']]);
});
