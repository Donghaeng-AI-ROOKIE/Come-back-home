import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { StyleProp, ViewStyle } from 'react-native';
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
      <Text style={styles.cardTitle}>{title}</Text>
      <Text style={styles.cardBody}>{body}</Text>
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

const styles = StyleSheet.create({
  card: { height: 139, borderRadius: 10, paddingHorizontal: 16, paddingTop: 20, marginBottom: 28, position: 'relative', shadowColor: '#000000', shadowOpacity: 0.1, shadowRadius: 7, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
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
