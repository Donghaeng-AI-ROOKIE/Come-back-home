/** 데모 데이터 — 디자인 확정본(claude.ai/design S1·S2)과 동일한 값.
 *  백엔드 미기동 시 화면 시연·스크린샷용. 김순자 케이스만 실 시드와 대응하고
 *  나머지 카드는 보드 레이아웃 시연용 샘플(화면에 각주로 명시). */

export type DemoView = "loading" | "tips3" | "d3" | "closed";
export type PanelTab = "profile" | "timeline" | "manage";
export type PoaLayer = "combined" | "top_down" | "bottom_up" | "statistical";

export interface DemoCard {
  name: string;
  age: number;
  type: "치매" | "발달장애";
  baseSec: number; // 경과시간 시작값(초) — 틱마다 +1
  status: string;
  tone: "amber" | "red" | "accent" | "green";
  lkp: string;
  lastAlert: string;
  featured: boolean;
  closed: boolean;
}

export const DEMO_CARDS: DemoCard[] = [
  { name: "김순자", age: 78, type: "치매", baseSec: 9680, status: "제보 3건", tone: "amber", lkp: "정릉2동 정릉시장 인근", lastAlert: "08:53 · D2", featured: true, closed: false },
  { name: "최정자", age: 76, type: "치매", baseSec: 24630, status: "알림발송 · D3", tone: "red", lkp: "정릉3동 북한산 방면", lastAlert: "07:10 · D3", featured: false, closed: false },
  { name: "이말순", age: 82, type: "치매", baseSec: 15165, status: "알림발송 · D2", tone: "red", lkp: "길음동 지하철역", lastAlert: "06:40 · D2", featured: false, closed: false },
  { name: "박영수", age: 71, type: "치매", baseSec: 2292, status: "예측완료", tone: "accent", lkp: "정릉1동 주민센터", lastAlert: "—", featured: false, closed: false },
  { name: "정도현", age: 24, type: "발달장애", baseSec: 725, status: "접수", tone: "amber", lkp: "돈암동 성신여대입구", lastAlert: "대기", featured: false, closed: false },
  { name: "강병철", age: 68, type: "치매", baseSec: 0, status: "종결 · 발견", tone: "green", lkp: "정릉4동 우이천", lastAlert: "09:58 · 발견", featured: false, closed: true },
];

export interface DemoTimelineEvent {
  t: string;
  tag: string;
  tone: "red" | "amber" | "green" | "accent" | "gray";
  sim?: boolean;
  title: string;
  desc: string;
  p?: number;
  verdict?: "layer1" | "layer2" | "discard";
}

/** 제보 번호는 도착 시간순(#1 09:07 → #2 09:14 → #3 09:20) — 지도 핀 번호와 일치 */
export function demoTimeline(view: DemoView): DemoTimelineEvent[] {
  const base: DemoTimelineEvent[] = [
    { t: "08:32", tag: "접수", tone: "amber", title: "실종 신고 접수", desc: "보호자 전화 접수 · 최종 목격 08:00 정릉2동" },
    { t: "08:33", tag: "D1", tone: "red", sim: true, title: "반경 즉시경보(D1) 발송", desc: "LKP 반경 target_cells=19셀 발송 (sent=false)" },
  ];
  if (view === "loading") {
    return [...base, { t: "08:34", tag: "예측", tone: "accent", title: "AI 예측 실행 중…", desc: "500 워커 시뮬레이션 진행 중 (17–27초 소요)" }];
  }
  const rest: DemoTimelineEvent[] = [
    { t: "08:51", tag: "예측", tone: "accent", title: "AI 예측 완료", desc: "500 워커 시뮬레이션 · 4층 POA 생성 (18.4초)" },
    { t: "08:53", tag: "D2", tone: "red", sim: true, title: "예측기반 경보(D2) 발송", desc: "상위 확률 target_cells=34셀 발송 (sent=false)" },
    { t: "09:07", tag: "제보", tone: "amber", title: "제보 #1 — 정릉시장 입구", desc: "\"회색 점퍼 할머니를 봤어요\"", p: 0.61, verdict: "layer1" },
    { t: "09:14", tag: "제보", tone: "gray", title: "제보 #2 — 미아사거리 방면", desc: "유사 인상착의 문의", p: 0.13, verdict: "discard" },
    { t: "09:20", tag: "제보", tone: "red", title: "제보 #3 — 북한산 입구", desc: "\"북한산 입구 쪽으로 걸어가시는 걸 봤어요\"", p: 0.87, verdict: "layer2" },
    { t: "09:21", tag: "재예측", tone: "accent", title: "제보 반영 재예측 실행", desc: "층2 트리거 · POA 갱신 완료" },
  ];
  const items = [...base, ...rest];
  if (view === "d3") {
    items.push(
      { t: "09:44", tag: "제보", tone: "red", title: "제보 #4 — 정릉4동 우이천", desc: "\"천변에서 지팡이 짚은 분\"", p: 0.83, verdict: "layer2" },
      { t: "09:45", tag: "D3", tone: "red", sim: true, title: "신규 지역 발생 — D3 발송 권고", desc: "우이천 신규 클러스터 · rerun-check 트리거" },
    );
  }
  if (view === "closed") {
    items.push({ t: "10:12", tag: "종결", tone: "green", title: "케이스 종결 — 안전 발견", desc: "정릉4동 우이천 산책로 · 개인정보 5일 후 자동 파기 예약" });
  }
  return items;
}

export interface DemoAlert {
  code: "D1" | "D2" | "D3";
  name: string;
  cells: number;
  reach: string; // 도달 추정 — API에 없는 값이라 "(데모)" 라벨 필수
  time: string;
  pending?: boolean;
}

export function demoAlerts(view: DemoView): DemoAlert[] {
  const a: DemoAlert[] = [
    { code: "D1", name: "반경 즉시경보", cells: 19, reach: "약 1,240명", time: "08:33" },
    { code: "D2", name: "예측기반 경보", cells: 34, reach: "약 3,180명", time: "08:53" },
  ];
  if (view === "d3") a.push({ code: "D3", name: "신규 지역 경보", cells: 21, reach: "약 1,760명", time: "—", pending: true });
  if (view === "loading") return a.slice(0, 1);
  return a;
}

/** 데모 페르소나 축 점수 — 실축 필드명 사용(디자인 목업의 단순화 명칭 대체) */
export const DEMO_AXIS_SCORES: Record<string, number> = {
  mobility_transport_capacity: 0.62,
  autobiographical_destination_pull: 0.78,
  wayfinding_error_recovery_deficit: 0.41,
};

export const DEMO_ATTRACTIONS = [
  { label: "정릉전통시장", note: "방문 빈도 상" },
  { label: "정릉천 산책로", note: "오전 산책" },
  { label: "옛 자택(정릉1동)", note: "과거 거주지" },
  { label: "복지관 경로당", note: "주 3회" },
];

/** 데모 인상착의 — S3 접수 폼 프리필·디자인 브리프와 동일 문안 */
export const DEMO_APPEARANCE =
  "회색 점퍼, 검은색 바지, 지팡이 사용. 흰머리, 키 155cm가량.";

export const DEMO_BEHAVIOR_NOTE =
  "행동 특징: 오전 산책 습관이 강하고 물가(정릉천)를 선호. 평균 이동 반경 약 1.8km, 익숙한 옛 동선으로 회귀하는 경향.";

// ── 합성 히트맵 (디자인의 가우시안 혼합 로직 포트) ──────────────────

interface GaussCenter { x: number; y: number; sig: number; amp: number }

function centersFor(layer: PoaLayer, d3: boolean): GaussCenter[] {
  let base: GaussCenter[];
  if (layer === "statistical") base = [{ x: 430, y: 372, sig: 172, amp: 0.82 }, { x: 372, y: 300, sig: 150, amp: 0.55 }];
  else if (layer === "top_down") base = [{ x: 430, y: 360, sig: 122, amp: 0.92 }, { x: 500, y: 300, sig: 92, amp: 0.5 }];
  else if (layer === "bottom_up") base = [{ x: 360, y: 300, sig: 60, amp: 0.95 }, { x: 502, y: 430, sig: 70, amp: 0.9 }, { x: 430, y: 360, sig: 54, amp: 0.8 }];
  else base = [{ x: 430, y: 360, sig: 106, amp: 1.0 }, { x: 360, y: 300, sig: 66, amp: 0.72 }, { x: 505, y: 430, sig: 78, amp: 0.86 }];
  if (d3 && (layer === "combined" || layer === "bottom_up")) {
    base = base.concat([{ x: 735, y: 232, sig: 64, amp: 0.9 }, { x: 775, y: 288, sig: 50, amp: 0.55 }]);
  }
  return base;
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const mix = (c1: number[], c2: number[], t: number) =>
  `rgb(${Math.round(lerp(c1[0], c2[0], t))},${Math.round(lerp(c1[1], c2[1], t))},${Math.round(lerp(c1[2], c2[2], t))})`;

export function hexPoints(cx: number, cy: number, s: number): string {
  const p: string[] = [];
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 180) * (60 * i);
    p.push(`${(cx + s * Math.cos(a)).toFixed(1)},${(cy + s * Math.sin(a)).toFixed(1)}`);
  }
  return p.join(" ");
}

export interface HexCell {
  points: string;
  fill: string;
  opacity: number;
  stroke: string;
  sw: number;
  sop: number;
  dash: string;
}

/** POA 확률 → 색+불투명도 이중부호화 (인계 문서 램프: 낮음 rgb(120,84,26) → 높음 rgb(240,86,52)) */
export function probColor(p: number): { fill: string; opacity: number } {
  const low = [120, 84, 26], mid = [214, 140, 44], high = [240, 86, 52];
  const fill = p < 0.5 ? mix(low, mid, p / 0.5) : mix(mid, high, (p - 0.5) / 0.5);
  return { fill, opacity: 0.16 + 0.66 * Math.pow(p, 0.82) };
}

export function buildDemoCells(layer: PoaLayer, view: DemoView): HexCell[] {
  const d3 = view === "d3", faded = view === "closed";
  const centers = centersFor(layer, d3);
  const s = 30, horiz = 1.5 * s, vert = Math.sqrt(3) * s;
  const lkp = { x: 430, y: 360 };
  const cells: HexCell[] = [];
  for (let c = 0; c < 23; c++) {
    for (let r = 0; r < 18; r++) {
      const cx = 24 + c * horiz;
      const cy = 20 + r * vert + (c % 2 ? vert / 2 : 0);
      if (cx < 8 || cx > 952 || cy < 8 || cy > 772) continue;
      let p = 0;
      for (const g of centers) {
        const dx = cx - g.x, dy = cy - g.y;
        p += g.amp * Math.exp(-((dx * dx + dy * dy) / (2 * g.sig * g.sig)));
      }
      p = Math.min(1, p / 1.55);
      if (p < 0.1) continue;
      let { fill, opacity } = probColor(p);
      let stroke = "none", sw = 0, sop = 0, dash = "0";
      const dist = Math.hypot(cx - lkp.x, cy - lkp.y);
      if (!faded && (view === "tips3" || view === "d3") && dist < 142 && p > 0.14) {
        stroke = "#cfe4ff"; sw = 1.4; sop = 0.72; dash = "3 3";
      }
      if (faded) {
        opacity *= 0.32;
        fill = mix([84, 104, 92], [120, 150, 124], p);
      }
      cells.push({ points: hexPoints(cx, cy, s - 1.2), fill, opacity: +opacity.toFixed(3), stroke, sw, sop, dash });
    }
  }
  return cells;
}

export interface TipPin {
  x: number; y: number; num: string;
  color: string; r2: number; ringOp: number; dash: string;
}

/** 지도 제보 핀 — 번호는 타임라인과 동일하게 도착 시간순 */
export function demoTipPins(view: DemoView): TipPin[] {
  if (view === "loading" || view === "closed") return [];
  const color = { reflect: "#f0a63c", rerun: "#f2555a", discard: "#75798c" } as const;
  const pins: { x: number; y: number; tier: keyof typeof color; num: string }[] = [
    { x: 352, y: 300, tier: "reflect", num: "1" },
    { x: 250, y: 486, tier: "discard", num: "2" },
    { x: 512, y: 428, tier: "rerun", num: "3" },
  ];
  if (view === "d3") pins.push({ x: 742, y: 250, tier: "rerun", num: "4" });
  return pins.map((p) => ({
    x: p.x, y: p.y, num: p.num, color: color[p.tier],
    r2: p.tier === "rerun" ? 12 : 10,
    ringOp: p.tier === "discard" ? 0.6 : p.tier === "rerun" ? 0.5 : 0.4,
    dash: p.tier === "discard" ? "2 3" : "0",
  }));
}
