/**
 * 수색 플로우 API — 백엔드 `/phase3` 대응.
 *
 * 종전에는 `USE_MOCK = true` 가 파일에 박혀 있어 어떤 화면도 서버에 닿지
 * 않았고, 끄더라도 7개 함수 중 3개만 실제 경로가 있었으며 그중 하나는
 * `throw new Error('실서비스 응답 매핑 미구현')` 이었다. 이제 전부 실연결이고,
 * 목업은 EXPO_PUBLIC_USE_MOCK=true 일 때만 쓰는 시연장 퇴로다.
 *
 * 보호자 플로우(사전등록·신고·예측)는 ./guardian, 산책은 ./walk 에 있다.
 */
import type { GeoPoint, PoaCell, PoaGrid, TimeAxis, Tip, TipInput, TipResult } from '../types/domain';
import { DEMO_CASE_ID } from '../data/missing';
import { tierForProb } from '../theme/poa';
import { buildBeforeAfter, buildPoaGrid } from '../data/mock';
import { DEMO_USER_ID, USE_MOCK, api } from './config';

export { API_BASE, USE_MOCK, ApiError } from './config';
export { DEMO_CASE_ID };

type PoaResponse = { top_cells: { cell: string; prob: number; polygon: GeoPoint[] }[] };

/** 백엔드 Tip 원본 (snake_case). */
type TipResponse = {
  id: string;
  case_id: string;
  text: string;
  location?: GeoPoint | null;
  seen_at?: string | null;
  p?: number | null;
  decision?: 'discard' | 'layer1' | 'layer2' | null;
  created_at: string;
};

type NeedMore = { status: 'need_more'; missing: string[]; reason?: string };

function delay<T>(value: T, ms = 350): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

function polygonCentroid(poly: GeoPoint[]): GeoPoint {
  const n = poly.length || 1;
  const s = poly.reduce((a, p) => ({ lat: a.lat + p.lat, lng: a.lng + p.lng }), { lat: 0, lng: 0 });
  return { lat: s.lat / n, lng: s.lng / n };
}

/** H3 res9 육각형 1칸의 넓이(km²) — 알림 면적 환산에 쓴다(고정 상수). */
const CELL_AREA_KM2 = 0.105;

function toGrid(caseId: string, t: TimeAxis, data: PoaResponse): PoaGrid {
  // 백엔드 prob 는 전체 셀 합=1 기준이라 개별 값이 작다 → 최댓값 대비 상대값으로
  // 색을 펼친다. 표시용 변환이고, 누적 확률은 원본 prob 로 계산한다.
  const maxP = data.top_cells.reduce((m, c) => Math.max(m, c.prob), 0) || 1;
  const cells: PoaCell[] = data.top_cells.map((tc) => {
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
  const peakPct = Math.round((data.top_cells[0]?.prob ?? 0) * 100);
  return { caseId, t, cells, cumulative, topLabel: `최고확률 구역 ${peakPct}%` };
}

export async function getPoaPrediction(caseId: string, t: TimeAxis): Promise<PoaGrid> {
  if (USE_MOCK) return delay(buildPoaGrid(t));
  const data = await api<PoaResponse>(`/phase3/cases/${caseId}/poa?top=64`);
  return toGrid(caseId, t, data);
}

/**
 * 제보 전송.
 *
 * 백엔드는 before/after 를 주지 않으므로 **전송 전후로 POA 를 두 번 읽어**
 * 수색 구역 변화를 계산한다. 목업이 만들어 내던 숫자가 아니라 실제 갱신 결과다.
 *
 * 위치를 특정하지 못하면 백엔드가 `{status:"need_more"}` 로 되묻는다 —
 * 이때는 던지지 않고 그대로 반환해 챗봇이 한 번 더 묻게 한다.
 */
export async function submitTip(
  caseId: string,
  input: TipInput,
  opts: { force?: boolean } = {},
): Promise<TipResult | NeedMore> {
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
    return delay({ tip, beforeAreaKm2: beforeKm2, afterAreaKm2: afterKm2, deltaPct,
      beforeGrid: before, afterGrid: after }, 700);
  }

  const before = await api<PoaResponse>(`/phase3/cases/${caseId}/poa?top=64`);
  const res = await api<TipResponse | NeedMore>(`/phase3/cases/${caseId}/tips`, {
    method: 'POST',
    body: JSON.stringify({
      text: input.text,
      location: input.location ?? null,
      seen_at: input.seenAt ?? null,
      force: !!opts.force,
      reporter_user_id: DEMO_USER_ID,
    }),
  });
  if ('status' in res && res.status === 'need_more') return res;

  const after = await api<PoaResponse>(`/phase3/cases/${caseId}/poa?top=64`);
  const beforeKm2 = before.top_cells.length * CELL_AREA_KM2;
  const afterKm2 = after.top_cells.length * CELL_AREA_KM2;
  const tipRes = res as TipResponse;
  return {
    tip: {
      id: tipRes.id,
      caseId: tipRes.case_id,
      text: tipRes.text,
      location: tipRes.location ?? undefined,
      seenAt: tipRes.seen_at ?? undefined,
      hasPhoto: !!input.hasPhoto,
      p: tipRes.p ?? undefined,
      decision: tipRes.decision ?? undefined,
      createdAt: tipRes.created_at,
    },
    beforeAreaKm2: Number(beforeKm2.toFixed(2)),
    afterAreaKm2: Number(afterKm2.toFixed(2)),
    // 음수 = 좁혀짐. before 가 0 이면 나눗셈이 무한대가 되므로 0 으로 둔다.
    deltaPct: beforeKm2 > 0 ? Math.round(((afterKm2 - beforeKm2) / beforeKm2) * 100) : 0,
    beforeGrid: toGrid(caseId, 0, before),
    afterGrid: toGrid(caseId, 0, after),
  };
}

/**
 * 알림 발송. **푸시 인프라가 아직 없다** — 백엔드가 대상 셀만 계산하고
 * `sent:false` 로 답한다. 실제로 기기에 알림이 가지 않으므로 화면에서
 * "발송 완료"라고 단정하면 안 된다(sent 를 그대로 노출한다).
 */
export async function sendAlerts(
  caseId: string,
): Promise<{ targetCells: number; sent: boolean; message: string }> {
  if (USE_MOCK) return delay({ targetCells: 12, sent: false, message: '[목업] 알림 미리보기' });
  const r = await api<{ target_cells: number; sent: boolean; message: string }>(
    `/phase3/cases/${caseId}/alerts`, { method: 'POST' });
  return { targetCells: r.target_cells, sent: r.sent, message: r.message };
}
