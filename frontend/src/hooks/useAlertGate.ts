/**
 * 앱 진입 관문 (알림 개인화 #1 넛지의 본체) — 배선부.
 * 판정 규칙 자체는 utils/alertGate.ts 에 순수 함수로 분리돼 있다.
 *
 * ## 무엇을 하는가
 * **내가 알림 대상 구역 안에 있고** 경보가 살아 있는 동안에는, 앱을 열면 산책 모드가
 * 아니라 경보 상세가 먼저 뜬다. 산책 모드로 가려면 "이 사건은 그만 볼래요"를
 * 명시적으로 눌러야 한다.
 *
 * 넛지의 힘은 여기서 나온다: 알림을 무시하는 비용이 0이면 아무도 안 본다. 한 번의
 * 명시적 선택을 요구하는 것만으로 "봤다/안 볼 거다"가 실제 의사결정이 된다.
 * 다만 이 강도는 **타겟 셀 안의 시민에게만 도달한다**는 전제 위에서만 정당화된다 —
 * 그래서 지오펜스가 이 기능의 선행 조건이지 부가 기능이 아니다.
 *
 * ## 통과 경로는 두 가지고, 결과가 다르다
 *  - **"못 봤어요"** = 이번 진입만 통과. 앱을 다시 켜면 관문이 또 선다.
 *    목격 여부에 답했을 뿐 "그만 보겠다"고 한 게 아니므로 억제로 치지 않는다.
 *  - **"그만 볼래요"** = 영구 억제(재무장 조건 전까지).
 */
import { useEffect, useState } from 'react';
import { useActiveAlerts } from './queries';
import { useMyLocation, isLocationSettled } from './useMyLocation';
import { useAppModeStore } from '../store/appModeStore';
import { useDebugStore } from '../store/debugStore';
import { useEngagementLevel } from '../store/engagementStore';
import { alertsForMe, pickGateCase } from '../utils/alertGate';
import type { GeoPoint, PoliceAlert } from '../types/domain';

/**
 * 측위를 이만큼 기다렸는데도 결론이 없으면 그냥 진행한다(= 위치 없음으로 확정).
 *
 * 기다리는 이유: 위치를 모른 채 판정하면 fail-closed 로 "경보 없음"이 확정돼,
 * 잠시 뒤 측위가 끝나도 관문이 서지 않는다. 그렇다고 무한정 기다리면 권한
 * 팝업을 안 누른 사용자에게 앱이 영영 안 열린다.
 */
const BOOT_WAIT_MS = 6000;

export type AlertGate =
  | { pending: true; caseId: null }
  | { pending: false; caseId: string | null };

/** 지금 **나에게 해당되는** 경보들 (지오펜스 통과분). 화면들의 단일 창구. */
export function useAlertsForMe(enabled = true): {
  pending: boolean;
  alerts: PoliceAlert[];
  myPoint: GeoPoint | null;
} {
  const { data, isPending } = useActiveAlerts(enabled);
  const { point, status } = useMyLocation(enabled);
  const forceInArea = useDebugStore((s) => s.forceInAlertArea);

  const [waited, setWaited] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setWaited(true), BOOT_WAIT_MS);
    return () => clearTimeout(id);
  }, []);

  if (!enabled) return { pending: false, alerts: [], myPoint: null };

  const locationReady = isLocationSettled(status) || waited;
  if (isPending || !locationReady) return { pending: true, alerts: [], myPoint: point };

  // 데모 오버라이드는 지오펜스만 건너뛴다 — 확률 문턱·억제·재무장은 그대로 탄다.
  return { pending: false, alerts: alertsForMe(data ?? [], point, forceInArea), myPoint: point };
}

/**
 * @param enabled 시민 트리에서만 true. 운영자·미인증 화면은 관문 대상이 아니다.
 */
export function useAlertGate(enabled = true): AlertGate {
  const { data, isPending } = useActiveAlerts(enabled);
  const { point, status } = useMyLocation(enabled);
  const dismissedCases = useAppModeStore((s) => s.dismissedCases);
  const forceInArea = useDebugStore((s) => s.forceInAlertArea);
  // 피로도 예산 — 알림을 눌러보는 사람에겐 넓게, 꺼버리는 사람에겐 중요한 것만.
  // 신호는 기기 안에만 있으므로 판정도 여기서 한다(utils/alertBudget.ts).
  const level = useEngagementLevel();


  const [waited, setWaited] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setWaited(true), BOOT_WAIT_MS);
    return () => clearTimeout(id);
  }, []);

  if (!enabled) return { pending: false, caseId: null };

  // 조회가 끝나기 전에 판정하면 "경보 없음"으로 확정돼 관문이 안 선다.
  // 호출부(RootNavigator)는 이 동안 네비게이터를 마운트하지 않고 기다린다.
  const locationReady = isLocationSettled(status) || waited;
  if (isPending || !locationReady) return { pending: true, caseId: null };

  return {
    pending: false,
    caseId: pickGateCase(data ?? [], dismissedCases, point, level, forceInArea),
  };
}

export default useAlertGate;
