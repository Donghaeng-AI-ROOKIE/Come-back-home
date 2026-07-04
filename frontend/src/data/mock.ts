/**
 * 데모 목 데이터. 정릉동 "김순자" 단일 사건 기준.
 * POA 그리드는 시간축 t에 따라 결정론적으로 생성(가우시안 + 시드 노이즈).
 * 백엔드 연동 시 이 모듈을 api/client.ts의 실제 fetch로 교체.
 */
import type {
  AblationBar,
  CrossValCell,
  CrossValidation,
  FoundSummary,
  GeoPoint,
  PoaCell,
  PoaGrid,
  Poi,
  PoliceAlert,
  ReasonStep,
  TimeAxis,
  ValidationMetrics,
  WalkCourse,
  WalkStats,
} from '../types/domain';
import { DEMO_CASE_ID, LAST_SEEN, MISSING } from './missing';
import { tierForProb } from '../theme/poa';

// ── 시드 난수 (결정론적) ──────────────────────────────
function lcg(seed: number): () => number {
  let s = seed >>> 0 || 1;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 0xffffffff;
  };
}

const CENTER = LAST_SEEN;
const H_LAT = 0.0006; // 셀 반높이(위도) ≈ 130m
const H_LNG = 0.00076; // 셀 반너비(경도)
const COLS = 7;
const ROWS = 8;

type PeakCfg = { pi: number; pj: number; sx: number; sy: number; peak: number };
const PEAK: Record<TimeAxis, PeakCfg> = {
  0: { pi: 3.0, pj: 3.8, sx: 1.0, sy: 1.1, peak: 0.86 },
  1: { pi: 3.6, pj: 4.6, sx: 1.5, sy: 1.7, peak: 0.8 },
  3: { pi: 4.2, pj: 5.3, sx: 2.1, sy: 2.3, peak: 0.72 },
  6: { pi: 4.7, pj: 5.9, sx: 2.7, sy: 2.9, peak: 0.66 },
};

function cellPolygon(center: GeoPoint): GeoPoint[] {
  return [
    { lat: center.lat + H_LAT, lng: center.lng - H_LNG },
    { lat: center.lat + H_LAT, lng: center.lng + H_LNG },
    { lat: center.lat - H_LAT, lng: center.lng + H_LNG },
    { lat: center.lat - H_LAT, lng: center.lng - H_LNG },
  ];
}

export function buildPoaGrid(t: TimeAxis, seedSalt = 0): PoaGrid {
  const cfg = PEAK[t];
  const rnd = lcg(1000 + t * 97 + seedSalt * 7);
  type Raw = { i: number; j: number; center: GeoPoint; w: number };
  const raws: Raw[] = [];
  let sumW = 0;
  let maxW = 0;
  for (let i = 0; i < COLS; i++) {
    for (let j = 0; j < ROWS; j++) {
      const dx = i - cfg.pi;
      const dy = j - cfg.pj;
      const g = Math.exp(-((dx * dx) / (2 * cfg.sx * cfg.sx) + (dy * dy) / (2 * cfg.sy * cfg.sy)));
      const w = g * (0.85 + 0.3 * rnd());
      const center: GeoPoint = {
        lat: CENTER.lat + (j - (ROWS - 1) / 2) * 2 * H_LAT,
        lng: CENTER.lng + (i - (COLS - 1) / 2) * 2 * H_LNG,
      };
      raws.push({ i, j, center, w });
      sumW += w;
      if (w > maxW) maxW = w;
    }
  }

  const cells: PoaCell[] = [];
  let midMarked = 0;
  for (const r of raws) {
    const prob = Math.min(0.95, (r.w / maxW) * cfg.peak);
    if (prob < 0.1) continue; // 크림 여백 과다 방지
    const tier = tierForProb(prob);
    const mismatch = tier === 'mid' && (r.i + r.j) % 2 === 0 && midMarked++ < 2;
    cells.push({
      id: `c-${t}-${r.i}-${r.j}`,
      center: r.center,
      polygon: cellPolygon(r.center),
      prob,
      tier,
      mismatch,
    });
  }

  const masses = raws.map((r) => r.w / sumW).sort((a, b) => b - a);
  const cumulative = masses.slice(0, 10).reduce((a, b) => a + b, 0);
  const peakPct = Math.round(Math.max(...cells.map((c) => c.prob)) * 100);

  return { caseId: DEMO_CASE_ID, t, cells, cumulative, topLabel: `정릉천 북동 구역, ${peakPct}%` };
}

/** ReportDone 기여 시각화 — 제보 전/후 구역 축소. */
export function buildBeforeAfter(): { before: PoaGrid; after: PoaGrid; beforeKm2: number; afterKm2: number } {
  const before = buildPoaGrid(3, 0);
  // after: 더 집중된 분포(제보 반영). t=1 좁은 분포 + salt.
  const after = buildPoaGrid(1, 3);
  return { before, after, beforeKm2: 2.3, afterKm2: 0.8 };
}

// ── POI 확률 (근거 뷰) ────────────────────────────────
export const POIS: Poi[] = [
  { id: 'poi-stream', name: '정릉천 산책로', center: { lat: 37.6083, lng: 127.0134 }, prob: 0.42, reason: '매일 오전 걷던 길' },
  { id: 'poi-market', name: '정릉시장', center: { lat: 37.6047, lng: 127.0121 }, prob: 0.18, reason: '장보기 습관' },
  { id: 'poi-arirang', name: '아리랑고개', center: { lat: 37.6015, lng: 127.0088 }, prob: 0.12, reason: '예전 거주지 방향' },
  { id: 'poi-kmu', name: '국민대 후문', center: { lat: 37.6108, lng: 127.0079 }, prob: 0.09, reason: '손주 학교 방향' },
  { id: 'poi-center', name: '정릉동 주민센터', center: LAST_SEEN, prob: 0.07, reason: '최종 목격지' },
];

// ── 교차검증 (마음 ↔ 몸) ──────────────────────────────
function crossGrid(seed: number, mismatchAt: number[]): CrossValCell[] {
  const rnd = lcg(seed);
  const cells: CrossValCell[] = [];
  const N = 4;
  for (let row = 0; row < N; row++) {
    for (let col = 0; col < N; col++) {
      const idx = row * N + col;
      const prob = Math.exp(-(((col - 1.4) ** 2) / 3 + ((row - 1.6) ** 2) / 3)) * (0.8 + 0.4 * rnd());
      cells.push({
        id: `cv-${seed}-${idx}`,
        row,
        col,
        tier: tierForProb(Math.min(0.9, prob * 0.9)),
        mismatch: mismatchAt.includes(idx),
      });
    }
  }
  return cells;
}

export function buildCrossValidation(): CrossValidation {
  return {
    caseId: DEMO_CASE_ID,
    agreement: 0.78,
    jsd: 0.081,
    mind: crossGrid(21, [6, 11]),
    body: crossGrid(42, [7, 11]),
  };
}

// ── 근거 타임라인 (마음 상태 추론) ────────────────────
export const REASON_TIMELINE: ReasonStep[] = [
  { id: 'r0', time: '15:10', status: '집을 나섬', confusion: 0.3, note: '평소 산책 시간대' },
  { id: 'r1', time: '15:40', status: '길을 헷갈림', confusion: 0.6, note: '익숙한 갈림길에서 지체 추정' },
  { id: 'r2', time: '16:20', status: '쉬는 중', confusion: 0.7, note: '정릉천 벤치 부근 추정' },
  { id: 'r3', time: '17:00', status: '귀가 시도', confusion: 0.5, note: '집 방향 재탐색' },
];

// ── 경찰 실종경보 ─────────────────────────────────────
export function buildAlert(): PoliceAlert {
  return {
    caseId: DEMO_CASE_ID,
    issuedAt: new Date(Date.now() - 42 * 60 * 1000).toISOString(), // 42분 전 발령
    area: MISSING.area,
    severity: 'critical',
    distanceM: 320,
    summary: MISSING.label,
    matchedPersonId: MISSING.id,
  };
}

// ── 검증 수치 ─────────────────────────────────────────
export const ABLATION: AblationBar[] = [
  { label: '돌아오길 AI', value: 0.87, highlight: true },
  { label: '고전 모델', value: 0.61 },
  { label: '유형 평균', value: 0.44 },
];

export function buildValidation(): ValidationMetrics {
  return { caseId: DEMO_CASE_ID, ablation: ABLATION, hitAtDistanceM: 380, jsd: 0.081, cumulativePoa: 0.84 };
}

// ── 발견·종료 요약 ────────────────────────────────────
export function buildFoundSummary(): FoundSummary {
  return { caseId: DEMO_CASE_ID, elapsed: '52분', citizens: 128, validTips: 7, foundArea: '정릉천 북동 산책로' };
}

// ── 산책(평시) ────────────────────────────────────────
export const WALK_STATS: WalkStats = {
  steps: 6420,
  goal: 8000,
  distanceKm: 4.3,
  durationMin: 48,
  route: [
    { lat: 37.6055, lng: 127.0098 },
    { lat: 37.6062, lng: 127.0109 },
    { lat: 37.6071, lng: 127.0121 },
    { lat: 37.6079, lng: 127.0132 },
    { lat: 37.6086, lng: 127.0139 },
  ],
};

export const WALK_COURSES: WalkCourse[] = [
  { id: 'wc1', name: '정릉천 물길 코스', distanceKm: 2.1, durationMin: 30, tag: '평지' },
  { id: 'wc2', name: '북한산 둘레길 초입', distanceKm: 3.4, durationMin: 55, tag: '숲길' },
  { id: 'wc3', name: '아리랑시장 마실', distanceKm: 1.6, durationMin: 22, tag: '동네' },
];

/** 지도 초기 리전 (정릉동). */
export const REGION = { latitude: CENTER.lat, longitude: CENTER.lng, latitudeDelta: 0.018, longitudeDelta: 0.014 };
