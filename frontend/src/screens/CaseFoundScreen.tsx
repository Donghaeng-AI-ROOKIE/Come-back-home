/**
 * 발견·종료 (spec §3.4, CONTRACT #10). 운영자 다크 fullScreenModal.
 * 무사 발견 성공 히어로 + 요약 통계(useFoundSummary) + 감사 카피.
 * 액션: [검증 수치 리포트]→ValidationReport / [닫기]→closeCase()+popToTop().
 * 성공=산책 그린(무사/평온 의미). 심각도 색(빨강/앰버)은 여기 미사용.
 */
import React from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { color, radius, space, type } from '../theme/tokens';
import { operatorTheme } from '../theme/theme';
import { hexToRgba } from '../utils/color';
import { useFoundSummary } from '../hooks/queries';
import { useAppModeStore } from '../store/appModeStore';
import { DEMO_CASE_ID } from '../data/missing';
import type { OperatorStackParamList } from '../navigation/types';
import StatCard from '../components/StatCard';

type Nav = NativeStackNavigationProp<OperatorStackParamList>;

export default function CaseFoundScreen() {
  const navigation = useNavigation<Nav>();
  const closeCase = useAppModeStore((s) => s.closeCase);
  const { data: summary, isLoading } = useFoundSummary(DEMO_CASE_ID);

  const handleReport = () => navigation.navigate('ValidationReport');
  const handleClose = () => {
    closeCase();
    navigation.popToTop();
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.top}>
          {/* 성공 히어로 */}
          <View style={styles.hero}>
            <View style={styles.checkOuter}>
              <View style={styles.checkInner}>
                <Text style={styles.check} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  ✓
                </Text>
              </View>
            </View>
            <Text style={styles.heroTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              무사히 발견됐어요
            </Text>
            <Text style={styles.heroSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              골든타임 안에, 온 동네가 함께 찾았어요.{'\n'}어르신은 안전하게 가족 품으로 돌아갔습니다.
            </Text>

            {summary ? (
              <View
                style={styles.locPill}
                accessible
                accessibilityLabel={`발견 위치 ${summary.foundArea}`}
              >
                <Text
                  style={styles.locText}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                  numberOfLines={1}
                >
                  발견 위치 · {summary.foundArea}
                </Text>
              </View>
            ) : null}
          </View>

          {/* 요약 통계 */}
          {isLoading || !summary ? (
            <View style={styles.loading}>
              <ActivityIndicator color={operatorTheme.accent} />
            </View>
          ) : (
            <View
              style={styles.stats}
              accessible
              accessibilityLabel={`소요 시간 ${summary.elapsed}, 동원 시민 ${summary.citizens}명, 유효 제보 ${summary.validTips}건`}
            >
              <View style={styles.statCell}>
                <StatCard value={summary.elapsed} label="소요 시간" dark />
              </View>
              <View style={styles.statCell}>
                <StatCard value={summary.citizens} label="동원 시민" accent={operatorTheme.accent} dark />
              </View>
              <View style={styles.statCell}>
                <StatCard value={summary.validTips} label="유효 제보" dark />
              </View>
            </View>
          )}

          {/* 감사 카피 */}
          <View style={styles.thanks}>
            <Text style={styles.thanksText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              함께 찾아주신 이웃들, 제보해주신 시민 한 분 한 분 덕분입니다.{'\n'}당신의 관심이 한 사람의 하루를 지켰습니다.
            </Text>
          </View>
        </View>

        {/* 하단 액션 */}
        <View style={styles.actions}>
          <Pressable
            onPress={handleReport}
            accessibilityRole="button"
            accessibilityLabel="검증 수치 리포트 보기"
            accessibilityHint="예측 정확도와 검증 지표를 확인합니다"
            style={({ pressed }) => [styles.primaryBtn, pressed && styles.pressed]}
          >
            <Text
              style={styles.primaryLabel}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
              numberOfLines={1}
            >
              검증 수치 리포트 보기
            </Text>
          </Pressable>

          <Pressable
            onPress={handleClose}
            accessibilityRole="button"
            accessibilityLabel="닫기"
            accessibilityHint="사건을 종료하고 처음 화면으로 돌아갑니다"
            style={({ pressed }) => [styles.closeBtn, pressed && styles.pressed]}
          >
            <Text
              style={styles.closeLabel}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
              numberOfLines={1}
            >
              닫기
            </Text>
          </Pressable>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: operatorTheme.bg },
  scroll: {
    flexGrow: 1,
    justifyContent: 'space-between',
    paddingHorizontal: space.xl,
    paddingTop: space.xl,
    paddingBottom: space.lg,
  },
  top: { gap: space.xxl },

  hero: { alignItems: 'center', gap: space.lg, marginTop: space.xxl },
  checkOuter: {
    width: 112,
    height: 112,
    borderRadius: 56,
    backgroundColor: hexToRgba(color.walk, 0.16),
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkInner: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: color.walk,
    alignItems: 'center',
    justifyContent: 'center',
  },
  check: { fontSize: 40, color: '#FFFFFF', fontWeight: type.weight.black, fontFamily: type.family },
  heroTitle: {
    fontSize: 24,
    fontWeight: type.weight.black,
    color: operatorTheme.text,
    fontFamily: type.family,
    textAlign: 'center',
  },
  heroSub: {
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: operatorTheme.textSec,
    fontFamily: type.family,
    textAlign: 'center',
    lineHeight: 24,
  },
  locPill: {
    marginTop: space.xs,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    backgroundColor: operatorTheme.surfaceAlt,
    borderWidth: 1,
    borderColor: operatorTheme.border,
  },
  locText: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.walk,
    fontFamily: type.family,
  },

  loading: { paddingVertical: space.xl, alignItems: 'center' },
  stats: { flexDirection: 'row', gap: space.sm },
  statCell: { flex: 1 },

  thanks: {
    backgroundColor: operatorTheme.surface,
    borderColor: operatorTheme.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  thanksText: {
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: operatorTheme.textSec,
    fontFamily: type.family,
    lineHeight: 24,
    textAlign: 'center',
  },

  actions: { gap: space.md, marginTop: space.xxl },
  primaryBtn: {
    minHeight: 56,
    borderRadius: radius.lg,
    backgroundColor: operatorTheme.accent,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xl,
  },
  primaryLabel: {
    fontSize: type.size.body,
    fontWeight: type.weight.black,
    color: '#FFFFFF',
    fontFamily: type.family,
  },
  closeBtn: {
    minHeight: 56,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xl,
  },
  closeLabel: {
    fontSize: type.size.body,
    fontWeight: type.weight.bold,
    color: operatorTheme.text,
    fontFamily: type.family,
  },
  pressed: { opacity: 0.85 },
});
