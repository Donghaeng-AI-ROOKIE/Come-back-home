// 긴급 알림 목록 카드 — 인상착의 요약이 칩과 같은 이름(키·몸무게)으로 나오는가, 제목이 어절 단위로 꺾이는가.
//
// 10/28 12회차 C2: 경보 상세 칩은 "키 160cm · 몸무게 50kg"(#340)인데 목록 카드 본문은 서버 summary
// 원문 "…, 160/50/검정 핸드백" 그대로였고, 지역명이 들어간 제목이 "…81세 실종 어르 / 신"으로 꺾였다.
//
// 화면 파일을 실제로 변환해 그리고(react-dom/server), 카드에 넘긴 값과 style 을 data 속성으로 꺼내 본다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

function load(file,modules){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
  const out={exports:{}};
  vm.runInNewContext(source,{exports:out.exports,module:out,React,
    require:name=>modules[name]??{__esModule:true,default:()=>null}});
  return out.exports;
}

/** react-native 의 style 배열·함수를 한 객체로 편다. */
function flat(style){
  if(typeof style==='function')return flat(style({pressed:false}));
  if(Array.isArray(style))return Object.assign({},...style.map(flat));
  return style||{};
}

const tag=(name)=>({style,children})=>React.createElement(name,{'data-style':JSON.stringify(flat(style))},children);
const native={View:tag('div'),Text:tag('span'),Pressable:tag('button'),ScrollView:tag('section'),
  ActivityIndicator:()=>null,StyleSheet:{create:x=>x},Platform:{OS:'web'}};
const tokens={color:{figmaRed:'RED',figmaGray:'GRAY',brand:'BRAND'},type:{}};

test('the card title and body break between words and the card can grow', () => {
  const AlertCard=load('src/components/AlertCard.tsx',{react:React,'react-native':native,'../theme/tokens':tokens}).default;
  const html=renderToStaticMarkup(React.createElement(AlertCard,{tone:'red',badge:'수색 중',
    title:'[고양시 일산서구 한류월드로] 81세 실종 어르신',body:'회색 점퍼\n터치하여 예상 구역을 확인해 주세요.',onPress(){}}));
  const styles=[...html.matchAll(/<(div|span|button) data-style="([^"]*)">([^<]*)/g)]
    .map(m=>({tag:m[1],style:JSON.parse(m[2].replace(/&quot;/g,'"')),text:m[3]}));
  const title=styles.find(s=>s.text.startsWith('[고양시'));
  const body=styles.find(s=>s.text.startsWith('회색 점퍼'));
  assert.equal(title.style.wordBreak,'keep-all');
  assert.equal(body.style.wordBreak,'keep-all');
  const card=styles.find(s=>s.tag==='button').style;
  assert.equal(card.minHeight,139);
  assert.equal(card.height,undefined);
});

test('the list card body names height and weight like the detail chips', () => {
  const cards=[];
  const modules={react:React,'react-native':native,'../theme/tokens':tokens,
    'react-native-safe-area-context':{SafeAreaView:tag('main')},
    'expo-status-bar':{StatusBar:()=>null},
    '@react-navigation/native':{useNavigation:()=>({navigate(){}})},
    '../hooks/queries':{useActiveAlerts:()=>({data:[{caseId:'c1',area:'[고양시 일산서구] 한류월드로',age:81,
      targetCells:new Array(80).fill('x'),summary:'회색 점퍼, 검은 바지, 흰 운동화, 160/50/검정 핸드백'}],
      isLoading:false,isError:false,refetch(){}}),useResolvedAlerts:()=>({data:[]})},
    '../hooks/useMyLocation':{useMyLocation:()=>({point:{lat:37.66,lng:126.75},status:'granted'}),isLocationSettled:()=>true,retryLocation(){}},
    '../store/appModeStore':{useAppModeStore:sel=>sel({dismissedCases:{}})},
    '../utils/resolvedCopy':load('src/utils/resolvedCopy.ts',{}),
    '../utils/alertTitle':load('src/utils/alertTitle.ts',{}),
    '../utils/bodyNotes':load('src/utils/bodyNotes.ts',{}),
    '../components/AlertCard':{__esModule:true,default:(props)=>{cards.push(props);return null;}}};
  const Screen=load('src/screens/CitizenAlertsScreen.tsx',modules).default;
  renderToStaticMarkup(React.createElement(Screen));
  assert.equal(cards.length,1);
  assert.equal(cards[0].body,'회색 점퍼, 검은 바지, 흰 운동화, 키 160cm, 몸무게 50kg, 검정 핸드백\n터치하여 예상 구역을 확인해 주세요.');
  assert.doesNotMatch(cards[0].body,/160\/50/);
});
