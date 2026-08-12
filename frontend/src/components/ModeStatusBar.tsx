/**
 * 모드 상태 배너 (spec §2.5). green(산책)/amber(수색 진행)/red(긴급).
 * 색만으로 상태 전달 금지 — 도트 + 텍스트 이중부호화.
 *
 * **표시 전용 컴포넌트다.** 모드·심각도를 스토어에서 직접 읽지 않고 props 로 받는다 —
 * 디자인 교체 시 상태 연결이 같이 사라지지 않게. 색 계산(`computeModeTokens`)은
 * 순수 함수라 여기서 불러도 무방하다(테마는 원래 표시 계층의 몫).
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';
import { computeModeTokens } from '../theme/theme';
import type { AppMode, Severity } from '../types/domain';

export type ModeStatusBarProps = {
  mode: AppMode;
  severity: Severity;
  /** 배너 좌측 라벨 오버라이드. 기본은 모드에 따라 자동. */
  label?: string;
  compact?: boolean;
};

export function ModeStatusBar({ mode, severity, label, compact }: ModeStatusBarProps) {
  const t = computeModeTokens(mode, severity);
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
  label: { fontSize: type.size.label, fontFamily: type.familyBold },
});

export default ModeStatusBar;
