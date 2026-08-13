/**
 * 챗봇 말풍선 (spec §2.5, §3.3/§3.4). 등록·제보·알림 챗봇 공용.
 * bot 좌측(surfaceAlt) / user 우측(accent 틴트). 고령 타깃 — 큰 본문(16sp)·고대비.
 * 색만으로 화자 구분 금지: 정렬(좌/우) + 꼬리 모서리로 이중부호화.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';
import { hexToRgba } from '../utils/color';
import { gFont } from '../theme/guardianTokens';

export type ChatBubbleProps = {
  from: 'bot' | 'user';
  text: string;
  /** 표시용 시각 (예: '오후 3:12'). */
  time?: string;
  dark?: boolean;
  /** 배경 오버라이드 — 보호자 트리(피그마 그린 팔레트) 전용. 미지정 시 기존 색. */
  bg?: string;
  /** 글자색 오버라이드. */
  fg?: string;
  /** 보호자 Figma 챗 UI의 작은 13px 말풍선 규격. */
  guardian?: boolean;
};

export function ChatBubble({ from, text, time, dark, bg, fg, guardian }: ChatBubbleProps) {
  const isUser = from === 'user';

  const bubbleBg =
    bg ??
    (isUser
      ? dark
        ? hexToRgba(color.walk, 0.24)
        : color.walkWash
      : dark
        ? color.operatorSurfaceAlt
        : color.surfaceAlt);
  const textColor = fg ?? (dark ? color.operatorText : color.text);
  const timeColor = dark ? color.operatorTextSec : color.textCaption;

  const speaker = isUser ? '나' : '상담';
  const a11yLabel = time ? `${speaker}. ${text}. ${time}` : `${speaker}. ${text}`;

  return (
    <View
      style={[styles.row, isUser ? styles.rowUser : styles.rowBot]}
      accessible
      accessibilityLabel={a11yLabel}
    >
      <View
        style={[
          styles.bubble,
          guardian && styles.guardianBubble,
          { backgroundColor: bubbleBg },
          isUser ? styles.bubbleUser : styles.bubbleBot,
        ]}
      >
        <Text
          style={[styles.text, guardian && styles.guardianText, { color: textColor }]}
          allowFontScaling
          maxFontSizeMultiplier={type.maxScale}
        >
          {text}
        </Text>
        {time ? (
          <Text
            style={[styles.time, { color: timeColor }]}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
          >
            {time}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', marginVertical: space.xs },
  rowBot: { justifyContent: 'flex-start' },
  rowUser: { justifyContent: 'flex-end' },
  bubble: {
    maxWidth: '80%',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.lg,
  },
  bubbleBot: { borderTopLeftRadius: radius.sm },
  bubbleUser: { borderTopRightRadius: radius.sm },
  text: {
    fontSize: type.size.body,
    fontFamily: type.familySemiBold,
  },
  guardianBubble: { maxWidth: 280, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10 },
  guardianText: { fontSize: 13, lineHeight: 19, fontFamily: gFont.regular, fontWeight: '400' },
  time: {
    marginTop: space.xs,
    fontSize: type.size.caption,
    fontFamily: type.family,
    textAlign: 'right',
  },
});

export default ChatBubble;
