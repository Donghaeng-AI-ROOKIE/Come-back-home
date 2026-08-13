/**
 * 보호자 플로우 상태 — 등록된 페르소나와 진행 중인 케이스.
 *
 * 신고 화면이 "사전 등록해 둔 정보를 불러왔습니다"를 띄우려면 등록 결과를
 * 들고 있어야 한다. 서버에는 personas 조회가 있지만 보호자↔페르소나를 잇는
 * 인증이 아직 없어, 앱이 방금 만든 것을 기억하는 방식으로 둔다.
 *
 * **인증이 붙으면 이 스토어는 서버 조회로 대체해야 한다** — 앱을 지우면
 * 등록이 사라진 것처럼 보이는 현재 동작은 임시다.
 */
import { create } from 'zustand';
import type { Persona } from '../api/guardian';

type GuardianState = {
  persona: Persona | null;
  caseId: string | null;
  setPersona: (p: Persona) => void;
  setCaseId: (id: string) => void;
  reset: () => void;
};

export const useGuardianStore = create<GuardianState>((set) => ({
  persona: null,
  caseId: null,
  setPersona: (persona) => set({ persona }),
  setCaseId: (caseId) => set({ caseId }),
  reset: () => set({ persona: null, caseId: null }),
}));
