/**
 * 지오메트리 계산 — 폴리곤 포함 판정.
 *
 * 거리 계산(하버사인)까지 여기 있었는데 전부 없앴다. 화면 표기는 "예측 구역
 * 안/밖 + 확률 등급"으로 갔고(utils/areaStatus.ts), 남아 있던 마지막 사용처인
 * 지오펜스도 중심+반경 근사에서 **H3 셀 대조**로 바뀌었다(utils/h3cell.ts).
 * 거리를 다시 쓰고 싶어지면, 확률분포에는 잴 점이 없다는 areaStatus.ts 의
 * 논의를 먼저 읽을 것.
 */
import type { GeoPoint } from '../types/domain';

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

