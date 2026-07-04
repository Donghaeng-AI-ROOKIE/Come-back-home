/**
 * 예측 반경 원 (spec §2.5, §4.1). BaseMap(MapView) 안에서만 사용.
 * 예측 반경은 '수색 진행' 요소 → 기본색은 앰버(color.search). 긴급 빨강 아님.
 * fill은 도로/지명 가림 방지를 위해 낮은 알파(§4.5)로, hexToRgba로 생성.
 */
import React from 'react';
import { Circle } from 'react-native-maps';
import { color } from '../theme/tokens';
import { hexToRgba, toLatLng } from '../utils/color';
import type { GeoPoint } from '../types/domain';

export type PredictionRadiusProps = {
  center: GeoPoint;
  radiusM: number;
  /** 반경 색 오버라이드(토큰 hex). 기본 color.search(앰버). */
  color?: string;
};

export function PredictionRadius({ center, radiusM, color: strokeColor = color.search }: PredictionRadiusProps) {
  return (
    <Circle
      center={toLatLng(center)}
      radius={radiusM}
      strokeColor={strokeColor}
      strokeWidth={2}
      fillColor={hexToRgba(strokeColor, 0.12)}
      lineDashPattern={[6, 4]}
      zIndex={1}
    />
  );
}

export default PredictionRadius;
