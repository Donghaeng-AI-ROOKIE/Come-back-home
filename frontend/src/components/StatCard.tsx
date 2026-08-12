/**
 * 통계 카드 (spec §2.5). 대형 수치(type.size.bigNum, tabular-nums) + 라벨 캡션. 컴팩트 카드.
 * ReportDone/CaseFound 등에서 "함께 찾는 이웃 128명" 형태로 사용.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { TextStyle } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';

export type StatCardProps = {
  value: string | number;
  label: string;
  /** 수치 강조색 오버라이드(예: 수색 앰버 잉크). 기본 text 토큰. */
  accent?: string;
  icon?: React.ReactNode;
  dark?: boolean;
};

// 수치 자릿수 흔들림 방지를 위해 고정폭 숫자.
const TABULAR_NUMS: TextStyle = { fontVariant: ['tabular-nums'] };

export function StatCard({ value, label, accent, icon, dark = false }: StatCardProps) {
  const c = dark
    ? {
        surface: color.operatorSurface,
        border: color.operatorBorder,
        value: color.operatorText,
        label: color.operatorTextSec,
      }
    : {
        surface: color.surface,
        border: color.border,
        value: color.text,
        label: color.textCaption,
      };

  const valueColor = accent ?? c.value;
  const valueText = String(value);

  return (
    <View
      accessible
      accessibilityLabel={`${label} ${valueText}`}
      style={[styles.card, { backgroundColor: c.surface, borderColor: c.border }]}
    >
      {icon ? <View style={styles.icon}>{icon}</View> : null}
      <Text
        style={[styles.value, TABULAR_NUMS, { color: valueColor }]}
        allowFontScaling
        maxFontSizeMultiplier={type.maxScale}
        numberOfLines={1}
      >
        {valueText}
      </Text>
      <Text
        style={[styles.label, { color: c.label }]}
        allowFontScaling
        maxFontSizeMultiplier={type.maxScale}
        numberOfLines={2}
      >
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    borderWidth: 1,
    paddingVertical: space.md,
    paddingHorizontal: space.lg,
    alignItems: 'flex-start',
    minWidth: 96,
  },
  icon: { marginBottom: space.xs },
  value: { fontSize: type.size.bigNum, fontFamily: type.familyExtraBold },
  label: {
    marginTop: space.xs,
    fontSize: type.size.label,
    fontFamily: type.familyBold,
  },
});

export default StatCard;
