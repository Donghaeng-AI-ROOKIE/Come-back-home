/**
 * 경보 진입 관문의 **판정 규칙** (알림 개인화 #1).
 *
 * 네비게이션·React 에서 떼어낸 순수 함수만 둔다. 배선은 hooks/useAlertGate.ts.
 * 분리한 이유: 이 규칙이 기능의 본체이고 경계 조건(재무장·시각 역전·파싱 실패)이
 * 까다로워서, 앱을 띄우지 않고도 검사할 수 있어야 하기 때문.
 */
import type { PoliceAlert } from '../types/domain';

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

/** 관문을 세워야 하는 첫 경보의 caseId. 없으면 null. */
export function pickGateCase(
  alerts: readonly PoliceAlert[],
  dismissedCases: Readonly<Record<string, number>>,
): string | null {
  const gating = alerts.find((a) => shouldGate(a, dismissedCases[a.caseId]));
  return gating?.caseId ?? null;
}
