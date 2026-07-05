/**
 * 챗봇 입력창 (spec §2.5 — 고령 타깃 음성입력 지원).
 * TextInput + 🎤(onVoice) + 보내기(→ onSend). 큰 터치타깃(HIT), accent 강조.
 * 죽은 버튼 방지: onVoice 미제공 시 마이크 비활성, 입력 비었을 때 보내기 비활성.
 */
import React from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { color, radius, space, type, HIT } from '../theme/tokens';

export type ChatComposerProps = {
  value: string;
  onChangeText: (t: string) => void;
  onSend: () => void;
  onVoice?: () => void;
  placeholder?: string;
  accent?: string;
  dark?: boolean;
};

export function ChatComposer({
  value,
  onChangeText,
  onSend,
  onVoice,
  placeholder = '메시지를 입력하세요',
  accent = color.walk,
  dark,
}: ChatComposerProps) {
  const canSend = value.trim().length > 0;
  const canVoice = typeof onVoice === 'function';

  const barBg = dark ? color.operatorSurface : color.surface;
  const barBorder = dark ? color.operatorBorder : color.border;
  const fieldBg = dark ? color.operatorSurfaceAlt : color.surfaceAlt;
  const textColor = dark ? color.operatorText : color.text;
  const placeholderColor = dark ? color.operatorTextSec : color.textCaption;

  const handleSend = () => {
    if (canSend) onSend();
  };

  return (
    <View style={[styles.bar, { backgroundColor: barBg, borderTopColor: barBorder }]}>
      <Pressable
        onPress={() => onVoice?.()}
        disabled={!canVoice}
        accessibilityRole="button"
        accessibilityLabel="음성으로 입력"
        accessibilityState={{ disabled: !canVoice }}
        style={({ pressed }) => [
          styles.iconBtn,
          { borderColor: barBorder, backgroundColor: fieldBg },
          !canVoice && styles.disabled,
          pressed && canVoice && styles.pressed,
        ]}
      >
        <Text style={styles.icon} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          🎤
        </Text>
      </Pressable>

      <TextInput
        style={[styles.input, { backgroundColor: fieldBg, color: textColor }]}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={placeholderColor}
        multiline
        allowFontScaling
        maxFontSizeMultiplier={type.maxScale}
        accessibilityLabel="메시지 입력"
        returnKeyType="send"
        onSubmitEditing={handleSend}
      />

      <Pressable
        onPress={handleSend}
        disabled={!canSend}
        accessibilityRole="button"
        accessibilityLabel="보내기"
        accessibilityState={{ disabled: !canSend }}
        style={({ pressed }) => [
          styles.sendBtn,
          { backgroundColor: accent },
          !canSend && styles.disabled,
          pressed && canSend && styles.pressed,
        ]}
      >
        <Text style={styles.sendIcon} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          →
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderTopWidth: 1,
    gap: space.sm,
  },
  iconBtn: {
    width: HIT,
    height: HIT,
    borderRadius: radius.pill,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  icon: { fontSize: 22 },
  input: {
    flex: 1,
    minHeight: HIT,
    maxHeight: 120,
    borderRadius: radius.lg,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    fontSize: type.size.body,
    fontFamily: type.family,
  },
  sendBtn: {
    width: HIT,
    height: HIT,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendIcon: {
    fontSize: 24,
    color: '#FFFFFF',
    fontWeight: type.weight.black,
    fontFamily: type.family,
  },
  disabled: { opacity: 0.45 },
  pressed: { opacity: 0.85 },
});

export default ChatComposer;
