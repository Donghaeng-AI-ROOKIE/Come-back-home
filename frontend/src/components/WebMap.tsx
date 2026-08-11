/**
 * 웹 전용 지도 — 실제 OSM 타일 + 실제 POA 폴리곤.
 *
 * ## 왜 따로 만드나
 * `react-native-maps` 는 웹을 지원하지 않아 `BaseMap` 이 웹에서 플레이스홀더로
 * 떨어지고, `PoaHeatmap` 의 `<Polygon>` 도 웹에선 렌더되지 않는다. 그 자리를
 * **디자인 시안의 지도 그림**으로 메우면 예측 지도로 오인된다 — 심사·시연에서
 * "이게 AI 예측 결과"로 읽히는 그림이 실제로는 고정 이미지인 상태가 된다.
 *
 * 그래서 웹에서도 진짜를 그린다: 배경은 OSM 래스터 타일(`<img>` 격자, 별도 라이브러리
 * 불필요), 그 위에 서버가 준 셀 폴리곤을 SVG 로 얹는다. 색·등급은 네이티브
 * 히트맵과 같은 `poaMeta` 를 쓴다 — 플랫폼마다 다른 색을 보여주면 안 된다.
 *
 * ## 좌표 변환
 * 표준 Web Mercator(EPSG:3857). 타일 좌표 = 픽셀좌표 / 256.
 */
import React, { useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Svg, { Polygon as SvgPolygon, Circle, Polyline as SvgPolyline } from 'react-native-svg';
import type { GeoPoint, PoaCell, PoaGrid } from '../types/domain';
import { poaMeta } from '../theme/poa';
import { API_BASE } from '../api/config';
import { hexToRgba } from '../utils/color';
import { color, type as typo } from '../theme/tokens';
import { Text } from 'react-native';

const TILE = 256;
/** OSM 타일 서버 — 이용약관상 대량 트래픽 금지. 시연·검증 용도로만 쓴다. */
/**
 * 타일은 **우리 서버가 중계**한다.
 *
 * tile.openstreetmap.org 를 앱이 직접 부르면 폰에서 안 열리는 사례가 나왔다
 * (학교 WiFi·이동통신 양쪽에서 지도가 회색으로만 떴다 — 실측 08-11).
 * 앱은 이미 우리 서버에 붙어 있으므로 그 경로로 받으면 확실하다. 서버가 캐시도 한다.
 */
const TILE_URL = (z: number, x: number, y: number) => `${API_BASE}/geo/tiles/${z}/${x}/${y}.png`;

function lngToX(lng: number, z: number) {
  return ((lng + 180) / 360) * Math.pow(2, z) * TILE;
}
function latToY(lat: number, z: number) {
  const rad = (lat * Math.PI) / 180;
  return ((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * Math.pow(2, z) * TILE;
}

export type WebMapProps = {
  /** 지도 중심 — 보통 최종 목격 위치. 없으면 아무것도 그릴 수 없다. */
  center?: GeoPoint;
  grid?: PoaGrid;
  /** 최종 목격 위치 마커. */
  marker?: GeoPoint;
  /** 실제로 걸은 경로(산책 화면). */
  path?: GeoPoint[];
  zoom?: number;
  style?: any;
  accessibilityLabel?: string;
  /**
   * 셀을 눌렀을 때. 폰에는 마우스 오버가 없어서, 확률을 보려면 누르는 수밖에 없다
   * (현장 요청 08-11 — "지도에서 아무 인터랙션도 못 한다").
   */
  onCellPress?: (cell: PoaCell) => void;
  /** 손가락으로 지도를 밀어 볼 수 있게 한다. */
  pannable?: boolean;
};

export default function WebMap({
  center,
  grid,
  marker,
  path,
  zoom = 15,
  style,
  accessibilityLabel = '발견확률 지도',
  onCellPress,
  pannable,
}: WebMapProps) {
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  return (
    <View
      style={[styles.root, style]}
      onLayout={(e) => {
        const { width, height } = e.nativeEvent.layout;
        setSize({ w: width, h: height });
      }}
      accessible
      accessibilityRole="image"
      accessibilityLabel={grid ? `${accessibilityLabel}. ${grid.topLabel}` : accessibilityLabel}
    >
      {center && size ? (
        <Inner
          center={center}
          grid={grid}
          marker={marker}
          path={path}
          zoom={zoom}
          w={size.w}
          h={size.h}
          onCellPress={onCellPress}
          pannable={pannable}
        />
      ) : null}
      <Text style={styles.attribution}>© OpenStreetMap</Text>
    </View>
  );
}

function Inner({
  center, grid, marker, path, zoom, w, h, onCellPress, pannable,
}: {
  center: GeoPoint; grid?: PoaGrid; marker?: GeoPoint; path?: GeoPoint[];
  zoom: number; w: number; h: number;
  onCellPress?: (cell: PoaCell) => void; pannable?: boolean;
}) {
  /**
   * 손가락으로 민 만큼의 픽셀 이동량. 중심 좌표를 바꾸지 않고 원점만 옮긴다 —
   * 부모가 주는 center 는 그대로 두어야 다시 그릴 때 화면이 튀지 않는다.
   */
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  // 화면 중앙이 center 가 되도록 하는 픽셀 원점.
  const cx = lngToX(center.lng, zoom);
  const cy = latToY(center.lat, zoom);
  const originX = cx - w / 2 - pan.x;
  const originY = cy - h / 2 - pan.y;

  const toPx = (p: GeoPoint) => ({
    x: lngToX(p.lng, zoom) - originX,
    y: latToY(p.lat, zoom) - originY,
  });

  const x0 = Math.floor(originX / TILE);
  const y0 = Math.floor(originY / TILE);
  const x1 = Math.floor((originX + w) / TILE);
  const y1 = Math.floor((originY + h) / TILE);
  const max = Math.pow(2, zoom);

  const tiles: { key: string; url: string; left: number; top: number }[] = [];
  for (let tx = x0; tx <= x1; tx++) {
    for (let ty = y0; ty <= y1; ty++) {
      if (ty < 0 || ty >= max) continue;
      const wrapped = ((tx % max) + max) % max;
      tiles.push({
        key: `${tx}/${ty}`,
        url: TILE_URL(zoom, wrapped, ty),
        left: tx * TILE - originX,
        top: ty * TILE - originY,
      });
    }
  }

  const markerPx = marker ? toPx(marker) : null;

  /** 화면 좌표 → 그 자리의 셀. 폴리곤 내부 판정(레이 캐스팅). */
  const cellAt = (px: number, py: number): PoaCell | null => {
    if (!grid) return null;
    for (const cell of grid.cells) {
      const pts = cell.polygon.map(toPx);
      let inside = false;
      for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
        const a = pts[i]; const b = pts[j];
        if ((a.y > py) !== (b.y > py) && px < ((b.x - a.x) * (py - a.y)) / (b.y - a.y) + a.x) inside = !inside;
      }
      if (inside) return cell;
    }
    return null;
  };

  const handlers = (pannable || onCellPress) ? {
    onPointerDown: (e: any) => {
      drag.current = { x: e.clientX, y: e.clientY, moved: false };
      e.currentTarget.setPointerCapture?.(e.pointerId);
    },
    onPointerMove: (e: any) => {
      const d = drag.current;
      if (!d || !pannable) return;
      const dx = e.clientX - d.x; const dy = e.clientY - d.y;
      // 5px 넘게 움직이면 '탭'이 아니라 '밀기'로 본다.
      if (!d.moved && Math.hypot(dx, dy) < 5) return;
      d.moved = true;
      d.x = e.clientX; d.y = e.clientY;
      setPan((prev) => ({ x: prev.x + dx, y: prev.y + dy }));
    },
    onPointerUp: (e: any) => {
      const d = drag.current;
      drag.current = null;
      if (!d || d.moved || !onCellPress) return;
      const box = e.currentTarget.getBoundingClientRect();
      const hit = cellAt(e.clientX - box.left, e.clientY - box.top);
      if (hit) onCellPress(hit);
    },
  } : {};

  return (
    <View
      style={StyleSheet.absoluteFill as any}
      // 웹 전용 포인터 이벤트 — react-native-web 이 DOM 으로 그대로 넘긴다.
      {...(handlers as object)}
    >
      {tiles.map((t) => (
        // react-native-web 에서 <Image> 는 추가 래핑이 붙어 픽셀 정렬이 어긋난다.
        // 타일은 정확한 격자 정렬이 생명이라 순수 img 를 쓴다.
        React.createElement('img', {
          key: t.key,
          src: t.url,
          width: TILE,
          height: TILE,
          style: { position: 'absolute', left: t.left, top: t.top, width: TILE, height: TILE },
          alt: '',
        })
      ))}

      <Svg style={StyleSheet.absoluteFill} width={w} height={h}>
        {grid?.cells.map((cell) => {
          const meta = poaMeta[cell.tier];
          const pts = cell.polygon.map((p) => {
            const q = toPx(p);
            return `${q.x},${q.y}`;
          }).join(' ');
          return (
            <SvgPolygon
              key={cell.id}
              points={pts}
              fill={hexToRgba(meta.fill, meta.opacity)}
              stroke={meta.border}
              strokeWidth={cell.mismatch ? 3 : 1}
              strokeDasharray={cell.mismatch ? '4,4' : undefined}
            />
          );
        })}
        {path && path.length > 1 ? (
          <SvgPolyline
            points={path.map((p) => { const q = toPx(p); return `${q.x},${q.y}`; }).join(' ')}
            fill="none"
            stroke={color.brand}
            strokeWidth={5}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ) : null}
        {markerPx ? (
          <Circle cx={markerPx.x} cy={markerPx.y} r={9} fill={color.critical} stroke="#FFFFFF" strokeWidth={3} />
        ) : null}
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { overflow: 'hidden', backgroundColor: '#E8E8E8' },
  attribution: {
    position: 'absolute',
    right: 4,
    bottom: 2,
    fontSize: 9,
    color: '#555555',
    fontFamily: typo.family,
    backgroundColor: 'rgba(255,255,255,0.7)',
    paddingHorizontal: 4,
  },
});
