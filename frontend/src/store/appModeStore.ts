/**
 * 산책 ↔ 수색 전역 모드 (spec §2.4). 화면 이동이 아니라 상태 전환.
 * 전환은 오직 이벤트로: 경찰 실종경보 연동(enterSearch) / 사건 종료(closeCase).
 * 보호자는 앱에서 수동 발동하지 않는다.
 */
import { create } from 'zustand';
import type { AppMode, Severity } from '../types/domain';

type AppModeState = {
  mode: AppMode; // 기본 walk
  activeCaseId: string | null;
  severity: Severity; // critical=빨강 / active=앰버
  enteredSearchAt: number | null; // 골든타임 카운트다운 기준(초는 저장 안 함, 파생 계산)

  /** 경찰 실종경보 연동 → 수색 모드 진입. */
  enterSearch: (caseId: string, severity?: Severity) => void;
  /** 심각도 강등(긴급→진행). */
  setSeverity: (severity: Severity) => void;
  /** 사건 종료 → 산책 모드 복귀. */
  closeCase: () => void;
  reset: () => void;
};

export const useAppModeStore = create<AppModeState>((set) => ({
  mode: 'walk',
  activeCaseId: null,
  severity: 'active',
  enteredSearchAt: null,

  enterSearch: (caseId, severity = 'critical') =>
    set((s) => ({
      mode: 'search',
      activeCaseId: caseId,
      severity,
      enteredSearchAt: s.enteredSearchAt ?? Date.now(),
    })),
  setSeverity: (severity) => set({ severity }),
  closeCase: () => set({ mode: 'walk', activeCaseId: null, severity: 'active', enteredSearchAt: null }),
  reset: () => set({ mode: 'walk', activeCaseId: null, severity: 'active', enteredSearchAt: null }),
}));
