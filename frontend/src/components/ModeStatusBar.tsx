/**
 * 모드 상태 배너 (spec §2.5). green(산책)/amber(수색 진행)/red(긴급).
 * useModeTheme 소비. 색만으로 상태 전달 금지 — 도트 + 텍스트 이중부호화.
 * 참조 컴포넌트.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';
import { useModeTheme } from '../theme/theme';

export type ModeStatusBarProps = {
  /** 배너 좌측 라벨 오버라이드. 기본은 모드에 따라 자동. */
  label?: string;
  compact?: boolean;
};

export function ModeStatusBar({ label, compact }: ModeStatusBarProps) {
  const t = useModeTheme();
  const isSearch = t.mode === 'search';
  const bg = isSearch ? t.severityWash : color.walkWash;
  const ink = isSearch ? t.severityInk : color.walkInk;
  const dot = isSearch ? t.severityColor : color.walk;

  const text =
    label ??
    (t.mode === 'walk'
      ? '산책 모드 · 우리 동네는 지금 평온해요'
      : t.severity === 'critical'
        ? '수색 모드 · 긴급 실종경보 진행 중'
        : '수색 모드 · 수색 진행 중');

  return (
    <View
      style={[styles.wrap, { backgroundColor: bg }, compact && styles.compact]}
      accessibilityRole="text"
      accessibilityLabel={text}
    >
      <View style={[styles.dot, { backgroundColor: dot }]} />
      <Text
        style={[styles.label, { color: ink }]}
        allowFontScaling
        maxFontSizeMultiplier={type.maxScale}
        numberOfLines={1}
      >
        {text}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.pill,
    alignSelf: 'flex-start',
  },
  compact: { paddingVertical: space.sm },
  dot: { width: 10, height: 10, borderRadius: 5, marginRight: space.sm },
  label: { fontSize: type.size.label, fontWeight: type.weight.bold, fontFamily: type.family },
});

export default ModeStatusBar;
