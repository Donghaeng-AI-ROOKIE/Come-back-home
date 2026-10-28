// 보호자 알림 탭의 사건 관리 카드 — 진행 중 사건은 긴급 모드 빨강 톤인가, 종결 사건은 회색 그대로인가.
//
// 10/28 화면흐름 보드 의견: 하단 탭은 빨강(#342)인데 바로 위 사건 관리 카드의 "수색 중" 배지와
// [가족을 찾았어요]가 보호자 초록이라, 긴급 상황이 끝난 것처럼 읽혔다.
//
// 화면 파일을 실제로 변환해 그리고(react-dom/server), 각 요소의 style 을 data 속성으로 꺼내 본다.
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

const tokens={color:{guardian:'GREEN',figmaRed:'RED'},type:{}};
const ACTIVE={id:'live',status:'searching',created_at:'2026-10-27T03:00:00',tips:[]};
const CLOSED={id:'done',status:'found',created_at:'2026-10-26T03:00:00',tips:[]};

/** 카드 하나를 그리고, 바탕·배지·버튼의 style 을 돌려준다. */
function renderCard(item){
  const tag=(name)=>({style,children})=>React.createElement(name,{'data-style':JSON.stringify(flat(style))},children);
  const native={View:tag('div'),Text:tag('span'),Pressable:tag('button'),StyleSheet:{create:x=>x}};
  const modules={react:React,'react-native':native,'../theme/tokens':tokens,
    '@tanstack/react-query':{useQueryClient:()=>({})},'../api/guardian':{},
    '../store/authStore':{useAuthStore:sel=>sel({userId:'owner-1'})},
    '../utils/caseRefresh':{refreshAfterCaseChange:async()=>{}},
    '../utils/walkFormat':load('src/utils/walkFormat.ts',{})};
  const {CaseLifecycleCard}=load('src/components/LifecycleControls.tsx',modules);
  const html=renderToStaticMarkup(React.createElement(CaseLifecycleCard,{item}));
  const styles=[...html.matchAll(/<(div|span|button) data-style="([^"]*)">/g)]
    .map(m=>({tag:m[1],style:JSON.parse(m[2].replace(/&quot;/g,'"'))}));
  // 맨 바깥 div 가 카드 바탕, 그 안 첫 div 가 배지, 배지 안 첫 span 이 배지 글자다.
  return {html,card:styles[0].style,badge:styles[1].style,badgeText:styles[2].style,
    buttons:styles.filter(s=>s.tag==='button').map(s=>s.style)};
}

test('an ongoing case card is red like the home "수색 중" card and the red tabs', () => {
  const ui=renderCard(ACTIVE);
  assert.match(ui.html,/수색 중/);
  assert.equal(ui.card.backgroundColor,'#FFF0F1');
  assert.equal(ui.badge.backgroundColor,'#FFC9CB');
  assert.equal(ui.badgeText.color,'RED');
  // 첫 버튼이 [가족을 찾았어요], 둘째가 [신고 철회](흰 바탕 그대로).
  assert.equal(ui.buttons[0].backgroundColor,'RED');
  assert.equal(ui.buttons[1].backgroundColor,'#FFFFFF');
  assert.doesNotMatch(JSON.stringify([ui.card,ui.badge,ui.badgeText,...ui.buttons]),/GREEN|#B0DB9C|#316837/);
});

test('a closed case card stays grey', () => {
  const ui=renderCard(CLOSED);
  assert.match(ui.html,/종결/);
  assert.equal(ui.card.backgroundColor,'#F7F7F7');
  assert.equal(ui.badge.backgroundColor,'#E2E2E2');
  assert.equal(ui.badgeText.color,'#6B6B70');
});
