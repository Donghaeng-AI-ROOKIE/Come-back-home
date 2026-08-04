/**
 * 산책 ↔ 수색 전역 모드 (spec §2.4). 화면 이동이 아니라 상태 전환.
 * 전환은 오직 이벤트로: 경찰 실종경보 연동(enterSearch) / 사건 종료(closeCase).
 * 보호자는 앱에서 수동 발동하지 않는다.
 *
 * 넛지 게이트(알림 개인화 #1 "안볼래요"): dismissedCases 가 사건별 재촉 UI를 끈다.
 */
import { create } from 'zustand';
import type { AppMode, Severity } from '../types/domain';

type AppModeState = {
  mode: AppMode; // 기본 walk
  activeCaseId: string | null;
  severity: Severity; // critical=빨강 / active=앰버
  enteredSearchAt: number | null; // 골든타임 카운트다운 기준(초는 저장 안 함, 파생 계산)
  /** "안볼래요" 처리된 사건 → 처리 시각(ms). 넛지 억제 판정의 단일 소스. */
  dismissedCases: Record<string, number>;

  /** 경찰 실종경보 연동 → 수색 모드 진입. */
  enterSearch: (caseId: string, severity?: Severity) => void;
  /** 심각도 강등(긴급→진행). */
  setSeverity: (severity: Severity) => void;
  /** "안볼래요" — 이 사건의 재촉 UI를 끈다(경보 도달 자체는 막지 않음). */
  dismissCase: (caseId: string) => void;
  /** 넛지 복구 — 다시 보기. */
  restoreCase: (caseId: string) => void;
  /** 사건 종료 → 산책 모드 복귀. */
  closeCase: () => void;
  reset: () => void;
};

const IDLE = {
  mode: 'walk' as const,
  activeCaseId: null,
  severity: 'active' as const,
  enteredSearchAt: null,
};

export const useAppModeStore = create<AppModeState>((set) => ({
  ...IDLE,
  dismissedCases: {},

  enterSearch: (caseId, severity = 'critical') =>
    set((s) => ({
      mode: 'search',
      activeCaseId: caseId,
      severity,
      enteredSearchAt: s.enteredSearchAt ?? Date.now(),
    })),
  setSeverity: (severity) => set({ severity }),

  dismissCase: (caseId) =>
    set((s) => ({ dismissedCases: { ...s.dismissedCases, [caseId]: Date.now() } })),
  restoreCase: (caseId) =>
    set((s) => {
      // 키를 남기고 값을 비우면 "억제 해제"와 "억제 중"이 구분되지 않는다 — 항목 자체를 뺀다.
      const { [caseId]: _removed, ...rest } = s.dismissedCases;
      return { dismissedCases: rest };
    }),

  // 종결된 사건의 억제 기록은 의미가 없다. 남겨두면 같은 id 가 재사용될 때
  // (데모 리셋·재신고) 새 경보가 조용히 억제된 채 시작된다 — 여기서 반드시 턴다.
  closeCase: () =>
    set((s) => {
      if (s.activeCaseId === null) return IDLE;
      const { [s.activeCaseId]: _closed, ...rest } = s.dismissedCases;
      return { ...IDLE, dismissedCases: rest };
    }),
  reset: () => set({ ...IDLE, dismissedCases: {} }),
}));

/**
 * 이 사건의 넛지가 꺼져 있는가.
 *
 * ⚠️ 억제 대상은 **재촉 UI(홈 배지·배너)** 뿐이다. 경보 도달 자체나 긴급 경보 화면
 * 진입은 막지 않는다 — iOS 는 이미 도착한 푸시를 앱이 억제할 수 없고(권한 밖),
 * 골든타임 reflex 알림이 사용자 조작 한 번으로 묻히면 안 되기 때문.
 * 서버측 피로도 예산의 `kind == "reflex"` 면제와 같은 원칙.
 */
export function useIsCaseDismissed(caseId: string | null | undefined): boolean {
  return useAppModeStore((s) => (caseId ? s.dismissedCases[caseId] !== undefined : false));
}
