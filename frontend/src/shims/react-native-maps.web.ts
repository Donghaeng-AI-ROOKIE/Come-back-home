/**
 * `react-native-maps` 웹 스텁 (개발 확인용).
 *
 * ## 왜 필요한가
 * `react-native-maps` 는 `MapView` 에만 웹 변형(`MapView.web.ts`)이 있고
 * `Marker`·`Circle`·`Polygon`·`Polyline` 에는 없다. 이들은 `codegenNativeComponent`
 * 를 부르는데 `react-native-web` 에는 그 함수가 없어서, 웹에서 **모듈을 평가하는
 * 순간** 터진다:
 *
 *     TypeError: _reactNativeWebDistIndex.codegenNativeComponent is not a function
 *
 * 번들링은 통과한다(모듈을 실행하지 않으므로). 런타임에만 드러난다.
 *
 * ## 왜 렌더링에 영향이 없는가
 * `BaseMap` 은 `Platform.OS === 'web'` 이면 children 을 렌더하지 않고 플레이스홀더로
 * 즉시 반환한다. 즉 웹에서 이 컴포넌트들은 **import 만 되고 렌더되지 않는다.**
 * 따라서 아무것도 그리지 않는 스텁으로 충분하다.
 *
 * ## 범위
 * 웹은 지도가 필요 없는 로직(진입 관문·거리 계산·참여자 배지)을 기기 없이 확인하기
 * 위한 경로다. 지도 자체와 OS 위치마커는 웹에서 검증할 수 없고, 실기기 또는
 * development build 가 필요하다.
 *
 * 타입은 실제 패키지에서 그대로 온다 — 이 별칭은 Metro 번들링에만 적용되고
 * TypeScript 해석에는 영향을 주지 않는다.
 */

/** 아무것도 그리지 않는 컴포넌트. 웹에서는 렌더 경로에 도달하지 않는다. */
const Noop = () => null;

export default Noop;

export const MapView = Noop;
export const Marker = Noop;
export const MapMarker = Noop;
export const Circle = Noop;
export const Polygon = Noop;
export const Polyline = Noop;
export const Callout = Noop;
export const Overlay = Noop;
export const Heatmap = Noop;
export const Geojson = Noop;

// 실제 패키지에서도 PROVIDER_DEFAULT 는 undefined(플랫폼 기본 지도)다.
export const PROVIDER_DEFAULT = undefined;
export const PROVIDER_GOOGLE = 'google';
export const MAP_TYPES = {
  STANDARD: 'standard',
  SATELLITE: 'satellite',
  HYBRID: 'hybrid',
  TERRAIN: 'terrain',
  NONE: 'none',
} as const;
