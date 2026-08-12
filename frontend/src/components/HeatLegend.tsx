/**
 * POA 히트맵 범례 (spec §4.2). 색만으로 구분 금지 — 실제 셀 패턴을 SVG로 렌더한다.
 * 각 행 = [패턴 스와치(채움/45° 빗금/점/테두리)] + 등급 라벨(고·중·저·최저) + 확률 구간.
 * dark 변형은 운영자 다크 대시보드용 색을 사용.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Defs, Line, Pattern, Rect } from 'react-native-svg';
import { color, radius, space, type } from '../theme/tokens';
import { operatorTheme } from '../theme/theme';
import { poaMeta, TIER_LABEL, TIER_ORDER, TIER_RANGE } from '../theme/poa';
import type { PoaTier } from '../types/domain';

export type HeatLegendProps = {
  title?: string;
  dark?: boolean;
  compact?: boolean;
};

/** 등급별 실제 패턴을 그리는 SVG 스와치 — 색+명도+패턴 3중 부호화. */
function PoaSwatch({ tier, size, dark }: { tier: PoaTier; size: number; dark: boolean }) {
  const meta = poaMeta[tier];
  const rawId = React.useId();
  const pid = `poa-${rawId.replace(/[^a-zA-Z0-9]/g, '')}-${tier}`;
  const swatchBg = dark ? color.operatorSurfaceAlt : color.surface;
  const inset = 1;
  const s = size - inset * 2;

  const isPatterned = meta.pattern === 'hatch' || meta.pattern === 'dot';
  const fill =
    meta.pattern === 'solid' ? meta.fill : meta.pattern === 'outline' ? 'none' : `url(#${pid})`;
  const fillOpacity = meta.pattern === 'solid' ? meta.opacity : 1;

  return (
    <Svg width={size} height={size}>
      {isPatterned ? (
        <Defs>
          <Pattern id={pid} patternUnits="userSpaceOnUse" width={6} height={6}>
            <Rect x={0} y={0} width={6} height={6} fill={swatchBg} />
            {meta.pattern === 'hatch' ? (
              <>
                <Line x1={-1.5} y1={1.5} x2={1.5} y2={-1.5} stroke={meta.fill} strokeWidth={1.8} />
                <Line x1={0} y1={6} x2={6} y2={0} stroke={meta.fill} strokeWidth={1.8} />
                <Line x1={4.5} y1={7.5} x2={7.5} y2={4.5} stroke={meta.fill} strokeWidth={1.8} />
              </>
            ) : (
              <Circle cx={3} cy={3} r={1.35} fill={meta.fill} />
            )}
          </Pattern>
        </Defs>
      ) : null}
      <Rect
        x={inset}
        y={inset}
        width={s}
        height={s}
        rx={5}
        ry={5}
        fill={fill}
        fillOpacity={fillOpacity}
        stroke={meta.border}
        strokeWidth={meta.pattern === 'outline' ? 2 : 1.25}
        strokeDasharray={meta.pattern === 'outline' ? [3, 2] : undefined}
      />
    </Svg>
  );
}

export function HeatLegend({ title = '발견 확률 (POA)', dark = false, compact = false }: HeatLegendProps) {
  const swatchSize = compact ? 22 : 28;
  const cardBg = dark ? operatorTheme.surface : color.surface;
  const cardBorder = dark ? operatorTheme.border : color.border;
  const titleColor = dark ? operatorTheme.text : color.text;
  const labelColor = dark ? operatorTheme.text : color.text;
  const rangeColor = dark ? operatorTheme.textSec : color.textBody;

  const summary =
    `${title} 범례. ` +
    TIER_ORDER.map((t) => `${TIER_LABEL[t]} ${TIER_RANGE[t]}`).join(', ') +
    '. 색과 명도, 셀 패턴으로 구분됩니다.';

  return (
    <View
      style={[
        styles.card,
        { backgroundColor: cardBg, borderColor: cardBorder },
        compact && styles.cardCompact,
      ]}
      accessible
      accessibilityLabel={summary}
    >
      <Text
        style={[styles.title, { color: titleColor }, compact && styles.titleCompact]}
        allowFontScaling
        maxFontSizeMultiplier={type.maxScale}
      >
        {title}
      </Text>
      {TIER_ORDER.map((tier) => (
        <View key={tier} style={[styles.row, compact && styles.rowCompact]}>
          <PoaSwatch tier={tier} size={swatchSize} dark={dark} />
          <Text
            style={[styles.tierLabel, { color: labelColor }]}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
          >
            {TIER_LABEL[tier]}
          </Text>
          <Text
            style={[styles.tierRange, { color: rangeColor }]}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
            numberOfLines={1}
          >
            {TIER_RANGE[tier]}
          </Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    alignSelf: 'flex-start',
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  cardCompact: { padding: space.sm },
  title: {
    fontSize: type.size.cardTitle,
    fontFamily: type.familyExtraBold,
    marginBottom: space.sm,
  },
  titleCompact: { fontSize: type.size.label, marginBottom: space.xs },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.xs,
  },
  rowCompact: { paddingVertical: 2 },
  tierLabel: {
    marginLeft: space.sm,
    width: 40,
    fontSize: type.size.label,
    fontFamily: type.familyExtraBold,
  },
  tierRange: {
    flex: 1,
    marginLeft: space.sm,
    fontSize: type.size.label,
    fontFamily: type.familySemiBold,
    textAlign: 'right',
  },
});

export default HeatLegend;
