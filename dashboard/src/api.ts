/** 백엔드 API 클라이언트 — API_CONTRACT.md v0.1 범위만 사용.
 *
 *  라이브 모드: 백엔드(기본 http://localhost:8000)가 응답하면 실데이터.
 *  데모 모드: 백엔드가 없으면 화면은 디자인 확정 데모 데이터로 동작한다
 *  (헤더 배지가 두 모드를 구분 표기 — 정직성 라벨 원칙).
 */

export const API_BASE: string =
  (import.meta as any).env?.VITE_API_BASE ?? "http://localhost:8000";

export const DEMO_CASE_ID = "case-jeongneung-001";

// ── 계약 타입 (백엔드 스키마 실측 기준) ─────────────────────────────

export interface GeoPoint {
  lat: number;
  lng: number;
}

/** GET /debug/overview 응답의 cases[] 항목 */
export interface OverviewCase {
  id: string;
  status: "intake" | "predicted" | "searching" | "found" | "closed";
  persona_id: string | null;
  lkp: GeoPoint;
  lkp_time: string;
  has_trace: boolean;
}

export interface OverviewPersona {
  id: string;
  name: string;
  age: number;
  type: "dementia";
  n_attractions: number;
  n_notes: number;
}

export interface Overview {
  personas: OverviewPersona[];
  cases: OverviewCase[];
}

/** GET /phase3/cases/{id}/poa — 셀마다 polygon 포함(백엔드가 변환, 프론트는 그대로 렌더) */
export interface PoaCell {
  cell: string;
  prob: number;
  polygon: GeoPoint[];
}

export interface PoaResponse {
  case_id: string;
  total_cells: number;
  top_cells: PoaCell[];
}

export interface Tip {
  id: string;
  case_id: string;
  text: string;
  location: GeoPoint | null;
  seen_at: string | null;
  p: number | null;
  decision: "discard" | "layer1" | "layer2" | null;
  created_at: string;
}

/** POST /tips 는 Tip 또는 되묻기 응답 두 형태 — status 키 유무로 분기(계약 경고 박스).
 *  reason 은 시각 분기에서만 오는 사유 코드(현재 "layer2_needs_time" 뿐), 위치 분기엔 없음. */
export interface NeedMore {
  status: "need_more";
  missing: ("location" | "time")[];
  reason?: string;
}

export type TipResult = Tip | NeedMore;

export const isNeedMore = (r: TipResult): r is NeedMore =>
  (r as NeedMore).status === "need_more";

/** POST /phase3/cases/{id}/alerts 응답 — sent 는 FCM 미구현이라 항상 false(시뮬레이션) */
export interface AlertResult {
  case_id: string;
  target_cells: string[];
  message: string;
  sent: boolean;
  note?: string;
}

export interface RerunCheck {
  case_id: string;
  should_rerun: boolean;
  reason: string | null;
}

/** 신고자(보호자) — 신고서(문서) 접수 시 Upstage 추출(스텁은 "[스텁]" 접두), 미접수면 null */
export interface ReporterInfo {
  name: string;
  relation: string;
  phone: string;
}

/** 인상착의 — 사진 접수 시 VARCO 추출(스텁 모드는 "[스텁]" 접두 고정값), 미접수면 null */
export interface Appearance {
  top: string;
  bottom: string;
  shoes: string;
  physical: string;
  summary: string;
  accessories?: string[];
}

export interface AttractionPoint {
  label: string;
  location?: GeoPoint;
  weight?: string | null;
  place_type?: string;
}

export interface Persona {
  id: string;
  name: string;
  age: number;
  type: "dementia";
  home: GeoPoint;
  attraction_points: AttractionPoint[];
  behavior_notes: string[];
  axis_scores: Record<string, number>;
}

export interface CaseDetail {
  id: string;
  status: OverviewCase["status"];
  lkp: GeoPoint;
  lkp_time: string;
  created_at: string;
  closed_at: string | null;
  last_sim_at: string | null;
  tips: Tip[];
  report: {
    persona_id?: string | null;
    missing_type?: string;
    appearance?: Appearance | null;
    reporter?: ReporterInfo | null;
  };
}

/** GET /debug/cases/{id}/bundle 중 대시보드가 쓰는 부분 — 4층 POA 레이어.
 *  트레이스 예측(POST /debug/.../predict)을 돌린 케이스만 4층이 다 차고,
 *  아니면 combined 만 온다(레이어당 상위 400셀 + coverage). */
export interface LayerCells {
  total_cells: number;
  coverage: number;
  cells: PoaCell[];
}

export interface Bundle {
  poa_layers: Record<string, LayerCells>;
}

// ── fetch 헬퍼 ──────────────────────────────────────────────────────

async function req<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 8000,
): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal: ctrl.signal,
      ...init,
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`${res.status} ${path} — ${body.slice(0, 200)}`);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

// ── 엔드포인트 (계약표 그대로) ──────────────────────────────────────

export const api = {
  /** 라이브 여부 프로브 겸 케이스 목록 (관제용 목록 API 신설 전까지 debug/overview 사용) */
  overview: () => req<Overview>("/debug/overview", undefined, 2500),

  getCase: (id: string) => req<CaseDetail>(`/phase1/cases/${id}`),

  createReport: (body: {
    missing_type: string;
    lkp: GeoPoint;
    lkp_time: string;
    persona_id?: string;
    with_photo?: boolean;
    with_document?: boolean;
  }) => req<CaseDetail>("/phase1/reports", { method: "POST", body: JSON.stringify(body) }),

  /** 17~27초 소요 — 호출측에서 단계 스테퍼 UI 필수 */
  predict: (id: string, seed?: number) =>
    req<unknown>(
      `/phase2/cases/${id}/predict${seed != null ? `?seed=${seed}` : ""}`,
      { method: "POST" },
      60000,
    ),

  poa: (id: string, top = 80) => req<PoaResponse>(`/phase3/cases/${id}/poa?top=${top}`),

  bundle: (id: string) => req<Bundle>(`/debug/cases/${id}/bundle`, undefined, 15000),

  /** 트레이스 예측 — phase2 와 같은 파이프라인(trace=True, 결과 불변)이지만
   *  4층 POA 분해가 bundle 로 조회 가능해진다. 17~27초 — 호출측 로딩 UI 필수 */
  predictTraced: (id: string, seed?: number) =>
    req<unknown>(
      `/debug/cases/${id}/predict${seed != null ? `?seed=${seed}` : ""}`,
      { method: "POST" },
      60000,
    ),

  // D1 반경 경보는 신고 접수 시 백엔드가 자동 발송(reflex_alert_on_intake=True 기본)
  // — 수동 재발송 엔드포인트(/reflex-alerts)는 UI에서 안 쓰므로 클라이언트 미노출.
  alert: (id: string) => req<AlertResult>(`/phase3/cases/${id}/alerts`, { method: "POST" }),

  submitTip: (
    id: string,
    body: { text: string; location?: GeoPoint; seen_at?: string; force?: boolean },
  ) => req<TipResult>(`/phase3/cases/${id}/tips`, { method: "POST", body: JSON.stringify(body) }),

  rerunCheck: (id: string) => req<RerunCheck>(`/phase3/cases/${id}/rerun-check`),

  persona: (id: string) => req<Persona>(`/phase0/personas/${id}`),

  closeCase: (id: string, reason: "found" | "withdrawn" = "found") =>
    req<CaseDetail>(`/privacy/cases/${id}/close`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
};
