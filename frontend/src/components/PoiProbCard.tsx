/**
 * 목표 지점(POI) 확률 카드 (spec §3.4, 운영자 '근거' 뷰).
 * 지명 + 확률 바 & `${Math.round(prob*100)}%` + 근거 캡션. 선택적 순위 배지.
 * 확률 바는 색+수치 이중부호화, 정보 그래픽은 요약 accessibilityLabel로 래핑.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';
import type { Poi } from '../types/domain';

export type PoiProbCardProps = {
  poi: Poi;
  rank?: number;
  dark?: boolean;
};

export function PoiProbCard({ poi, rank, dark }: PoiProbCardProps) {
  const pct = Math.round(Math.min(1, Math.max(0, poi.prob)) * 100);
  const c = dark
    ? {
        surface: color.operatorSurface,
        alt: color.operatorSurfaceAlt,
        border: color.operatorBorder,
        text: color.operatorText,
        sub: color.operatorTextSec,
      }
    : {
        surface: color.surface,
        alt: color.surfaceAlt,
        border: color.border,
        text: color.text,
        sub: color.textCaption,
      };

  return (
    <View
      style={[styles.card, { backgroundColor: c.surface, borderColor: c.border }]}
      accessible
      accessibilityRole="summary"
      accessibilityLabel={`${rank != null ? `${rank}순위 ` : ''}${poi.name}, 발견 확률 ${pct}퍼센트. ${poi.reason}`}
    >
      <View style={styles.head}>
        {rank != null ? (
          <View style={[styles.badge, { backgroundColor: color.search }]}>
            <Text
              style={styles.badgeText}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
            >
              {rank}
            </Text>
          </View>
        ) : null}
        <Text
          style={[styles.name, { color: c.text }]}
          allowFontScaling
          maxFontSizeMultiplier={type.maxScale}
          numberOfLines={1}
        >
          {poi.name}
        </Text>
        <Text
          style={[styles.pct, { color: color.searchInk }]}
          allowFontScaling
          maxFontSizeMultiplier={type.maxScale}
        >
          {pct}%
        </Text>
      </View>

      <View style={[styles.barTrack, { backgroundColor: c.alt }]}>
        <View style={[styles.barFill, { width: `${pct}%`, backgroundColor: color.search }]} />
      </View>

      <Text
        style={[styles.reason, { color: c.sub }]}
        allowFontScaling
        maxFontSizeMultiplier={type.maxScale}
      >
        {poi.reason}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  head: { flexDirection: 'row', alignItems: 'center' },
  badge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: space.md,
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: type.size.label,
    fontFamily: type.familyExtraBold,
    fontVariant: ['tabular-nums'],
  },
  name: {
    flex: 1,
    fontSize: type.size.cardTitle,
    fontFamily: type.familyExtraBold,
  },
  pct: {
    marginLeft: space.sm,
    fontSize: type.size.body,
    fontFamily: type.familyExtraBold,
    fontVariant: ['tabular-nums'],
  },
  barTrack: {
    marginTop: space.md,
    height: 12,
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  barFill: { height: '100%', borderRadius: radius.pill },
  reason: {
    marginTop: space.sm,
    fontSize: type.size.label,
    fontFamily: type.family,
    lineHeight: 22,
  },
});

export default PoiProbCard;
