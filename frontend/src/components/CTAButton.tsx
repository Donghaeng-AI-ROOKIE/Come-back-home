/**
 * 주요 액션 버튼 (spec §2.5). 큰 터치타깃(고령 타깃), 실제 핸들러, 접근성 role 명시.
 * variant: primary(채움) / secondary(연한 채움) / danger(긴급 빨강) / ghost(고스트).
 * 참조 컴포넌트 — 다른 컴포넌트는 이 스타일 규칙(토큰·접근성·터치타깃)을 따른다.
 */
import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import type { StyleProp, ViewStyle } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';

export type CTAButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';

export type CTAButtonProps = {
  label: string;
  onPress: () => void;
  variant?: CTAButtonVariant;
  /** primary/secondary의 강조색 오버라이드 (예: useModeTheme().accent). 기본 walk 그린. */
  accent?: string;
  disabled?: boolean;
  loading?: boolean;
  icon?: React.ReactNode;
  fullWidth?: boolean;
  accessibilityHint?: string;
  style?: StyleProp<ViewStyle>;
};

export function CTAButton({
  label,
  onPress,
  variant = 'primary',
  accent = color.walk,
  disabled,
  loading,
  icon,
  fullWidth = true,
  accessibilityHint,
  style,
}: CTAButtonProps) {
  const bg =
    variant === 'primary' ? accent : variant === 'danger' ? color.critical : variant === 'secondary' ? color.surfaceAlt : 'transparent';
  const fg =
    variant === 'primary' || variant === 'danger' ? '#FFFFFF' : variant === 'secondary' ? accent : color.textBody;
  const isDisabled = disabled || loading;

  return (
    <Pressable
      onPress={onPress}
      disabled={isDisabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: !!isDisabled, busy: !!loading }}
      style={({ pressed }) => [
        styles.base,
        { backgroundColor: bg },
        variant === 'ghost' && styles.ghost,
        fullWidth && styles.fullWidth,
        isDisabled && styles.disabled,
        pressed && !isDisabled && styles.pressed,
        style,
      ]}
    >
      <View style={styles.row}>
        {loading ? (
          <ActivityIndicator color={fg} />
        ) : (
          <>
            {icon ? <View style={styles.icon}>{icon}</View> : null}
            <Text
              style={[styles.label, { color: fg }]}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
              numberOfLines={1}
            >
              {label}
            </Text>
          </>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 56,
    borderRadius: radius.lg,
    paddingHorizontal: space.xl,
    justifyContent: 'center',
    alignItems: 'center',
  },
  fullWidth: { alignSelf: 'stretch' },
  ghost: { minHeight: 48 },
  disabled: { opacity: 0.45 },
  pressed: { opacity: 0.85 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center' },
  icon: { marginRight: space.sm },
  label: { fontSize: type.size.body, fontFamily: type.familyExtraBold },
});

export default CTAButton;
