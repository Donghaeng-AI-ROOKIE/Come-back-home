/**
 * POA(발견확률) 히트맵 오버레이 (spec §4.2 / §4.5).
 * grid.cells 하나당 <Polygon> 하나 — 색상+명도 이중부호화(poaMeta), 테두리는 등급 border.
 * 교차검증 불일치 셀은 파선(lineDashPattern) + 굵은 테두리로 시각 강조.
 *
 * <Polygon> 프래그먼트만 렌더한다 → 반드시 <BaseMap>(=<MapView>) 자식으로 사용.
 */
import React from 'react';
import { Polygon } from 'react-native-maps';
import type { PoaGrid } from '../types/domain';
import { poaMeta } from '../theme/poa';
import { hexToRgba, toLatLng } from '../utils/color';

export type PoaHeatmapProps = {
  grid: PoaGrid;
  /** 불일치 셀 강조(파선) 표시 여부. 기본 true. */
  showMismatch?: boolean;
};

export function PoaHeatmap({ grid, showMismatch = true }: PoaHeatmapProps) {
  return (
    <>
      {grid.cells.map((cell) => {
        const meta = poaMeta[cell.tier];
        const isMismatch = showMismatch && cell.mismatch === true;
        return (
          <Polygon
            key={cell.id}
            coordinates={cell.polygon.map(toLatLng)}
            fillColor={hexToRgba(meta.fill, meta.opacity)}
            strokeColor={meta.border}
            strokeWidth={isMismatch ? 3 : 1}
            lineDashPattern={isMismatch ? [4, 4] : undefined}
          />
        );
      })}
    </>
  );
}

export default PoaHeatmap;
