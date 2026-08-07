/**
 * 보호자 알림 탭 — 피그마 주석 "제보 받는 알림창 추가" (내용 시안 미확정).
 *
 * 시안이 나올 때까지 빈 상태만 둔다. 백엔드에도 보호자용 제보 통지 경로가
 * 아직 없다(제보는 POA 갱신·시민 3차 알림·대시보드로만 흐른다) — 고신뢰
 * 제보만 보호자에게 알리는 층위가 설계되면 여기서 소비한다.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { SvgXml } from 'react-native-svg';
import { color, space, type } from '../theme/tokens';
import { gColor } from '../theme/guardianTokens';
import { tabAlertXml, tintXml } from '../assets/guardianSvg';

export default function GuardianAlertsScreen() {
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        알림
      </Text>
      <View style={styles.empty}>
        <SvgXml xml={tintXml(tabAlertXml, gColor.chip)} width={40} height={48} />
        <Text style={styles.emptyText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          아직 도착한 알림이 없습니다.
        </Text>
        <Text style={styles.emptyCaption} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          수색 진행 상황과 확인된 제보 소식을 이곳에서 알려드립니다.
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: gColor.surface },
  title: {
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    padding: space.xl,
  },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.md, padding: space.xl },
  emptyText: { fontSize: type.size.body, fontWeight: type.weight.bold, color: gColor.textMuted, fontFamily: type.family },
  emptyCaption: { fontSize: type.size.caption, color: gColor.gray, fontFamily: type.family, textAlign: 'center', lineHeight: 20 },
});
