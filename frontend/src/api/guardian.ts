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
import { api } from './config';

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

export type Case = {
  id: string;
  status: string;
  lkp: GeoPoint;
  lkp_time: string;
  persona_id?: string | null;
};

// ── Phase 0 — 사전등록 인터뷰 ────────────────────────────────────
export function startInterview(guardianName: string, personaType?: PersonaType) {
  return api<InterviewSession>('/phase0/interviews', {
    method: 'POST',
    body: JSON.stringify({ guardian_name: guardianName, persona_type: personaType ?? null }),
  });
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
export function listPersonas() {
  return api<Persona[]>('/phase0/personas');
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
  appearance?: {
    top_color?: string | null;
    bottom_color?: string | null;
    shoes?: string | null;
    accessories?: string[];
  } | null;
}) {
  return api<Case>('/phase1/reports', { method: 'POST', body: JSON.stringify(body) });
}

export function getCase(caseId: string) {
  return api<Case>(`/phase1/cases/${caseId}`);
}

// ── Phase 2 — 동선 예측 ─────────────────────────────────────────
/**
 * 예측 실행. **10초 안팎 걸린다**(EXAONE 실호출 5회 + 몬테카를로 500명).
 * 신고 완료 화면이 "AI 예상 경로 분석 중"을 띄우는 이유가 이것이다 —
 * 응답을 기다리는 동안 화면이 멈춘 것처럼 보이면 안 된다.
 */
export function runPrediction(caseId: string, seed?: number) {
  const q = seed == null ? '' : `?seed=${seed}`;
  return api<{ case_id: string }>(`/phase2/cases/${caseId}/predict${q}`, { method: 'POST' });
}
