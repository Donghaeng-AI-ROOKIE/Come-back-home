/**
 * 챗봇 입력창 (spec §2.5 — 고령 타깃 음성입력 지원).
 * 기본 화면은 TextInput + 음성입력 + 보내기. 보호자 variant는 Figma의 원형
 * 위쪽 화살표만 렌더한다.
 * 죽은 버튼 방지: onVoice 미제공 시 마이크 비활성, 입력 비었을 때 보내기 비활성.
 */
import React from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { color, radius, space, type, HIT } from '../theme/tokens';
import { gFont } from '../theme/guardianTokens';
import { icSendUpXml } from '../assets/guardianSvg';
import { SvgXml } from 'react-native-svg';

export type ChatComposerProps = {
  value: string;
  onChangeText: (t: string) => void;
  onSend: () => void;
  onVoice?: () => void;
  placeholder?: string;
  accent?: string;
  dark?: boolean;
  /** 보호자 Figma 입력창: 마이크 없이 36px 필드 + 26px 원형 위쪽 화살표. */
  guardian?: boolean;
};

export function ChatComposer({
  value,
  onChangeText,
  onSend,
  onVoice,
  placeholder = '메시지를 입력하세요',
  accent = color.walk,
  dark,
  guardian,
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
    <View style={[styles.bar, guardian && styles.guardianBar, { backgroundColor: barBg, borderTopColor: barBorder }]}>
      {!guardian ? <Pressable
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
      </Pressable> : null}

      <TextInput
        style={[styles.input, guardian && styles.guardianInput, { backgroundColor: guardian ? '#FAFAFA' : fieldBg, color: textColor }]}
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
          guardian && styles.guardianSend,
          { backgroundColor: guardian ? 'transparent' : accent },
          !canSend && !guardian && styles.disabled,
          pressed && canSend && styles.pressed,
        ]}
      >
        {guardian ? (
          <SvgXml xml={icSendUpXml.replace('#328E6E', accent)} width={26} height={26} />
        ) : (
          <Text style={styles.sendIcon} allowFontScaling maxFontSizeMultiplier={type.maxScale}>→</Text>
        )}
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
  guardianBar: { height: 52, paddingHorizontal: 16, paddingVertical: 8, alignItems: 'center', borderTopWidth: 0, gap: 8 },
  guardianInput: { minHeight: 36, maxHeight: 36, borderRadius: 17, paddingHorizontal: 14, paddingVertical: 8, fontSize: 13, fontFamily: gFont.regular, borderWidth: 1, borderColor: 'rgba(0,0,0,0.06)' },
  guardianSend: { width: 32, height: 32 },
  disabled: { opacity: 0.45 },
  pressed: { opacity: 0.85 },
});

export default ChatComposer;
