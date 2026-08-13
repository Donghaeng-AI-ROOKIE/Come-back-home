/**
 * 이 기기가 접수한 신고 케이스 — 기기 영속.
 *
 * ## 왜 기기가 기억하나
 * 서버에는 "이 보호자의 케이스 목록" API 가 없다 — 계정-케이스 바인딩 자체가 없다.
 * 그렇다고 `GET /phase3/alerts` 로 활성 사건을 통째로 받아 오면 **남의 실종 사건과
 * 제보 원문까지** 보호자 화면에 뜬다. 백엔드가 그 경로를 fail-closed 로 막아 둔
 * 이유가 그것이다(api/phase3.list_active_alerts 주석). 그래서 신고를 접수한 기기가
 * 자기 케이스 id 를 기억하고, 그 사건만 `GET /phase1/cases/{id}` 로 읽는다.
 *
 * 여러 건을 담는 이유: 한 보호자가 두 분을 등록했거나, 이전 사건이 아직 안 끝난
 * 채로 새로 신고할 수 있다. 종결된 사건은 조회에서 404 가 나므로 화면이 걸러낸다.
 */
import { safeStorage } from './safeStorage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

/** 기기에 남기는 최대 건수 — 오래된 것부터 밀어낸다. */
const MAX_KEEP = 10;

type GuardianCaseState = {
  /** 최근 접수 순(앞이 최신). */
  caseIds: string[];
  addCase: (caseId: string) => void;
  removeCase: (caseId: string) => void;
  clear: () => void;
};

export const useGuardianCaseStore = create<GuardianCaseState>()(
  persist(
    (set) => ({
      caseIds: [],
      addCase: (caseId) =>
        set((s) => ({ caseIds: [caseId, ...s.caseIds.filter((id) => id !== caseId)].slice(0, MAX_KEEP) })),
      removeCase: (caseId) => set((s) => ({ caseIds: s.caseIds.filter((id) => id !== caseId) })),
      clear: () => set({ caseIds: [] }),
    }),
    {
      name: 'guardian-case-v2',
      storage: createJSONStorage(() => safeStorage),
      partialize: (s) => ({ caseIds: s.caseIds }),
    },
  ),
);
