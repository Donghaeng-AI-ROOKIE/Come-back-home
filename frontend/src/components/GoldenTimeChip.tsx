/**
 * 골든타임 칩 (spec §2.5, §4.1).
 * critical=빨강 필(긴급 실종경보), searching=앰버 필(수색 진행). mm:ss는 tabular-nums 고정폭.
 * goldenTime 이 null(수색 모드 아님)이면 "골든타임 —".
 *
 * **표시 전용 컴포넌트다.** 카운트다운은 화면이 `useGoldenTime()` 으로 가져와
 * 넘긴다 — 디자인 교체 시 이 파일이 바뀌어도 시간 계산이 같이 사라지지 않게.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { TextStyle } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';
import type { GoldenTime } from '../hooks/queries';

export type GoldenTimeChipProps = {
  /** `useGoldenTime()` 결과. null 이면 수색 모드가 아니다. */
  goldenTime: GoldenTime | null;
  label?: string;
  emphasis?: 'critical' | 'searching';
  dark?: boolean;
};

// 시간 표기는 자릿수 흔들림 방지를 위해 고정폭 숫자.
const TABULAR_NUMS: TextStyle = { fontVariant: ['tabular-nums'] };
// 채움 필 위 온-컬러 텍스트(빨강/앰버 필 대비). 심각도 hex는 토큰 고정.
const ON_FILL = '#FFFFFF';

export function GoldenTimeChip({
  goldenTime: gt,
  label = '골든타임',
  emphasis = 'critical',
  dark = false,
}: GoldenTimeChipProps) {
  const filled = gt != null;
  const fill = emphasis === 'critical' ? color.critical : color.search;

  const neutralBg = dark ? color.operatorSurfaceAlt : color.surfaceAlt;
  const neutralInk = dark ? color.operatorTextSec : color.textCaption;

  const ink = filled ? ON_FILL : neutralInk;
  const timeText = gt ? gt.label : '—';
  const remainMin = gt ? Math.ceil(gt.remainingSec / 60) : 0;
  const a11yLabel = gt ? `${label} 남은 시간 ${remainMin}분` : `${label} 정보 없음`;

  return (
    <View
      accessible
      accessibilityRole="text"
      accessibilityLabel={a11yLabel}
      style={[styles.chip, { backgroundColor: filled ? fill : neutralBg }]}
    >
      <Text
        style={[styles.label, { color: ink }]}
        allowFontScaling
        maxFontSizeMultiplier={type.maxScale}
        numberOfLines={1}
      >
        {label}
      </Text>
      <Text
        style={[styles.time, TABULAR_NUMS, { color: ink }]}
        allowFontScaling
        maxFontSizeMultiplier={type.maxScale}
        numberOfLines={1}
      >
        {timeText}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
  },
  label: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
    marginRight: space.sm,
  },
  time: {
    fontSize: type.size.body,
    fontWeight: type.weight.black,
    fontFamily: type.family,
  },
});

export default GoldenTimeChip;
