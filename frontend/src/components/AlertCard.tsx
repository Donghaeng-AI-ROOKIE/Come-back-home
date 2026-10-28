import React from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import type { StyleProp, TextStyle, ViewStyle } from 'react-native';
import { color, type } from '../theme/tokens';

/**
 * 시안의 알림 카드. tone 이 색과 배지를 가른다(빨강=수색 중, 초록=상황 종료).
 *
 * 긴급 알림 목록(CitizenAlertsScreen)에만 있던 카드를 꺼냈다 — 홈 화면의 "수색 중"
 * 카드도 같은 모양이어야 같은 사건을 같은 카드로 알아본다. `style` 은 바깥 여백만
 * 바꾸는 데 쓴다(목록은 카드 사이 28, 홈은 화면 가장자리 여백).
 *
 * `onPress` 가 없으면 **꺾쇠(›)도 그리지 않는다.** 눌러도 아무 일이 없는 꺾쇠는
 * "눌리지 않는다"는 제보로 돌아온다.
 */
export default function AlertCard({ tone, badge, title, body, onPress, style, accessibilityLabel }: {
  tone: 'red' | 'green';
  badge: string;
  title: string;
  body: string;
  onPress?: () => void;
  style?: StyleProp<ViewStyle>;
  accessibilityLabel?: string;
}) {
  const red = tone === 'red';
  const inner = (
    <>
      <View style={[styles.badge, red ? styles.redBadge : styles.greenBadge]}><Text style={[styles.badgeText, red ? styles.redBadgeText : styles.greenBadgeText]}>{badge}</Text></View>
      <Text style={[styles.cardTitle, keepWords]} lineBreakStrategyIOS="hangul-word">{title}</Text>
      <Text style={[styles.cardBody, keepWords]} lineBreakStrategyIOS="hangul-word">{body}</Text>
      {onPress ? <Text style={[styles.chevron, { color: red ? color.figmaRed : '#286C45' }]}>›</Text> : null}
    </>
  );
  if (!onPress) {
    return <View style={[styles.card, red ? styles.redCard : styles.greenCard, style]}>{inner}</View>;
  }
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      style={({ pressed }) => [styles.card, red ? styles.redCard : styles.greenCard, style, pressed && styles.pressed]}
    >
      {inner}
    </Pressable>
  );
}

// 지역명이 들어간 제목("[고양시 일산서구 한류월드로] 81세 실종 어르신")은 폭 끝에 걸려
// "어르 / 신"으로 음절 중간에서 꺾였다(10/28 12회차 C2) — 어절 단위로 줄을 바꾼다.
// 웹은 CSS word-break(RN 타입에는 없어 캐스팅), iOS 는 lineBreakStrategyIOS 로 맞춘다.
const keepWords = (Platform.OS === 'web' ? { wordBreak: 'keep-all' } : null) as TextStyle | null;

const styles = StyleSheet.create({
  // 높이는 시안 값(139)을 최소로만 둔다. 제목이 두 줄이고 인상착의가 길면 글이 카드
  // 밖으로 넘치므로 그때는 카드가 늘어나고, 아래 여백(12)이 마지막 줄을 테두리에서 띄운다.
  card: { minHeight: 139, borderRadius: 10, paddingHorizontal: 16, paddingTop: 20, paddingBottom: 12, marginBottom: 28, position: 'relative', shadowColor: '#000000', shadowOpacity: 0.1, shadowRadius: 7, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  redCard: { backgroundColor: '#FFF0F1' },
  greenCard: { backgroundColor: '#ECFAE5' },
  badge: { alignSelf: 'flex-start', height: 16, borderRadius: 8, paddingHorizontal: 11, alignItems: 'center', justifyContent: 'center' },
  redBadge: { backgroundColor: '#FFC9CB' },
  greenBadge: { backgroundColor: '#BDE6A9' },
  badgeText: { fontFamily: type.familyCssBold, fontSize: 10, lineHeight: 13, letterSpacing: 0.07 },
  redBadgeText: { color: color.figmaRed },
  greenBadgeText: { color: '#286C45' },
  cardTitle: { marginTop: 15, fontFamily: type.familyCssBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#525253' },
  cardBody: { marginTop: 7, fontFamily: type.familyCss, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253' },
  chevron: { position: 'absolute', right: 17, top: 17, fontFamily: type.familyCss, fontSize: 28, lineHeight: 30 },
  pressed: { opacity: 0.82 },
});
