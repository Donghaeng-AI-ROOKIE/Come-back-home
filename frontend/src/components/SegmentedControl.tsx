/**
 * 세그먼트 컨트롤 (spec §2.5, §4.4). 운영자 대시보드 예측/근거/교차검증 전환.
 * 활성 = 색 + 굵기 + 밑줄 3중 부호화 (색만으로 상태 전달 금지, spec §4.4).
 * 각 세그먼트 = Pressable role="button", 실제 onChange. dark=운영자 다크.
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { color, space, type } from '../theme/tokens';

export type Segment = { key: string; label: string };

export type SegmentedControlProps = {
  segments: Segment[];
  value: string;
  onChange: (key: string) => void;
  /** 활성 강조색. 기본 수색 앰버(운영자 세그먼트 활성, spec §4.1). */
  accent?: string;
  dark?: boolean;
};

export function SegmentedControl({
  segments,
  value,
  onChange,
  accent = color.search,
  dark,
}: SegmentedControlProps) {
  const baseLine = dark ? color.operatorBorder : color.border;
  const inactiveInk = dark ? color.operatorTextSec : color.textCaption;

  return (
    <View style={[styles.wrap, { borderBottomColor: baseLine }]}>
      {segments.map((seg) => {
        const active = seg.key === value;
        return (
          <Pressable
            key={seg.key}
            onPress={() => onChange(seg.key)}
            accessibilityRole="button"
            accessibilityLabel={seg.label}
            accessibilityState={{ selected: active }}
            style={({ pressed }) => [
              styles.seg,
              { borderBottomColor: active ? accent : 'transparent' },
              pressed && styles.pressed,
            ]}
          >
            <Text
              style={[
                styles.label,
                {
                  color: active ? accent : inactiveInk,
                  fontFamily: active ? type.familyExtraBold : type.familySemiBold,
                },
              ]}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
              numberOfLines={1}
            >
              {seg.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignSelf: 'stretch',
    borderBottomWidth: 1,
  },
  seg: {
    flex: 1,
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: space.md,
    paddingHorizontal: space.sm,
    borderBottomWidth: 3,
    marginBottom: -1,
  },
  pressed: { opacity: 0.7 },
  label: {
    fontSize: type.size.body,
  },
});

export default SegmentedControl;
