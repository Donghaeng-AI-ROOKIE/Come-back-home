/**
 * 산책 요약 (와이어프레임 A-3).
 *
 * 산책 직후에 "얼마나 걸었는지"와 "그게 무슨 의미인지"를 한 번 보여주는 화면.
 * 서버가 방금 저장한 값을 그대로 받아 쓴다 — 앱이 다시 계산하면 저장된 값과
 * 화면 값이 어긋날 수 있다(종료 시점 반올림 차이).
 */
import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import CTAButton from '../components/CTAButton';
import { useWalkStats } from '../hooks/queries';

export default function WalkSummaryScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { distanceKm, durationMin } = useRoute<RouteProp<RootStackParamList, 'WalkSummary'>>().params;
  const { data: stats } = useWalkStats();

  const goHome = () => navigation.navigate('CitizenTabs', { screen: 'Home' });
  const goRecords = () => navigation.navigate('CitizenTabs', { screen: 'Records' });

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          오늘의 산책 기록
        </Text>

        <View style={styles.row}>
          <View style={styles.statCard} accessible accessibilityLabel={`보행 거리 ${distanceKm.toFixed(1)}킬로미터`}>
            <Text style={styles.statLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              보행 거리
            </Text>
            <Text style={styles.statValue} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {distanceKm.toFixed(1)} <Text style={styles.statUnit}>km</Text>
            </Text>
          </View>
          <View style={styles.statCard} accessible accessibilityLabel={`시간 ${Math.round(durationMin)}분`}>
            <Text style={styles.statLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              시간
            </Text>
            <Text style={styles.statValue} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {Math.round(durationMin)} <Text style={styles.statUnit}>분</Text>
            </Text>
          </View>
        </View>

        {stats && (
          <View style={styles.progressCard}>
            <Text style={styles.progressTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              누적 {stats.total_km.toFixed(1)}km · {stats.level_label}
            </Text>
            <Text style={styles.progressBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {stats.next_level_km > 0
                ? `다음 단계까지 ${stats.next_level_km.toFixed(1)}km 남았어요.`
                : '최고 단계에 도달했어요.'}
            </Text>
          </View>
        )}

        <View style={styles.meaning}>
          <Text style={styles.meaningText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            산책을 이어 가면 실종 알림이 필요한 순간에 이 동네에 더 많은 이웃이 남아 있게 됩니다.
          </Text>
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <CTAButton label="내 기록 보기" onPress={goRecords} accent={color.walk} />
        <View style={styles.gap} />
        <CTAButton label="홈으로 돌아가기" onPress={goHome} variant="ghost" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  scroll: { padding: space.xl, gap: space.lg },
  title: { fontSize: type.size.title, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },

  row: { flexDirection: 'row', gap: space.md },
  statCard: {
    flex: 1,
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    gap: space.xs,
    alignItems: 'center',
  },
  statLabel: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family, fontWeight: type.weight.bold },
  statValue: {
    fontSize: type.size.bigNum,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
  },
  statUnit: { fontSize: type.size.label, fontWeight: type.weight.bold, color: color.textBody },

  progressCard: {
    backgroundColor: color.walkWash,
    borderRadius: radius.lg,
    padding: space.lg,
    gap: space.xs,
  },
  progressTitle: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: color.walkInk, fontFamily: type.family },
  progressBody: { fontSize: type.size.label, color: color.walkInk, fontFamily: type.family, fontWeight: type.weight.medium },

  meaning: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
  },
  meaningText: { fontSize: type.size.label, color: color.textBody, fontFamily: type.family, lineHeight: 23 },

  footer: {
    padding: space.xl,
    borderTopWidth: 1,
    borderTopColor: color.border,
    backgroundColor: color.surface,
  },
  gap: { height: space.sm },
});
