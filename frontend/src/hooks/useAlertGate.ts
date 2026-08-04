/**
 * 앱 진입 관문 (알림 개인화 #1 넛지의 본체) — 배선부.
 * 판정 규칙 자체는 utils/alertGate.ts 에 순수 함수로 분리돼 있다.
 *
 * ## 무엇을 하는가
 * 경보가 살아 있는 동안에는 앱을 열면 **산책 모드가 아니라 경보 상세가 먼저** 뜬다.
 * 산책 모드로 가려면 "이 사건은 그만 볼래요"를 명시적으로 눌러야 한다.
 *
 * 넛지의 힘은 여기서 나온다: 알림을 무시하는 비용이 0이면 아무도 안 본다.
 * 한 번의 명시적 선택을 요구하는 것만으로 "봤다/안 볼 거다"가 실제 의사결정이 된다.
 * 타겟 셀 안의 시민에게만 도달한다는 전제(온디바이스 지오펜싱) 위에서만 정당화되는
 * 강도다 — 무차별 발송에 이 관문을 붙이면 그냥 민폐다.
 *
 * ## 통과 경로는 두 가지고, 결과가 다르다
 *  - **"못 봤어요"** = 이번 진입만 통과. 앱을 다시 켜면 관문이 또 선다.
 *    목격 여부에 답했을 뿐 "그만 보겠다"고 한 게 아니므로 억제로 치지 않는다.
 *    관문을 유지하는 압력이 이쪽이다.
 *  - **"그만 볼래요"** = 영구 억제(재무장 조건 전까지).
 *
 * "이번만 통과"에 별도 상태가 필요 없는 이유: 관문은 네비게이터 마운트 시점에
 * initialRouteName 으로 한 번만 판정된다. 세션 안에서는 다시 서지 않고, 앱을
 * 다시 켜면 자연히 재판정된다.
 */
import { useActiveAlerts } from './queries';
import { useAppModeStore } from '../store/appModeStore';
import { pickGateCase } from '../utils/alertGate';

export type AlertGate =
  | { pending: true; caseId: null }
  | { pending: false; caseId: string | null };

/**
 * @param enabled 시민 트리에서만 true. 운영자·미인증 화면은 관문 대상이 아니다.
 */
export function useAlertGate(enabled = true): AlertGate {
  const { data, isPending } = useActiveAlerts();
  const dismissedCases = useAppModeStore((s) => s.dismissedCases);

  if (!enabled) return { pending: false, caseId: null };
  // 조회가 끝나기 전에 판정하면 "경보 없음"으로 확정돼 관문이 영영 안 선다
  // (initialRouteName 은 마운트 시점에 한 번만 읽힌다). 호출부는 이 동안 대기해야 한다.
  if (isPending) return { pending: true, caseId: null };

  return { pending: false, caseId: pickGateCase(data ?? [], dismissedCases) };
}

export default useAlertGate;
