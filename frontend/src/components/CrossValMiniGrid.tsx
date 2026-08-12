/**
 * 교차검증(마음/몸) 미니 격자 (spec §4.2). 지도 위가 아닌 독립 컴포넌트.
 * 셀은 poaMeta[tier]로 색(fill+opacity)+명도 부호화 + SVG 패턴 오버레이(해치/도트)로
 * 색약 접근성 확보. 불일치 셀은 흰 대시 아웃라인(§4.2) + 컨테이너 라벨에 "불일치 N칸".
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Line } from 'react-native-svg';
import { color, radius, space, type } from '../theme/tokens';
import { poaMeta } from '../theme/poa';
import { hexToRgba } from '../utils/color';
import type { CrossValCell, PoaTier } from '../types/domain';

export type CrossValMiniGridProps = {
  title: string;
  cells: CrossValCell[];
  cols?: number;
  dark?: boolean;
};

const CELL = 34;
const GAP = space.xs;

/** 셀 위 패턴 오버레이 — 색만이 아닌 패턴으로 등급 재부호화(§4.2). */
function CellPattern({ tier, size }: { tier: PoaTier; size: number }) {
  const kind = poaMeta[tier].pattern;
  if (kind === 'solid' || kind === 'outline') return null;
  const stroke = poaMeta[tier].border;

  if (kind === 'hatch') {
    return (
      <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
        <Line x1={0} y1={size} x2={size} y2={0} stroke={stroke} strokeWidth={1.2} />
        <Line x1={0} y1={size * 0.5} x2={size * 0.5} y2={0} stroke={stroke} strokeWidth={1.2} />
        <Line x1={size * 0.5} y1={size} x2={size} y2={size * 0.5} stroke={stroke} strokeWidth={1.2} />
      </Svg>
    );
  }

  // dot
  const dots: Array<[number, number]> = [
    [0.3, 0.3],
    [0.7, 0.3],
    [0.5, 0.5],
    [0.3, 0.7],
    [0.7, 0.7],
  ];
  return (
    <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
      {dots.map(([fx, fy], i) => (
        <Circle key={i} cx={fx * size} cy={fy * size} r={1.6} fill={stroke} />
      ))}
    </Svg>
  );
}

export function CrossValMiniGrid({ title, cells, cols = 4, dark }: CrossValMiniGridProps) {
  const mismatchCount = cells.filter((c) => c.mismatch).length;
  const a11y = `${title} 예측 격자, 총 ${cells.length}칸 중 불일치 ${mismatchCount}칸`;
  const titleColor = dark ? color.operatorText : color.text;

  return (
    <View style={styles.wrap}>
      <Text
        style={[styles.title, { color: titleColor }]}
        allowFontScaling
        maxFontSizeMultiplier={type.maxScale}
      >
        {title}
      </Text>
      <View
        style={[styles.grid, { width: cols * (CELL + GAP) }]}
        accessible
        accessibilityRole="image"
        accessibilityLabel={a11y}
      >
        {cells.map((cell) => {
          const meta = poaMeta[cell.tier];
          return (
            <View
              key={cell.id}
              style={[
                styles.cell,
                { backgroundColor: hexToRgba(meta.fill, meta.opacity), borderColor: meta.border },
                cell.mismatch && styles.mismatch,
              ]}
            >
              <CellPattern tier={cell.tier} size={CELL} />
            </View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignSelf: 'flex-start',
  },
  title: {
    fontSize: type.size.label,
    fontFamily: type.familyBold,
    marginBottom: space.sm,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  cell: {
    width: CELL,
    height: CELL,
    borderRadius: radius.sm,
    borderWidth: 1,
    marginRight: GAP,
    marginBottom: GAP,
    overflow: 'hidden',
  },
  mismatch: {
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: color.surface,
  },
});

export default CrossValMiniGrid;
