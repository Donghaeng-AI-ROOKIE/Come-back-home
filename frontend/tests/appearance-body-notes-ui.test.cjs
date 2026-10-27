// 인상착의 '키/체형/소지품' 칸 — 숫자만 적힌 키·몸무게가 시민 화면에 이름 붙어 나오는가.
//
// 10/27 팀 점검(운영 사건 7ccf1a190cd3): 보호자가 네 번째 칸에 "160/50/검정 핸드백"이라고
// 적자 경보 상세 칩과 인상착의 화면에 "160/50/검정 핸드백"이 그대로 나왔다.
//
// 화면 파일을 실제로 변환해 그린다(react-dom/server).
// 경보 상세는 React 를 import 하지 않는 자동 JSX 라 jsx-runtime 으로 변환한다.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');

function load(file,modules){
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const out={exports:{}};
  vm.runInNewContext(source,{exports:out.exports,module:out,
    require:name=>modules[name]??{__esModule:true,default:()=>null}});
  return out.exports;
}

// 운영 사건의 report.appearance 를 경보 응답으로 옮긴 것(빈 칸 없음).
const CASE={caseId:'c1',age:81,area:'[군포시] 수리동',targetCells:['x'],
  appearance:['노란색 티','검정 바지','갈색 운동화','160/50/검정 핸드백'],
  appearanceColors:{top:'yellow',bottom:'black',shoes:'brown'}};

function render(file,alert=CASE){
  const calls=[];const pressables=[];
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  const Pressable=(props)=>{pressables.push(props);return React.createElement('div',{role:'button'},props.children);};
  const nav={navigate:(...a)=>calls.push(['navigate',...JSON.parse(JSON.stringify(a))]),goBack:()=>calls.push(['goBack'])};
  const modules={react:React,'react/jsx-runtime':require('react/jsx-runtime'),'react-native':{View:Box,Text,Pressable,StyleSheet:{create:x=>x}},
    'react-native-safe-area-context':{SafeAreaView:Box},'expo-status-bar':{StatusBar:()=>null},
    '@react-navigation/native':{useNavigation:()=>nav,useRoute:()=>({params:{caseId:'c1'}})},
    '../theme/tokens':{color:{figmaRed:'red',figmaGray:'gray'},type:{}},
    '../hooks/queries':{useActiveAlerts:()=>({data:[alert]}),useGoldenTime:()=>null,usePresenceCount:()=>null},
    '../store/appModeStore':{useAppModeStore:sel=>sel({enterSearch(){},dismissCase(){}})},
    '../store/engagementStore':{useEngagementStore:sel=>sel({recordDismissed(){}})},
    // 화면이 고르는 규칙은 진짜를 쓴다 — 이 시험이 보려는 것이 그것이다.
    '../data/missingView':load('src/data/missingView.ts',{})};
  // 수정 전 화면은 이 모듈을 부르지 않는다. 필요할 때만 읽는다.
  Object.defineProperty(modules,'../utils/bodyNotes',{get:()=>load('src/utils/bodyNotes.ts',{})});
  const screen=load(file,modules);
  const html=renderToStaticMarkup(React.createElement(screen.default));
  const press=(label)=>{
    const hit=pressables.find(p=>renderToStaticMarkup(React.createElement(React.Fragment,null,p.children))===`<span>${label}</span>`);
    assert.ok(hit,`no button labelled ${label}`);
    hit.onPress();
  };
  return {html,press,calls};
}

const spans=(html)=>[...html.matchAll(/<span>([^<]*)<\/span>/g)].map(m=>m[1]);

test('alert detail shows height, weight and the bag as separate tags, none cut off', () => {
  const tags=spans(render('src/screens/AlertDetailScreen.tsx').html);
  for (const tag of ['노란색 티','검정 바지','갈색 운동화','키 160cm','몸무게 50kg','검정 핸드백']) assert.ok(tags.includes(tag),`missing tag ${tag}`);
  assert.ok(!tags.includes('160/50/검정 핸드백'));
});

test('appearance screen names height and weight in the line under the clothing tags', () => {
  const tags=spans(render('src/screens/AppearanceScreen.tsx').html);
  assert.ok(tags.includes('키 160cm · 몸무게 50kg · 검정 핸드백'),tags.join(' | '));
  // seed 예시 꼴 — 단위가 붙은 키와 체형을 나눈다.
  const seed=spans(render('src/screens/AppearanceScreen.tsx',{...CASE,appearance:['회색 점퍼','검정 바지','흰색 운동화','160cm 마른 체형, 흰머리']}).html);
  assert.ok(seed.includes('키 160cm · 마른 체형 · 흰머리'),seed.join(' | '));
});

test('the figure reads a bare-number height and a handbag', () => {
  const bodyNotes=load('src/utils/bodyNotes.ts',{});
  const {appearanceAvatarProfile}=load('src/utils/appearanceAvatar.ts',{'./bodyNotes':bodyNotes});
  const colors={top:'yellow',bottom:'black',shoes:'brown'};
  const short=appearanceAvatarProfile(colors,['노란색 티','검정 바지','갈색 운동화','150/45/검정 핸드백']);
  assert.equal(short.heightScale,0.94);
  assert.deepEqual([...short.accessories],['bag']);
  // 단위를 붙인 예전 꼴도 그대로 읽힌다.
  assert.equal(appearanceAvatarProfile(colors,['180cm']).heightScale,1.04);
});
