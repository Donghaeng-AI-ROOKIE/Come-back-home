/**
 * 보호자 플로우 API — 사전등록 인터뷰(Phase 0) → 실종 신고(Phase 1) → 예측(Phase 2).
 *
 * 이 세 단계는 앱에 API 함수 자체가 없었다(목 화면만 있었다). 와이어프레임의
 * 보호자 트리가 실제로 동작하려면 이 파일이 필요하다.
 *
 * 인터뷰는 서버가 다음 질문을 고른다 — 앱이 질문 목록을 들고 있지 않다.
 * 슬롯 충족도에 따라 질문이 달라지므로 앱에 박아 두면 서버와 어긋난다.
 */
import type { GeoPoint } from '../types/domain';
import { SLOW_TIMEOUT_MS, api } from './config';

export type PersonaType = 'dementia';

export type InterviewMessage = { role: 'assistant' | 'user'; text: string };

export type InterviewSession = {
  id: string;
  guardian_name: string;
  persona_type: PersonaType | null;
  messages: InterviewMessage[];
  /** 값이 채워진 슬롯 키 — 진행률의 분자. 프론트 단계 인덱스가 아니라 이것이 진실. */
  filled_keys: string[];
  /** 서버가 지금 묻고 있는 슬롯. 빠른응답 칩을 띄울지 정할 때 쓴다. */
  prev_target_key?: string | null;
  /** 마지막 확인("이대로 등록할까요?") 대기 중. */
  awaiting_confirmation?: boolean;
  /** Mi:dm 호출이 반복 실패해 고정 문장으로 떨어진 상태 — 숨기지 않고 알린다. */
  llm_degraded?: boolean;
  done?: boolean;
  /** 완료 시 서버가 만든 페르소나 ID. 신고·예측이 이 값을 쓴다. */
  persona_id?: string | null;
  /**
   * 이 세션이 묻는 슬롯의 tier 집합. `null`/없음 = 전체(12문항 온보딩).
   * 신고 전 미니챗은 `[1]` — 진행률 분모를 이 값으로 좁힌다.
   */
  target_tiers?: number[] | null;
};

export type SlotInfo = {
  key: string;
  label: string;
  axis: string;
  axis_field: string | null;
  /** 1=필수 · 2=중요 · 3=보조. */
  tier: number;
  /** 답변 예시(슬롯 카탈로그 원문) — 음성 인식 붙기 전 입력 보조. */
  answer_example: string;
};

export type AttractionPointIn = {
  label: string;
  location: GeoPoint;
  weight?: number;
  place_type?: string;
};

export type AttractionPoint = {
  label: string;
  location: GeoPoint;
  weight: number;
  place_type?: string | null;
  area_text?: string | null;
  /** 어느 인터뷰 슬롯에서 나왔는지 — 잘못 분류된 항목을 보호자가 알아볼 단서. */
  origin_slot?: string | null;
  evidence?: string | null;
};

export type Persona = {
  id: string;
  name: string;
  age: number;
  type: PersonaType;
  home: GeoPoint;
  attraction_points: AttractionPoint[];
  /** 인터뷰가 추출한 관찰 문장 — "슬롯라벨: 내용" 형태로 저장된다. */
  behavior_notes: string[];
  created_at?: string;
};

export type CaseAppearance = {
  top: string;
  bottom: string;
  shoes: string;
  etc: string;
  summary: string;
  top_color: string;
  bottom_color: string;
  shoes_color: string;
};

export type CaseTip = {
  id: string;
  case_id: string;
  text: string;
  location?: GeoPoint | null;
  seen_at?: string | null;
  p?: number | null;
  decision?: 'discard' | 'layer1' | 'layer2' | null;
  created_at: string;
};

export type Case = {
  id: string;
  status: string;
  created_at: string;
  lkp: GeoPoint;
  lkp_time: string;
  report: {
    id: string;
    persona_id?: string | null;
    missing_type: PersonaType;
    lkp: GeoPoint;
    lkp_time: string;
    appearance?: CaseAppearance | null;
    situation?: string;
  };
  tips: CaseTip[];
  last_alert_at?: string | null;
};

// ── Phase 0 — 사전등록 인터뷰 ────────────────────────────────────
export function startInterview(guardianName: string, personaType?: PersonaType, guardianId?: string) {
  return api<InterviewSession>('/phase0/interviews', {
    method: 'POST',
    // guardian_id = 이 인터뷰로 만들 페르소나의 **주인**. 이걸 안 보내면 소유자
    // 없는 페르소나가 되어 등록해 놓고도 목록에 안 뜬다.
    body: JSON.stringify({ guardian_name: guardianName, persona_type: personaType ?? null,
                           guardian_id: guardianId ?? '' }),
  });
}

/**
 * 신고 직전 미니챗 — **Tier1 5문항만** 묻는 인터뷰를 시작한다.
 *
 * 온보딩을 안 한 보호자가 바로 실종신고를 누른 경우다. 12문항 전체를 물으면
 * 골든타임을 대화로 태운다. 서버는 이미 tier 로 슬롯을 좁힐 수 있으므로
 * (`scope: "tier1"` → identity·home·자주 가는 곳·옛 장소·과거 배회 이력 5개)
 * 여기서는 그 스코프를 지정해 세션을 열기만 한다.
 *
 * 두 번 호출하는 이유: `/interviews/sessions` 는 마지막 질문 한 줄만 돌려주는데
 * 화면은 `InterviewSession`(messages 전문·awaiting_confirmation·llm_degraded)을
 * 그린다. 이어지는 답변 전송은 두 엔드포인트가 같은 엔진(answer_interview)을
 * 부르므로 기존 `answerInterview` 를 그대로 쓴다 — 시작 호출만 갈아끼우면 된다.
 */
export async function startTier1Interview(guardianName: string, guardianId?: string) {
  const opened = await api<{ session_id: string }>('/phase0/interviews/sessions', {
    method: 'POST',
    body: JSON.stringify({ guardian_name: guardianName, guardian_id: guardianId ?? '',
                           mode: 'create', scope: 'tier1', persona_type: null }),
  });
  return getInterview(opened.session_id);
}

/** 답변 1건 전송 → 갱신된 세션(다음 질문이 messages 끝에 붙어 온다). */
export function answerInterview(sessionId: string, text: string) {
  return api<InterviewSession>(`/phase0/interviews/${sessionId}/answers`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}

export function getInterview(sessionId: string) {
  return api<InterviewSession>(`/phase0/interviews/${sessionId}`);
}

/** 슬롯 카탈로그 — 진행률의 분모와 답변 예시를 서버에서 받는다(프론트에 박지 않는다). */
export function listSlots(personaType: PersonaType = 'dementia') {
  return api<SlotInfo[]>(`/phase0/slots?persona_type=${personaType}`);
}

/** 페르소나 조회 — 인터뷰가 만든 것을 등록 완료 후 다시 읽어 온다. */
export function getPersona(personaId: string) {
  return api<Persona>(`/phase0/personas/${personaId}`);
}

/** 등록된 가족 목록 — 앱을 다시 켜도 보이려면 스토어가 아니라 서버에서 읽어야 한다. */
export function listPersonas(guardianId?: string) {
  // **항상 내 계정 id 를 보낸다.** 안 보내면 서버가 전체를 돌려주고, 남이 등록한
  // 가족(이름·나이·집 위치)이 내 목록에 섞인다 — 화면 문제가 아니라 개인정보
  // 문제다(현장 제보 08-12). 로그인 전이라 id 가 없으면 빈 목록이 맞다.
  return api<Persona[]>(`/phase0/personas?guardian_id=${encodeURIComponent(guardianId ?? '')}`);
}

/**
 * 부분 수정 — 준 필드만 바뀐다.
 *
 * **인터뷰 추출은 완벽하지 않다.** 같은 답변이 두 슬롯에 중복 저장되거나, 과거
 * 발견 장소가 "가려는 곳"으로 분류되는 것을 실측했다. 그 오류가 그대로 예측
 * 근거가 되므로 보호자가 고칠 수 있어야 한다.
 */
export function updatePersona(personaId: string, patch: {
  name?: string;
  age?: number;
  home?: GeoPoint;
  attraction_points?: AttractionPoint[];
  behavior_notes?: string[];
}) {
  return api<Persona>(`/phase0/personas/${personaId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

/** 인터뷰 종료 → 페르소나 확정. session_id 를 주면 인터뷰 추출값이 함께 들어간다. */
export function registerPersona(body: {
  session_id?: string;
  name: string;
  age: number;
  type: PersonaType;
  home: GeoPoint;
  attraction_points?: AttractionPointIn[];
  behavior_notes?: string[];
  /** 등록하는 보호자 계정. session_id 가 있으면 세션 값이 우선한다. */
  guardian_id?: string;
}) {
  return api<Persona>('/phase0/personas', { method: 'POST', body: JSON.stringify(body) });
}

// ── Phase 1 — 실종 신고 ─────────────────────────────────────────
export function createReport(body: {
  missing_type: PersonaType;
  lkp: GeoPoint;
  lkp_time: string;
  persona_id?: string | null;
  situation?: string;
  appearance?: Partial<Pick<CaseAppearance, 'top' | 'bottom' | 'shoes' | 'etc'>> | null;
}) {
  return api<Case>('/phase1/reports', { method: 'POST', body: JSON.stringify(body) });
}

export function getCase(caseId: string) {
  return api<Case>(`/phase1/cases/${caseId}`);
}

/**
 * 이 기기가 접수한 사건들의 본문(tips 포함).
 *
 * 🚨 `GET /phase3/alerts` 로 활성 사건을 통째로 받지 않는다. 셀 없이 부르면 서버가
 * 빈 목록을 주고(fail-closed), 셀을 줘서 받아 오면 **남의 사건**까지 딸려 온다.
 * 내 사건 id 는 신고할 때 기기에 적어 둔다(store/guardianCaseStore).
 *
 * 종결·파기된 사건은 404 라 조용히 빠진다 — 화면에 남겨 두면 이미 끝난 수색을
 * 계속 붙잡고 있게 된다.
 */
export async function getMyCases(caseIds: readonly string[]) {
  const settled = await Promise.allSettled(caseIds.map((id) => getCase(id)));
  return settled.flatMap((r) => (r.status === 'fulfilled' ? [r.value] : []));
}

/**
 * 좌표 → 사람이 읽는 장소명 (`[서울특별시 성북구] 정릉로`).
 * 이름을 못 찾은 자리는 좌표 문자열로 온다 — 목록이 통째로 죽지 않게.
 */
export async function getAreaLabels(points: GeoPoint[]) {
  if (points.length === 0) return [];
  const res = await api<{ labels: string[] }>('/geo/labels', {
    method: 'POST',
    body: JSON.stringify({ points }),
  });
  return res.labels;
}

/**
 * 장소·주소 문자열 → 좌표. 신고 화면의 '마지막 목격 장소' 검색.
 *
 * `expo-location` 의 `geocodeAsync` 를 쓰면 **안 된다** — 그 함수는 웹에서
 * 동작하지 않는다. 배포본이 웹이라 검색이 늘 실패했고, 좌표가 없으니 지도는
 * 시안 목업(미국 지도)에 머물고 신고 버튼까지 막혔다(현장 제보 08-12).
 *
 * 서버는 온보딩 끌림점과 **같은 지오코더 체인**을 쓴다(카카오 → Nominatim →
 * 지명사전). 두 경로가 같은 좌표를 주어야 예측 근거가 어긋나지 않는다.
 */
export function searchPlace(query: string) {
  return api<{ lat: number; lng: number; label: string; precision: string; source: string }>(
    `/geo/search?q=${encodeURIComponent(query)}`,
  );
}

// ── Phase 2 — 동선 예측 ─────────────────────────────────────────
/**
 * 예측 실행. **10초 안팎 걸린다**(EXAONE 실호출 5회 + 몬테카를로 500명).
 * 신고 완료 화면이 "AI 예상 경로 분석 중"을 띄우는 이유가 이것이다 —
 * 응답을 기다리는 동안 화면이 멈춘 것처럼 보이면 안 된다.
 *
 * 기본 12초 타임아웃을 쓰면 **안 된다.** 웜에서도 11~13초라 반반 실패하고,
 * 새 지역의 첫 실행은 도로망 다운로드로 2분을 넘긴다(신촌 실측 08-12).
 */
export async function runPrediction(caseId: string, seed?: number) {
  const q = seed == null ? '' : `?seed=${seed}`;
  try {
    return await api<{ case_id: string }>(`/phase2/cases/${caseId}/predict${q}`,
                                          { method: 'POST', timeoutMs: SLOW_TIMEOUT_MS });
  } catch (e) {
    // **연결이 끊겨도 서버는 계산을 끝낸다.** 결과가 실제로 생겼는지 확인한다.
    //
    // 공개 경로의 Cloudflare 는 **100초에서 끊는다(524)** — 무료 플랜이라 못 늘린다.
    // 그런데 새 지역의 첫 예측은 도로망을 내려받느라 그걸 넘긴다(실측 08-12:
    // roadnet 84.7초 포함 총 101.4초 → 앱에는 524, 서버에는 POA 정상 생성).
    // 그대로 두면 **성공한 예측을 "AI 분석 실패"로 표시**하게 된다 — 보호자가
    // 다시 시도를 누르면 그제야 (도로망이 데워져) 되는, 설명 불가능한 동작이 된다.
    const done = await pollPoaReady(caseId);
    if (done) return { case_id: caseId };
    throw e;
  }
}

/** POA 가 생겼는지 짧게 확인한다. 생겼으면 예측은 끝난 것이다. */
async function pollPoaReady(caseId: string, tries = 20, gapMs = 6_000): Promise<boolean> {
  for (let i = 0; i < tries; i += 1) {
    try {
      const poa = await api<{ total_cells: number }>(`/phase3/cases/${caseId}/poa?top=1`);
      if ((poa.total_cells ?? 0) > 0) return true;
    } catch {
      // 조회 실패는 무시한다 — 아직 계산 중이거나 일시적 오류다.
    }
    await new Promise((r) => setTimeout(r, gapMs));
  }
  return false;
}
