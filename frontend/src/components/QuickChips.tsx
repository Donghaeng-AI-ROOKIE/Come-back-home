/**
 * 빠른 응답 칩 (spec §2.5). 감싸는 Pressable pill 행 — 실제 onSelect 발화.
 * accent 보더·틴트. 고령 타깃 — 넉넉한 터치타깃(minHeight + hitSlop).
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';
import { hexToRgba } from '../utils/color';

export type QuickChipsProps = {
  chips: string[];
  onSelect: (chip: string) => void;
  /** 강조색. 기본 walk 그린. */
  accent?: string;
  dark?: boolean;
  disabled?: boolean;
};

export function QuickChips({
  chips,
  onSelect,
  accent = color.walk,
  dark,
  disabled,
}: QuickChipsProps) {
  return (
    <View style={styles.wrap}>
      {chips.map((chip) => (
        <Pressable
          key={chip}
          onPress={() => onSelect(chip)}
          disabled={disabled}
          hitSlop={8}
          accessibilityRole="button"
          accessibilityLabel={chip}
          accessibilityState={{ disabled: !!disabled }}
          style={({ pressed }) => [
            styles.chip,
            {
              backgroundColor: hexToRgba(accent, pressed ? 0.24 : dark ? 0.18 : 0.12),
              borderColor: accent,
            },
            disabled && styles.disabled,
          ]}
        >
          <Text
            style={[styles.label, { color: dark ? color.operatorText : accent }]}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
            numberOfLines={1}
          >
            {chip}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    minHeight: 44,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    justifyContent: 'center',
    alignItems: 'center',
  },
  disabled: { opacity: 0.45 },
  label: {
    fontSize: type.size.label,
    fontFamily: type.familyBold,
  },
});

export default QuickChips;
