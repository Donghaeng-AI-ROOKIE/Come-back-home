/**
 * 경보 진입 관문의 **판정 규칙** (알림 개인화 #1).
 *
 * 네비게이션·React 에서 떼어낸 순수 함수만 둔다. 배선은 hooks/useAlertGate.ts.
 * 분리한 이유: 이 규칙이 기능의 본체이고 경계 조건(재무장·시각 역전·파싱 실패)이
 * 까다로워서, 앱을 띄우지 않고도 검사할 수 있어야 하기 때문.
 */
import type { GeoPoint, PoliceAlert } from '../types/domain';
import { distanceM } from './geo';

/**
 * 이 경보가 **나에게 해당되는가** — 온디바이스 지오펜싱의 판정부.
 *
 * 서버는 대상 구역만 뿌리고 내 위치는 모른다. 그 안에 있는지는 폰이 정한다.
 * 이 판정이 없으면 알림이 무차별 발송이 되고, 9km 떨어진 사람에게도 전체화면
 * 관문이 서는 일이 생긴다 — "타겟 알림"이라는 서비스 전제가 무너지는 지점이다.
 *
 * ⚠️ **위치를 모르면 해당된다고 본다(fail-open).** 근거: 실종 골든타임에서
 * 잘못 울린 알림의 비용(성가심)보다 놓친 알림의 비용(사람을 못 찾음)이 압도적으로
 * 크다. 위치 권한을 껐다고 경보를 감추면, 권한 거부가 곧 알림 차단이 되어버린다.
 * 대신 이 경우 거리·구역 문구는 숫자 없이 물러나므로 거짓 주장은 하지 않는다.
 */
export function alertAppliesToMe(alert: PoliceAlert, myPoint: GeoPoint | null): boolean {
  if (myPoint == null) return true; // 판정 불가 → fail-open (위 주석)
  if (!Number.isFinite(alert.targetRadiusM) || alert.targetRadiusM <= 0) return true;
  return distanceM(myPoint, alert.targetCenter) <= alert.targetRadiusM;
}

/**
 * 억제를 뚫고 관문을 다시 세우는 알림 종류.
 *
 * reflex(D1 골든타임)·new_region(새 지역 목격)은 "같은 얘기 또 하기"가 아니라
 * 새로 생긴 위험이다. 진짜 급한 알림이 사용자 조작 한 번으로 영영 묻히면 안 되므로
 * 억제를 존중하지 않는다 — 서버 피로도 예산의 `kind == "reflex"` 면제와 같은 원칙.
 * 반대로 poa 재알림은 같은 내용의 반복이라 억제를 그대로 지킨다.
 */
export const REARMING_KINDS: ReadonlySet<PoliceAlert['kind']> = new Set(['reflex', 'new_region']);

/**
 * 이 경보가 진입 관문을 세워야 하는가.
 *
 * @param dismissedAt 이 사건을 "그만 볼래요"로 끈 시각(ms). 안 껐으면 undefined.
 */
export function shouldGate(alert: PoliceAlert, dismissedAt: number | undefined): boolean {
  if (dismissedAt === undefined) return true; // 아직 아무 의사표시 없음

  const issuedAt = Date.parse(alert.issuedAt);
  // 발령 시각을 못 읽으면 억제를 존중한다. 판정 불능을 "다시 띄우기"로 해석하면
  // 파싱 버그 하나가 무한 관문이 된다 — 실패는 조용한 쪽으로 기운다.
  if (Number.isNaN(issuedAt)) return false;

  // 내가 이미 보고 끈 그 경보. 억제 시각과 동일한 순간까지 포함(<=)한다.
  if (issuedAt <= dismissedAt) return false;

  return REARMING_KINDS.has(alert.kind);
}

/**
 * 나에게 해당되는(= 대상 구역 안) 경보만 추린다.
 * 화면들이 "지금 나에게 유효한 경보"를 물어보는 단일 창구.
 */
export function alertsForMe(
  alerts: readonly PoliceAlert[],
  myPoint: GeoPoint | null,
): PoliceAlert[] {
  return alerts.filter((a) => alertAppliesToMe(a, myPoint));
}

/**
 * 관문을 세워야 하는 첫 경보의 caseId. 없으면 null.
 *
 * 순서가 중요하다: **지오펜스를 먼저** 통과해야 억제/재무장 판정으로 넘어간다.
 * 구역 밖 경보는 애초에 나에게 온 적이 없는 것이므로 "안볼래요"를 누를 일도 없다.
 */
export function pickGateCase(
  alerts: readonly PoliceAlert[],
  dismissedCases: Readonly<Record<string, number>>,
  myPoint: GeoPoint | null,
): string | null {
  const gating = alertsForMe(alerts, myPoint).find((a) =>
    shouldGate(a, dismissedCases[a.caseId]),
  );
  return gating?.caseId ?? null;
}
