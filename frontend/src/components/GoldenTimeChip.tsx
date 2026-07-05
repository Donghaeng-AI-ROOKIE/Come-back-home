/**
 * 골든타임 칩 (spec §2.5, §4.1). 파생 카운트다운 useGoldenTime() 소비(초는 스토어 미저장).
 * critical=빨강 필(긴급 실종경보), searching=앰버 필(수색 진행). mm:ss는 tabular-nums 고정폭.
 * useGoldenTime()가 null(수색 모드 아님)이면 "골든타임 —".
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { TextStyle } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';
import { useGoldenTime } from '../hooks/queries';

export type GoldenTimeChipProps = {
  label?: string;
  emphasis?: 'critical' | 'searching';
  dark?: boolean;
};

// 시간 표기는 자릿수 흔들림 방지를 위해 고정폭 숫자.
const TABULAR_NUMS: TextStyle = { fontVariant: ['tabular-nums'] };
// 채움 필 위 온-컬러 텍스트(빨강/앰버 필 대비). 심각도 hex는 토큰 고정.
const ON_FILL = '#FFFFFF';

export function GoldenTimeChip({
  label = '골든타임',
  emphasis = 'critical',
  dark = false,
}: GoldenTimeChipProps) {
  const gt = useGoldenTime();
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
