/**
 * 지오메트리 계산 — 거리와 폴리곤 포함 판정.
 *
 * 화면에 거리(m·분)를 쓰던 표기 함수들은 제거했다. 시민 화면은 거리 대신
 * "예측 구역 안/밖 + 확률 등급"으로 간다(2026-08-05 확정, 근거는 utils/areaStatus.ts).
 * 여기 남은 것은 지오펜스 판정과 셀 판정이 쓰는 순수 계산뿐이다.
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
 * 점이 폴리곤 안에 있는가 (ray casting).
 *
 * POA 셀 폴리곤에 내 위치를 대조해 "내가 예측 구역 안인가"를 판정하는 데 쓴다.
 * 위경도를 평면으로 취급하는데, 도심 한 구역(수 km) 스케일에서는 곡률 오차가
 * 셀 경계 판정에 영향을 줄 수준이 아니다.
 *
 * 경계선 위의 점은 구현상 어느 쪽으로 갈지 보장하지 않는다 — 인접 셀 중
 * 하나로만 잡히면 되는 용도라 문제되지 않는다.
 */
export function pointInPolygon(p: GeoPoint, polygon: readonly GeoPoint[]): boolean {
  if (polygon.length < 3) return false;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const a = polygon[i];
    const b = polygon[j];
    // a.lat 와 b.lat 가 p.lat 를 사이에 두는 변만 교차 후보
    const straddles = a.lat > p.lat !== b.lat > p.lat;
    if (!straddles) continue;
    const lngAtLat = ((b.lng - a.lng) * (p.lat - a.lat)) / (b.lat - a.lat) + a.lng;
    if (p.lng < lngAtLat) inside = !inside;
  }
  return inside;
}

