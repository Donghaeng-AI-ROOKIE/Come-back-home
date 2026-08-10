/**
 * 보호자의 진행 중 신고 케이스 — 기기 영속.
 *
 * 서버에는 "이 보호자의 케이스 목록" API 가 없다(계정-케이스 바인딩 자체가 없다).
 * 그래서 신고를 접수한 기기가 케이스 id 를 스스로 기억해야, 앱을 껐다 켜도
 * 알림 탭이 제보 현황을 이어서 보여줄 수 있다.
 *
 * 신고 접수의 유일한 착지점인 ReportSentScreen 에서 기록한다 — 신고 경로가
 * 늘어나도 전부 그 화면을 거치므로 여기 하나로 충분하다.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

type GuardianCaseState = {
  /** 마지막으로 접수한 신고의 케이스 id. null = 신고 이력 없음. */
  lastCaseId: string | null;
  setLastCase: (caseId: string) => void;
  clear: () => void;
};

export const useGuardianCaseStore = create<GuardianCaseState>()(
  persist(
    (set) => ({
      lastCaseId: null,
      setLastCase: (caseId) => set({ lastCaseId: caseId }),
      clear: () => set({ lastCaseId: null }),
    }),
    {
      name: 'guardian-case-v1',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (s) => ({ lastCaseId: s.lastCaseId }),
    },
  ),
);
