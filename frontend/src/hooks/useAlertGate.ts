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
import { alertsForMe, pickGateCase } from '../utils/alertGate';
import type { GeoPoint, PoliceAlert } from '../types/domain';

/**
 * 측위를 이만큼 기다렸는데도 결론이 없으면 그냥 진행한다.
 *
 * 기다리는 이유: 위치를 모른 채 판정하면 fail-open 으로 관문이 떴다가, 잠시 뒤
 * "구역 밖"으로 밝혀지며 사라진다 — 긴급 화면이 깜빡이는 최악의 경험.
 * 그렇다고 무한정 기다리면 권한 팝업을 안 누른 사용자에게 앱이 영영 안 열린다.
 */
const LOCATION_WAIT_MS = 4000;

export type AlertGate =
  | { pending: true; caseId: null }
  | { pending: false; caseId: string | null };

/** 지금 **나에게 해당되는** 경보들 (지오펜스 통과분). 화면들의 단일 창구. */
export function useAlertsForMe(enabled = true): {
  pending: boolean;
  alerts: PoliceAlert[];
  myPoint: GeoPoint | null;
} {
  const { data, isPending } = useActiveAlerts();
  const { point, status } = useMyLocation(enabled);
  const forceInArea = useDebugStore((s) => s.forceInAlertArea);

  const [waitedForLocation, setWaitedForLocation] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setWaitedForLocation(true), LOCATION_WAIT_MS);
    return () => clearTimeout(id);
  }, []);

  if (!enabled) return { pending: false, alerts: [], myPoint: null };

  const locationReady = isLocationSettled(status) || waitedForLocation;
  if (isPending || !locationReady) return { pending: true, alerts: [], myPoint: point };

  const all = data ?? [];
  // 데모 오버라이드는 지오펜스만 건너뛴다 — 억제·재무장 규칙은 그대로 탄다.
  return { pending: false, alerts: forceInArea ? [...all] : alertsForMe(all, point), myPoint: point };
}

/**
 * @param enabled 시민 트리에서만 true. 운영자·미인증 화면은 관문 대상이 아니다.
 */
export function useAlertGate(enabled = true): AlertGate {
  const { data, isPending } = useActiveAlerts();
  const { point, status } = useMyLocation(enabled);
  const dismissedCases = useAppModeStore((s) => s.dismissedCases);
  const forceInArea = useDebugStore((s) => s.forceInAlertArea);

  const [waitedForLocation, setWaitedForLocation] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setWaitedForLocation(true), LOCATION_WAIT_MS);
    return () => clearTimeout(id);
  }, []);

  if (!enabled) return { pending: false, caseId: null };

  // 조회가 끝나기 전에 판정하면 "경보 없음"으로 확정돼 관문이 안 선다.
  // 호출부(RootNavigator)는 이 동안 네비게이터를 마운트하지 않고 기다린다.
  const locationReady = isLocationSettled(status) || waitedForLocation;
  if (isPending || !locationReady) return { pending: true, caseId: null };

  // forceInAlertArea 일 때 좌표를 null 로 넘기면 지오펜스가 fail-open 으로
  // 통과한다 — 판정 경로를 하나로 유지하기 위해 별도 분기를 두지 않는다.
  const geofencePoint = forceInArea ? null : point;
  return { pending: false, caseId: pickGateCase(data ?? [], dismissedCases, geofencePoint) };
}

export default useAlertGate;
