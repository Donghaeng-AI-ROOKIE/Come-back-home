/**
 * API 클라이언트. 현재는 목 데이터. USE_MOCK=false 로 두면 실제 FastAPI 백엔드
 * (backend/app/api/phase0~3)에 연결. 함수 시그니처는 백엔드 계약을 그대로 반영.
 *
 * 백엔드 라우트 대응:
 *   getActiveAlerts   → (푸시/폴링; 데모는 목)
 *   getPoaPrediction  → GET  /phase3/cases/{caseId}/poa  (+ Phase2 predict 선행)
 *   getCrossValidation→ (Phase2 산출물 파생; 데모는 목)
 *   submitTip         → POST /phase3/cases/{caseId}/tips
 *   sendAlerts        → POST /phase3/cases/{caseId}/alerts
 *   getValidation     → (검증 리포트; 데모는 목)
 *   getFoundSummary   → GET  /phase1/cases/{caseId} + 집계
 */
import type {
  CrossValidation,
  FoundSummary,
  GeoPoint,
  PoaCell,
  PoaGrid,
  PoliceAlert,
  TimeAxis,
  Tip,
  TipInput,
  TipResult,
  ValidationMetrics,
} from '../types/domain';
import { DEMO_CASE_ID } from '../data/missing';
import { tierForProb } from '../theme/poa';
import {
  buildAlert,
  buildBeforeAfter,
  buildCrossValidation,
  buildFoundSummary,
  buildPoaGrid,
  buildValidation,
} from '../data/mock';

export const USE_MOCK = true;
/** 실제 백엔드 주소 (에뮬레이터: 안드로이드=10.0.2.2, iOS 시뮬=localhost). */
export const API_BASE = 'http://localhost:8000';

function delay<T>(value: T, ms = 350): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

export async function getActiveAlerts(): Promise<PoliceAlert[]> {
  if (USE_MOCK) return delay([buildAlert()]);
  // 실서비스: 푸시(Notifee/FCM) + 지오펜스 백그라운드 폴링. 데모 미구현.
  return [];
}

type PoaResponse = { top_cells: { cell: string; prob: number; polygon: GeoPoint[] }[] };

function polygonCentroid(poly: GeoPoint[]): GeoPoint {
  const n = poly.length || 1;
  const s = poly.reduce((a, p) => ({ lat: a.lat + p.lat, lng: a.lng + p.lng }), { lat: 0, lng: 0 });
  return { lat: s.lat / n, lng: s.lng / n };
}

export async function getPoaPrediction(caseId: string, t: TimeAxis): Promise<PoaGrid> {
  if (USE_MOCK) return delay(buildPoaGrid(t));
  // 백엔드가 각 셀의 폴리곤을 함께 반환(backend: POA 폴리곤 응답) → 그대로 렌더.
  const res = await fetch(`${API_BASE}/phase3/cases/${caseId}/poa?top=64`);
  if (!res.ok) throw new Error(`POA 조회 실패: ${res.status}`);
  const data = (await res.json()) as PoaResponse;
  const maxP = data.top_cells.reduce((m, c) => Math.max(m, c.prob), 0) || 1;
  const cells: PoaCell[] = data.top_cells.map((tc) => {
    // 백엔드 prob 는 전체 셀 합=1 기준이라 작다 → 최댓값 대비 상대값으로 색 스프레드.
    const rel = Math.min(0.95, (tc.prob / maxP) * 0.9);
    return {
      id: tc.cell,
      center: polygonCentroid(tc.polygon),
      polygon: tc.polygon,
      prob: rel,
      tier: tierForProb(rel),
    };
  });
  const cumulative = Math.min(1, data.top_cells.reduce((a, c) => a + c.prob, 0));
  const peakPct = Math.round((cells[0]?.prob ?? 0) * 100);
  return { caseId, t, cells, cumulative, topLabel: `최고확률 구역 ${peakPct}%` };
}

export async function getCrossValidation(caseId: string): Promise<CrossValidation> {
  if (USE_MOCK) return delay(buildCrossValidation());
  return buildCrossValidation();
}

export async function submitTip(caseId: string, input: TipInput): Promise<TipResult> {
  if (USE_MOCK) {
    const { before, after, beforeKm2, afterKm2 } = buildBeforeAfter();
    const tip: Tip = {
      id: `tip-${Math.round(Date.now() / 1000)}`,
      caseId,
      text: input.text,
      location: input.location,
      seenAt: input.seenAt,
      hasPhoto: !!input.hasPhoto,
      p: 0.72,
      decision: 'layer1',
      createdAt: new Date().toISOString(),
    };
    const deltaPct = Math.round(((afterKm2 - beforeKm2) / beforeKm2) * 100);
    return delay({ tip, beforeAreaKm2: beforeKm2, afterAreaKm2: afterKm2, deltaPct, beforeGrid: before, afterGrid: after }, 700);
  }
  const res = await fetch(`${API_BASE}/phase3/cases/${caseId}/tips`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: input.text,
      location: input.location,
      seen_at: input.seenAt,
      with_photo: !!input.hasPhoto,
    }),
  });
  if (!res.ok) throw new Error(`제보 전송 실패: ${res.status}`);
  throw new Error('실서비스 응답 매핑 미구현'); // TODO
}

export async function sendAlerts(caseId: string): Promise<{ delivered: number; cells: number }> {
  if (USE_MOCK) return delay({ delivered: 128, cells: 12 });
  const res = await fetch(`${API_BASE}/phase3/cases/${caseId}/alerts`, { method: 'POST' });
  if (!res.ok) throw new Error(`알림 발송 실패: ${res.status}`);
  return { delivered: 0, cells: 0 };
}

/**
 * 익명 참여 토큰 (알림 개인화 #4). 앱 실행마다 새로 만들고 **영속화하지 않는다** —
 * 서버가 세션을 넘어 같은 사람을 이어붙일 수 없어야 하므로 오히려 이게 맞다.
 *
 * 보안 토큰이 아니라 "같은 앱 인스턴스의 반복 폴링을 한 명으로 세기 위한" 중복제거
 * 키다. 탈취해봐야 참여자 수가 1 흔들리는 게 전부라 crypto 난수까지 갈 이유는 없고,
 * 충돌만 안 나면 된다(36^11 조합).
 */
const PRESENCE_TOKEN = `p-${Math.random().toString(36).slice(2, 13)}${Date.now().toString(36)}`;

/** 목 모드 참여자 수 — 데모에서 "실시간"이 정지화면으로 보이지 않게 소폭 흔든다. */
let mockWatching = 4;

/**
 * 하트비트 + 현재 동시 참여자 수. 좌표는 보내지 않는다 (셀 단위 집계 = 위치정보).
 * 서버 계약: POST /phase3/cases/{id}/presence → { watching: number }
 */
export async function touchPresence(caseId: string): Promise<number> {
  if (USE_MOCK) {
    mockWatching = Math.min(9, Math.max(2, mockWatching + (Math.random() < 0.5 ? -1 : 1)));
    return delay(mockWatching, 200);
  }
  const res = await fetch(`${API_BASE}/phase3/cases/${caseId}/presence`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: PRESENCE_TOKEN }),
  });
  if (!res.ok) throw new Error(`참여자 수 조회 실패: ${res.status}`);
  const data: { watching: number } = await res.json();
  return data.watching;
}

export async function getValidation(caseId: string): Promise<ValidationMetrics> {
  if (USE_MOCK) return delay(buildValidation());
  return buildValidation();
}

export async function getFoundSummary(caseId: string): Promise<FoundSummary> {
  if (USE_MOCK) return delay(buildFoundSummary());
  return buildFoundSummary();
}

export { DEMO_CASE_ID };
