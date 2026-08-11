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
import type {
  AlertKind,
  GeoPoint,
  PoaCell,
  PoaGrid,
  PoliceAlert,
  Severity,
  TimeAxis,
  Tip,
  TipInput,
  TipResult,
} from '../types/domain';
import { DEMO_CASE_ID } from '../data/missing';
import { tierForProb } from '../theme/poa';
import { buildAlert, buildBeforeAfter, buildPoaGrid } from '../data/mock';
import { DEMO_USER_ID, SLOW_TIMEOUT_MS, USE_MOCK, api } from './config';

export { API_BASE, USE_MOCK, ApiError } from './config';
export { DEMO_CASE_ID };

type PoaResponse = {
  top_cells: { cell: string; prob: number; polygon: GeoPoint[] }[];
  /** prior 출처 — 폴백(개인화 없음)을 앱이 숨기지 않고 알리기 위한 값. */
  prior_source?: 'exaone' | 'fallback' | 'stub' | 'unknown';
  prior_fallback_reason?: string;
  /** 도로망 위에서 걸었는지 — 로딩 실패 시 연속 공간 폴백이 조용히 일어난다. */
  roadnet_used?: boolean;
  roadnet_fallback_reason?: string;
  /** 이 지도가 계산된 시각 · 그때의 경과시간 — "몇 시간 시점 지도"를 말하기 위해. */
  computed_at?: string;
  elapsed_hours?: number | null;
};

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
  return {
    caseId,
    t,
    cells,
    cumulative,
    topLabel: `최고확률 구역 ${peakPct}%`,
    priorSource: data.prior_source ?? 'unknown',
    priorFallbackReason: data.prior_fallback_reason || undefined,
    roadnetUsed: data.roadnet_used ?? false,
    roadnetFallbackReason: data.roadnet_fallback_reason || undefined,
    computedAt: data.computed_at,
    elapsedHours: data.elapsed_hours ?? undefined,
  };
}

/**
 * POA 조회. `t` 는 **경과시간(시간)** 이고 0 은 "지금 실제 경과시간"을 뜻한다.
 *
 * 0 이 아니면 서버가 "만약 t시간 경과라면"의 지도를 계산해 준다 — 시간축
 * 슬라이더가 이걸 쓴다. 기존 통계(Koester 링)는 시점과 무관한 하나의 분포지만
 * 우리는 경과시간이 예측에 들어가므로 시점마다 다르다(30분 상한 1.44km vs
 * 1시간 2.88km). 첫 조회만 ~7초 걸리고 서버가 캐시한다.
 */
export async function getPoaPrediction(caseId: string, t: TimeAxis): Promise<PoaGrid> {
  if (USE_MOCK) return delay(buildPoaGrid(t));
  const q = t > 0 ? `&elapsed_hours=${t}` : '';
  const data = await api<PoaResponse>(`/phase3/cases/${caseId}/poa?top=64${q}`);
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
  opts: { force?: boolean; reporterUserId?: string } = {},
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
    // 고신뢰 제보는 **층2(새 LKP 로 재예측)** 를 발동시킨다 — 그 순간 이 요청
    // 하나가 예측 한 판을 통째로 품는다(실측 08-12: 29.5초, 새 지역이면 2분 초과).
    // 기본 12초로 끊으면 재예측이 중간에 잘려 **사건에 POA 가 없는 상태**가 남고,
    // 시민 화면의 확률지도가 통째로 비어 버린다.
    timeoutMs: SLOW_TIMEOUT_MS,
    body: JSON.stringify({
      text: input.text,
      location: input.location ?? null,
      seen_at: input.seenAt ?? null,
      force: !!opts.force,
      // 제보 참여 수가 이 값으로 갈린다 — 로그인한 사람 것으로 센다.
      reporter_user_id: opts.reporterUserId ?? DEMO_USER_ID,
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

/** 알림 발송 결과 — 왜 이만큼만 갔는지 단계별로 되짚을 수 있게 되어 있다. */
export type AlertSendResult = {
  /** 예측 셀(res9) 수. 대상 구역의 크기. */
  sourceCells: number;
  /** 발송 대상 res7 셀 목록. 폰이 관문 판정에 쓰는 그 목록과 같다. */
  targetCells: string[];
  /** 대상 구역 안에 있던 기기 수(확률 문턱 적용 **전**). */
  inArea: number;
  /** 그중 참여도 문턱에 못 미쳐 빠진 수 — 피로도 예산이 실제로 몇 명을 줄였나. */
  belowThreshold: number;
  /** 실제 발송 건수. */
  sent: number;
  /** 스텁 모드(push_enabled=false)라 네트워크를 타지 않았는가. */
  stub: boolean;
};

/**
 * 알림 발송 (경찰·운영 화면용).
 *
 * ⚠️ `stub: true` 면 **기기에 실제로 알림이 가지 않았다** — 서버가 "보낸 셈" 친
 * 것이다(백엔드 push_enabled 기본값 false). 화면에서 "발송 완료"라고 단정하기 전에
 * 이 값을 봐야 한다.
 */
export async function sendAlerts(caseId: string): Promise<AlertSendResult> {
  if (USE_MOCK) {
    return delay({
      sourceCells: 12, targetCells: ['8730e1c30ffffff'],
      inArea: 3, belowThreshold: 1, sent: 2, stub: true,
    });
  }
  const r = await api<{
    source_cells: number; target_cells: string[]; in_area: number;
    below_threshold: number; sent: number; stub: boolean;
  }>(`/phase3/cases/${caseId}/alerts`, { method: 'POST' });
  return {
    sourceCells: r.source_cells, targetCells: r.target_cells, inArea: r.in_area,
    belowThreshold: r.below_threshold, sent: r.sent, stub: r.stub,
  };
}

type AlertResponse = {
  case_id: string;
  issued_at: string;
  area: string;
  severity: Severity;
  kind: AlertKind;
  /** 대상 H3 셀(res7)과 그 해상도 — 폰이 자기 칸과 대조해 관문 여부를 정한다. */
  target_cells: string[];
  target_res: number;
  summary: string;
  matched_person_id?: string | null;
  /** 시민에게 보여줄 최소 신원 — 이름은 오지 않는다(불특정 다수 대상 알림). */
  age?: number | null;
  appearance?: string[];
  /** 실루엣 아바타용 색 태그(빨강·검정 등 영문 키). 백엔드는 이미지를 만들지 않는다. */
  appearance_colors?: { top: string; bottom: string; shoes: string };
  lkp?: GeoPoint;
  lkp_time?: string;
};

/**
 * 살아있는 경보 목록 — 관문(useAlertGate)이 판정할 대상.
 *
 * 종전에는 `buildAlert()` 를 **조건 없이** 돌려줘서, 시민이 앱을 열 때마다
 * 존재하지 않는 사건의 경보가 떴다(실측: 시뮬레이터 기본 위치가 쿠퍼티노라
 * "약 9023.9km" 라는 거리까지 표시됐다). 이제 서버의 실제 케이스만 본다.
 *
 * 푸시는 **보내는 그 순간**에만 도달하므로(폰이 꺼져 있었거나 알림을 쓸어 없앴으면
 * 아무것도 안 남는다) 이 조회 경로가 따로 필요하다 — 관문은 사용자가 앱을 **직접
 * 연** 순간에도 판정해야 한다.
 *
 * ## 내 칸을 보내고, 서버가 고른다
 * 전체 목록을 받아 폰이 거르는 구조로 만들면 앱이 전국 실종자 명단을 받게 된다 —
 * 푸시에서 최소화해 둔 것을 조회 경로가 무효화하는 셈. 발송과 **같은 기준**으로
 * 서버가 고른다(백엔드 `GET /phase3/alerts`).
 *
 * @param cellRes7 내 위치의 res7 셀. **null 이면 서버가 빈 목록을 준다** —
 *   위치를 모르면 어느 사건이 나에게 해당되는지 고를 수 없기 때문(fail-closed).
 */
export async function getActiveAlerts(cellRes7: string | null): Promise<PoliceAlert[]> {
  if (USE_MOCK) return delay(cellRes7 ? [buildAlert()] : []);
  if (cellRes7 == null) return [];
  const rows = await api<AlertResponse[]>(
    `/phase3/alerts?cell_res7=${encodeURIComponent(cellRes7)}`,
  );
  return rows.map((r) => ({
    caseId: r.case_id,
    issuedAt: r.issued_at,
    // 서버가 역지오코딩으로 채운다. 조회 실패 시에만 빈 문자열이 오고, 그때는
    // 동 이름을 지어내는 대신 물러난다.
    area: r.area || '내 주변',
    severity: r.severity,
    kind: r.kind,
    targetCells: r.target_cells,
    targetRes: r.target_res,
    summary: r.summary,
    matchedPersonId: r.matched_person_id ?? undefined,
    age: r.age ?? undefined,
    appearance: (r.appearance ?? []).filter(Boolean),
    appearanceColors: r.appearance_colors,
    lkp: r.lkp,
    lkpTime: r.lkp_time,
  }));
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
/** 내 주변 산책 **루트** — 서버가 OSM 에서 실제 산책로의 좌표열까지 가져온다. */
export type NearbyWalk = {
  name: string;
  /** 대표점(경로 중간) — 썸네일 지도의 중심. */
  lat: number;
  lng: number;
  /** 내 위치에서 그 길의 가장 가까운 지점까지(직선). */
  distance_km: number;
  /** 길 자체의 길이. "코스 N km"로 적는 값이다 — 직선거리와 섞지 않는다. */
  route_km: number;
  /** 'park' = 공원 둘레길 · 'path' = 산책로 */
  kind: string;
  /** 길의 실제 모양. 앱이 지도 위에 그린다. */
  path: GeoPoint[];
};

export async function getNearbyWalks(point: GeoPoint, limit = 4): Promise<NearbyWalk[]> {
  return api<NearbyWalk[]>(
    `/geo/nearby-walks?lat=${point.lat}&lng=${point.lng}&limit=${limit}`,
  );
}

export async function touchPresence(caseId: string): Promise<number> {
  if (USE_MOCK) {
    mockWatching = Math.min(9, Math.max(2, mockWatching + (Math.random() < 0.5 ? -1 : 1)));
    return delay(mockWatching, 200);
  }
  const data = await api<{ watching: number }>(`/phase3/cases/${caseId}/presence`, {
    method: 'POST',
    body: JSON.stringify({ token: PRESENCE_TOKEN }),
  });
  return data.watching;
}

/**
 * 기기 등록 — 푸시 발송 대상에 추가. 앱 실행마다·칸이 바뀔 때마다 호출해도
 * 안전하다(서버가 upsert 하고 발송 이력을 유지한다).
 *
 * ## 무엇을 보내고 무엇을 안 보내는가
 * 서버가 토큰을 영속 저장하는 것은 푸시의 본질상 회피할 수 없다. 대신 붙는 정보를
 * 최소로 깎는다 — 백엔드 `schemas/device.py` 의 경계와 짝을 이룬다.
 *
 *   ✅ cellRes7   폰이 좌표를 res7(≈5km²)로 **직접 바꾼 값**. 정밀 좌표는 기기를
 *                 떠나지 않는다. null 이면 "이번엔 위치를 못 구했다"는 뜻이고,
 *                 서버는 마지막으로 알던 칸을 지우지 않는다.
 *   ✅ engagement 참여도 **등급**만. 열람·제보 횟수 원본은 폰에만 있다.
 *   ❌ 좌표·정밀 셀·위치 이력·제보 이력
 */
export async function registerDevice(
  token: string,
  platform: 'android' | 'ios',
  cellRes7: string | null = null,
  engagement: 'high' | 'normal' | 'low' = 'normal',
): Promise<void> {
  if (USE_MOCK) return;
  await api('/phase3/devices', {
    method: 'POST',
    body: JSON.stringify({ token, platform, cell_res7: cellRes7, engagement }),
  });
}

/** 등록 해제 — 알림 수신 거부 시. 지속적 식별자이므로 지우는 경로가 반드시 있어야 한다. */
export async function unregisterDevice(token: string): Promise<void> {
  if (USE_MOCK) return;
  await api(`/phase3/devices/${encodeURIComponent(token)}`, { method: 'DELETE' });
}

/**
 * 수색 안내 문구 — "어디를 봐야 하는지" (알림 개인화 #5).
 *
 * **수색 탭 전용**이다. 푸시 본문에는 넣지 않는다 — 잠금화면은 폰을 집어든 누구나
 * 보고 그 알림은 넓은 지역에 가므로, 같은 문장이라도 노출 범위가 달라진다.
 * 서버 계약: GET /phase3/cases/{id}/guidance → { guidance, personalized, pending }
 */
export type Guidance = {
  text: string;
  personalized: boolean;
  /**
   * 서버가 LLM 으로 문구를 다듬는 중. 지금 온 것은 템플릿판이고 곧 더 나은 문구가
   * 준비된다 — 서버가 **기다리지 않고** 템플릿을 먼저 주기 때문이다(골든타임에
   * 안내가 비어 있으면 안 된다). 이 값이 true 인 동안만 다시 묻는다.
   */
  pending: boolean;
};

export async function getGuidance(caseId: string): Promise<Guidance> {
  if (USE_MOCK) {
    return delay({
      text: '멀리 가지 못하고 한자리에 머물러 계실 수 있어요. 골목, 벤치, 건물 그늘을 먼저 살펴봐 주세요.',
      personalized: true,
      pending: false,
    });
  }
  const data = await api<{ guidance: string; personalized: boolean; pending?: boolean }>(
    `/phase3/cases/${caseId}/guidance`,
  );
  return { text: data.guidance, personalized: data.personalized, pending: !!data.pending };
}
