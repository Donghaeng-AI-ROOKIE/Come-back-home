/**
 * 거리 계산·표기 (알림 개인화 #2 "거리 명시").
 *
 * 설계 원칙: **측정 정확도보다 정밀한 숫자를 주장하지 않는다.**
 * GPS 오차가 ±80m 인데 "약 317m"라고 쓰면 앱이 거짓말을 하는 것이고, 한 번
 * 어긋난 걸 겪은 사용자는 그 다음 경보의 거리도 안 믿는다. 그래서 정확도에 맞춰
 * 표기 단위를 키우고, 너무 나쁘면 숫자 자체를 포기한다(#7 나침반 가이드를 폐기한
 * 것과 같은 판단 — 못 믿을 정밀도는 아예 노출하지 않는다).
 */
import type { GeoPoint } from '../types/domain';

const EARTH_RADIUS_M = 6_371_000;

const toRad = (deg: number) => (deg * Math.PI) / 180;

/** 두 좌표 간 대권거리(m). 하버사인 — 도심 스케일에선 오차 무시 가능. */
export function distanceM(a: GeoPoint, b: GeoPoint): number {
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

/**
 * 이 정확도에서는 숫자를 쓰지 않는다. res9 셀 지름(≈300m)의 절반 —
 * 오차가 이보다 크면 "몇 미터"가 셀 하나를 통째로 넘나들어 의미를 잃는다.
 */
export const ACCURACY_UNUSABLE_M = 150;

/** 직선거리 → 실제 보행거리 보정. 도심 가로망의 우회로 통상 1.3배. */
const DETOUR_FACTOR = 1.3;
/** 보행 속도 m/분 (≈4.5km/h). */
const WALK_M_PER_MIN = 75;

/** 정확도에 맞춘 반올림 단위(m). 오차보다 잘게 끊어 말하지 않는다. */
function stepFor(accuracyM: number | null): number {
  if (accuracyM == null) return 50;
  return Math.max(50, Math.ceil(accuracyM / 50) * 50);
}

/**
 * 거리 라벨. 정확도를 못 믿을 상황이면 null 을 돌려주고, 호출부는
 * 숫자 없는 문구("내 주변")로 물러난다.
 */
export function formatDistance(meters: number, accuracyM: number | null = null): string | null {
  if (!Number.isFinite(meters) || meters < 0) return null;
  if (accuracyM != null && accuracyM > ACCURACY_UNUSABLE_M) return null;

  if (meters >= 1000) {
    // km 대에서는 100m 단위면 충분 — 소수점 둘째 자리는 의미 없는 정밀도다.
    return `약 ${(Math.round(meters / 100) / 10).toFixed(1)}km`;
  }
  const step = stepFor(accuracyM);
  // 반올림 단위보다 가까우면 "약 50m"가 아니라 "50m 이내"다. 목격 지점에 서 있는
  // 사람에게 "약 50m"라고 말하는 건 반대 방향의 같은 거짓말 — 이 구간에서는
  // 정확한 값을 못 주므로 상한만 말한다.
  if (meters < step) return `${step}m 이내`;
  return `약 ${Math.round(meters / step) * step}m`;
}

/**
 * 도보 시간 라벨. 직선거리를 그대로 나누면 항상 실제보다 짧게 나와
 * "3분이라더니 6분 걸렸다"가 된다 — 우회 보정을 넣는다.
 */
export function formatWalkTime(meters: number, accuracyM: number | null = null): string | null {
  if (!Number.isFinite(meters) || meters < 0) return null;
  if (accuracyM != null && accuracyM > ACCURACY_UNUSABLE_M) return null;
  const minutes = Math.max(1, Math.round((meters * DETOUR_FACTOR) / WALK_M_PER_MIN));
  return `걸어서 ${minutes}분`;
}
