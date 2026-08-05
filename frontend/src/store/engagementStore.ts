/**
 * 알림 참여 이력 (알림 개인화 #8) — 피로도 예산의 입력.
 *
 * ## 이 데이터는 기기를 떠나지 않는다
 * 열람·제보 이력을 서버로 올리면 "익명 제보" 약속이 깨지고, 서버가 시민 개개인의
 * 관심사를 알게 된다. **API 요청 바디에 이 스토어의 값을 싣지 말 것.**
 * 판정 규칙은 utils/alertBudget.ts 에 순수 함수로 있다.
 *
 * ## 왜 영속화하는가
 * 앱을 끌 때마다 초기화되면 "여러 번 껐다"는 신호가 쌓이지 않아 기능이 성립하지
 * 않는다. 다만 그만큼 **기기에 관심사 흔적이 남는다** — 그래서 서버로 안 보내는
 * 경계가 더 중요해지고, 사용자가 지울 수 있어야 한다(reset).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { EngagementSignals } from '../utils/alertBudget';
import { EMPTY_SIGNALS, engagementLevel } from '../utils/alertBudget';

type EngagementState = EngagementSignals & {
  /** 자발적으로 경보를 열었을 때(벨·알림 탭). 관문에 강제로 뜬 건 세지 않는다. */
  recordOpened: () => void;
  /** 제보 전송 완료. */
  recordReported: () => void;
  /** "그만 볼래요". */
  recordDismissed: () => void;
  /** 사용자가 이력을 지울 때 — 기기에 남은 관심사 흔적을 되돌리는 유일한 경로. */
  reset: () => void;
};

export const useEngagementStore = create<EngagementState>()(
  persist(
    (set) => ({
      ...EMPTY_SIGNALS,
      recordOpened: () => set((s) => ({ opened: s.opened + 1 })),
      recordReported: () => set((s) => ({ reported: s.reported + 1 })),
      recordDismissed: () => set((s) => ({ dismissed: s.dismissed + 1 })),
      reset: () => set({ ...EMPTY_SIGNALS }),
    }),
    {
      name: 'engagement-v1',
      storage: createJSONStorage(() => AsyncStorage),
      // 함수는 빼고 숫자만 저장한다.
      partialize: (s) => ({ opened: s.opened, reported: s.reported, dismissed: s.dismissed }),
    },
  ),
);

/** 현재 참여도 등급. 관문 판정이 이 값을 쓴다. */
export function useEngagementLevel() {
  return useEngagementStore((s) =>
    engagementLevel({ opened: s.opened, reported: s.reported, dismissed: s.dismissed }),
  );
}
