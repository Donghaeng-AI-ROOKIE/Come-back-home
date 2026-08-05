/**
 * 경보 진입 관문의 **판정 규칙** (알림 개인화 #1).
 *
 * 네비게이션·React 에서 떼어낸 순수 함수만 둔다. 배선은 hooks/useAlertGate.ts.
 * 분리한 이유: 이 규칙이 기능의 본체이고 경계 조건(재무장·시각 역전·파싱 실패)이
 * 까다로워서, 앱을 띄우지 않고도 검사할 수 있어야 하기 때문.
 */
import type { GeoPoint, PoaGrid, PoliceAlert } from '../types/domain';
import { distanceM, pointInPolygon } from './geo';
import { isWorthGating, rearmsAfterDismissal } from './alertBudget';
import type { EngagementLevel } from './alertBudget';

/**
 * 이 경보가 **나에게 해당되는가** — 온디바이스 지오펜싱의 판정부.
 *
 * 서버는 대상 구역만 뿌리고 내 위치는 모른다. 그 안에 있는지는 폰이 정한다.
 * 이 판정이 없으면 알림이 무차별 발송이 되고, 9km 떨어진 사람에게도 전체화면
 * 관문이 서는 일이 생긴다 — "타겟 알림"이라는 서비스 전제가 무너지는 지점이다.
 *
 * ## ⚠️ 위치를 모르면 **해당되지 않는다고 본다(fail-closed)** — 2026-08-05 확정
 * 한때 fail-open("놓친 알림이 성가신 알림보다 비싸다")이었는데 뒤집었다.
 * 결정적 근거: **모든 사람에게 같은 실종자가 뜨는 게 아니다.** 동시에 여러 사건이
 * 진행될 수 있고 위치에 따라 각자 다른 경보를 받는다. 위치를 모르면 "이 사람에게
 * 어느 경보가 해당되는지" 자체를 고를 수 없고, 그 상태에서 아무거나 띄우면
 * **틀린 사건**을 보여주게 된다. 놓치는 것보다 나쁘다.
 *
 * 🚨 대가: **위치 권한을 끄면 경보를 못 받는다.** 조용한 실패가 되지 않도록
 * 홈에서 그 사실을 알려야 한다(CitizenHomeScreen 의 위치 안내 문구).
 */
export function alertAppliesToMe(alert: PoliceAlert, myPoint: GeoPoint | null): boolean {
  if (myPoint == null) return false; // 판정 불가 → fail-closed (위 주석)
  if (!Number.isFinite(alert.targetRadiusM) || alert.targetRadiusM <= 0) return true;
  return distanceM(myPoint, alert.targetCenter) <= alert.targetRadiusM;
}

/**
 * 이 경보가 진입 관문을 세워야 하는가.
 *
 * ## 🚨 확률 문턱은 여기서 보지 않는다 (2026-08-05 확정)
 * 확률 문턱(피로도 예산)은 **푸시를 보낼지**의 기준이지 관문의 기준이 아니다.
 * 관문은 사용자가 **직접 앱을 연** 순간의 이야기이므로, 대상 구역 안에 사건이
 * 있으면 보여주는 게 맞다 — 확률이 낮다고 "당신 주변에 실종자가 있다"는 사실을
 * 숨길 이유가 없다. 발송은 alertBudget.meetsAlertThreshold 가 담당한다.
 *
 * 그래서 관문 판정은 두 가지만 본다.
 *   1) 참여도로 관문을 막지 않는다(항상 통과)
 *   2) 억제됐다면, 억제 **이후** 발령된 것이고 억제를 뚫는 종류인가
 *
 * @param dismissedAt 이 사건을 "그만 볼래요"로 끈 시각(ms). 안 껐으면 undefined.
 * @param level 참여도 등급. 억제된 사건이 얼마나 쉽게 돌아오는지에만 쓰인다.
 */
export function shouldGate(
  alert: PoliceAlert,
  dismissedAt: number | undefined,
  level: EngagementLevel = 'normal',
): boolean {
  if (!isWorthGating(alert.kind, level)) return false;

  if (dismissedAt === undefined) return true; // 아직 아무 의사표시 없음

  const issuedAt = Date.parse(alert.issuedAt);
  // 발령 시각을 못 읽으면 억제를 존중한다. 판정 불능을 "다시 띄우기"로 해석하면
  // 파싱 버그 하나가 무한 관문이 된다 — 실패는 조용한 쪽으로 기운다.
  if (Number.isNaN(issuedAt)) return false;

  // 내가 이미 보고 끈 그 경보. 억제 시각과 동일한 순간까지 포함(<=)한다.
  if (issuedAt <= dismissedAt) return false;

  return rearmsAfterDismissal(alert.kind, level);
}

/**
 * 나에게 해당되는(= 대상 구역 안) 경보만 추린다.
 * 화면들이 "지금 나에게 유효한 경보"를 물어보는 단일 창구.
 */
export function alertsForMe(
  alerts: readonly PoliceAlert[],
  myPoint: GeoPoint | null,
  /** 시연용 지오펜스 우회(기본 false). 켜면 위치와 무관하게 전부 통과시킨다. */
  ignoreGeofence = false,
): PoliceAlert[] {
  if (ignoreGeofence) return [...alerts];
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
  level: EngagementLevel = 'normal',
  ignoreGeofence = false,
): string | null {
  const gating = alertsForMe(alerts, myPoint, ignoreGeofence).find((a) =>
    shouldGate(a, dismissedCases[a.caseId], level),
  );
  return gating?.caseId ?? null;
}

/**
 * 내 위치가 속한 POA 셀의 표시 확률 — 알림 문턱 판정의 입력.
 *
 * 반환값의 의미를 구분한다:
 *   null  판정 불가(위치 모름·예측 미도착) → 호출부에서 fail-open
 *   0     예측 셀 밖 — 판정은 됐고 확률이 최저. 어떤 문턱도 못 넘는다.
 *
 * 지오펜스 원이 육각 셀 집합보다 넓어 "대상 구역 안이지만 예측 셀 밖"이 생기는데,
 * 그 사람들이 여기서 걸러진다.
 */
export function cellProbAt(point: GeoPoint | null, grid: PoaGrid | undefined): number | null {
  if (point == null || grid == null) return null;
  const cell = grid.cells.find((c) => pointInPolygon(point, c.polygon));
  return cell ? cell.prob : 0;
}
