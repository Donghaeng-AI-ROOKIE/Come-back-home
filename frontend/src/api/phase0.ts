/**
 * Phase 0 — 보호자 사전등록 인터뷰 (백엔드 `app/api/phase0.py`).
 *
 * 대화를 **서버가 몬다.** 다음에 무엇을 물을지는 검색(phase0.retrieval)이 고르고,
 * Mi:dm 이 그 슬롯을 존댓말 질문으로 문장화하고 답변에서 값을 추출한다. 그래서
 * 프론트는 질문 목록을 갖지 않는다 — 매 턴 서버가 돌려준 `messages` 를 그대로
 * 그린다. 프론트에 질문을 박아 두면 서버의 적응형 순서와 어긋난다.
 *
 * `MIDM_MODEL` 이 비어 있으면 백엔드가 결정적 스텁으로 폴백한다. 이때도 세션·
 * 슬롯·페르소나 생성은 정상 동작하고 질문 문장만 고정된다 — 그 상태는
 * `llm_degraded` 로 구분한다(문장화 실패가 누적된 경우).
 */
import { api } from './config';

/** 백엔드 `PersonaType` — 치매 단독 스코프(2026-08-03). */
export type PersonaType = 'dementia';

export type InterviewMessage = {
  role: 'assistant' | 'user';
  text: string;
};

/** 백엔드 `InterviewSession` 중 프론트가 쓰는 필드만. 나머지는 무시해도 안전하다. */
export type InterviewSession = {
  id: string;
  guardian_name: string;
  persona_type: PersonaType | null;
  messages: InterviewMessage[];
  /** 값이 채워진 슬롯 키 — 진행률 계산에 쓴다(프론트 단계 인덱스가 아니라 이것이 진실). */
  filled_keys: string[];
  /** 서버가 지금 묻고 있는 슬롯. 빠른응답 칩을 고를 때 쓴다. */
  prev_target_key: string | null;
  draft_fields: Record<string, unknown>;
  draft_attractions: unknown[];
  draft_behaviors: string[];
  /** 마지막 확인("이대로 등록할까요?") 대기 중. */
  awaiting_confirmation: boolean;
  /** Mi:dm 호출이 반복 실패해 스텁 문장으로 떨어진 상태. 배너로 알린다. */
  llm_degraded: boolean;
  llm_call_failures: number;
  done: boolean;
  /** 완료 시 생성된 페르소나 ID. 이후 신고·예측이 이 값을 쓴다. */
  persona_id: string | null;
};

export type SlotInfo = {
  key: string;
  label: string;
  axis: string;
  axis_field: string | null;
  /** 1=필수 · 2=중요 · 3=보조. 서버가 이 순서를 우선한다. */
  tier: number;
  /**
   * 답변 예시(슬롯 카탈로그 원문). 음성 인식이 붙기 전까지 마이크 버튼이 이 문구를
   * 입력창에 채워 보호자가 눈높이를 보고 고쳐 쓰게 한다 — 프론트가 예시를 지어내면
   * 서버 슬롯과 어긋나므로 반드시 서버 값을 쓴다.
   */
  answer_example: string;
};

/** 인터뷰 시작 — 첫 질문이 담긴 세션을 돌려준다. */
export function startInterview(
  guardianName: string,
  personaType: PersonaType = 'dementia',
): Promise<InterviewSession> {
  return api<InterviewSession>('/phase0/interviews', {
    method: 'POST',
    body: JSON.stringify({ guardian_name: guardianName, persona_type: personaType }),
  });
}

/** 답변 전송 — 갱신된 세션(사용자 발화 + 다음 질문 포함)을 돌려준다. */
export function answerInterview(sessionId: string, text: string): Promise<InterviewSession> {
  return api<InterviewSession>(`/phase0/interviews/${sessionId}/answers`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}

/** 세션 재조회 — 앱이 죽었다 살아났을 때 대화를 복원한다. */
export function getInterview(sessionId: string): Promise<InterviewSession> {
  return api<InterviewSession>(`/phase0/interviews/${sessionId}`);
}

/** 슬롯 카탈로그 — 진행률의 분모와 라벨을 서버에서 받는다(프론트에 박지 않는다). */
export function listSlots(personaType: PersonaType = 'dementia'): Promise<SlotInfo[]> {
  return api<SlotInfo[]>(`/phase0/slots?persona_type=${personaType}`);
}

/**
 * 인터뷰가 `done` 이면 서버가 페르소나를 이미 만들어 `persona_id` 를 채운다.
 * 이 함수는 인터뷰를 건너뛰고 값을 직접 넣어 등록할 때만 쓴다(대시보드·테스트).
 */
export function registerPersona(body: {
  session_id?: string;
  name: string;
  age: number;
  type: PersonaType;
  home: { lat: number; lng: number };
  attraction_points?: unknown[];
  behavior_notes?: string[];
}): Promise<{ id: string }> {
  return api<{ id: string }>('/phase0/personas', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
