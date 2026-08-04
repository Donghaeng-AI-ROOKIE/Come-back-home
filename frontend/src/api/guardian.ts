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
  filled_keys: string[];
  done?: boolean;
};

export type AttractionPointIn = {
  label: string;
  location: GeoPoint;
  weight?: number;
  place_type?: string;
};

export type Persona = {
  id: string;
  name: string;
  age: number;
  type: PersonaType;
  home: GeoPoint;
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
  with_photo?: boolean;
  with_document?: boolean;
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
