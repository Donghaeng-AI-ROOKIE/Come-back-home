/**
 * 검증 수치 리포트 (spec §3.4, §4.4, CONTRACT #11). 운영자 다크 card.
 * - Ablation 수평 막대(돌아오길 AI 87% 하이라이트 vs 고전 61% vs 유형평균 44%) + % 라벨 + 요약 aria.
 * - JSD 게이지(0.081, "완전일치에 가까움") + hit@거리 380m + 누적 발견확률 84%.
 * 정보 그래픽은 요약 accessibilityLabel을 가진 View로 감싼다(spec §4.4). Back→goBack.
 */
import React from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { DimensionValue } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { color, radius, space, type } from '../theme/tokens';
import { operatorTheme } from '../theme/theme';
import { hexToRgba } from '../utils/color';
import { useValidation } from '../hooks/queries';
import { DEMO_CASE_ID } from '../data/missing';
import type { AblationBar } from '../types/domain';
import type { OperatorStackParamList } from '../navigation/types';
import StatCard from '../components/StatCard';

type Nav = NativeStackNavigationProp<OperatorStackParamList>;

const pct = (v: number) => Math.round(v * 100);

export default function ValidationReportScreen() {
  const navigation = useNavigation<Nav>();
  const { data: metrics, isLoading } = useValidation(DEMO_CASE_ID);

  const ablation: AblationBar[] = metrics?.ablation ?? [];
  const ablationA11y = ablation.map((b) => `${b.label} ${pct(b.value)}%`).join(', ');

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="light" />

      {/* 헤더 */}
      <View style={styles.header}>
        <Pressable
          onPress={() => navigation.goBack()}
          accessibilityRole="button"
          accessibilityLabel="뒤로"
          hitSlop={12}
          style={({ pressed }) => [styles.back, pressed && styles.pressed]}
        >
          <Text style={styles.backIcon} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            ←
          </Text>
        </Pressable>
        <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          검증 수치
        </Text>
        <View style={styles.back} />
      </View>

      {isLoading || !metrics ? (
        <View style={styles.loading}>
          <ActivityIndicator color={operatorTheme.accent} />
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <Text style={styles.intro} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            실측 데이터로 검증한 예측 성능이에요. 색·명도·수치로 함께 표기했습니다.
          </Text>

          {/* Ablation 수평 막대 차트 */}
          <View style={styles.card}>
            <Text style={styles.cardTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              예측 정확도 비교
            </Text>
            <Text style={styles.cardSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              예측 반경 내 실제 발견 비율 (Recall@구역)
            </Text>

            <View style={styles.bars} accessible accessibilityLabel={ablationA11y}>
              {ablation.map((bar) => {
                const p = pct(bar.value);
                const width = `${p}%` as DimensionValue;
                const fill = bar.highlight ? operatorTheme.accent : hexToRgba(color.operatorText, 0.3);
                return (
                  <View key={bar.label} style={styles.barRow}>
                    <View style={styles.barHead}>
                      <Text
                        style={[styles.barLabel, bar.highlight && styles.barLabelHi]}
                        allowFontScaling
                        maxFontSizeMultiplier={type.maxScale}
                        numberOfLines={1}
                      >
                        {bar.label}
                      </Text>
                      <Text
                        style={[styles.barPct, bar.highlight && styles.barPctHi]}
                        allowFontScaling
                        maxFontSizeMultiplier={type.maxScale}
                        numberOfLines={1}
                      >
                        {p}%
                      </Text>
                    </View>
                    <View style={styles.barTrack}>
                      <View style={[styles.barFill, { width, backgroundColor: fill }]} />
                    </View>
                  </View>
                );
              })}
            </View>

            <Text style={styles.note} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              돌아오길 AI가 가장 높은 발견 정확도를 보였어요.
            </Text>
          </View>

          {/* JSD 게이지 */}
          <View
            style={styles.card}
            accessible
            accessibilityLabel={`이동분포 유사도 JSD ${metrics.jsd}, 완전일치에 가까움`}
          >
            <Text style={styles.cardTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              이동분포 유사도 (JSD)
            </Text>
            <View style={styles.gaugeHead}>
              <Text style={styles.gaugeValue} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                {metrics.jsd.toFixed(3)}
              </Text>
              <Text style={styles.gaugeTag} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                완전일치에 가까움
              </Text>
            </View>
            <View style={styles.gaugeTrack}>
              <View
                style={[styles.gaugeFill, { width: `${pct(1 - metrics.jsd)}%` as DimensionValue }]}
              />
            </View>
            <View style={styles.gaugeScale}>
              <Text style={styles.gaugeEnd} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                완전일치
              </Text>
              <Text style={styles.gaugeEnd} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                불일치
              </Text>
            </View>
          </View>

          {/* hit@거리 + 누적 발견확률 */}
          <View style={styles.statRow}>
            <View style={styles.statCell}>
              <StatCard value={`${metrics.hitAtDistanceM}m`} label="예측 반경 내 발견 거리" dark />
            </View>
            <View style={styles.statCell}>
              <StatCard
                value={`${pct(metrics.cumulativePoa)}%`}
                label="누적 발견확률"
                accent={operatorTheme.accent}
                dark
              />
            </View>
          </View>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: operatorTheme.bg },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: operatorTheme.border,
  },
  back: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center' },
  backIcon: { fontSize: 24, color: operatorTheme.text, fontWeight: type.weight.bold, fontFamily: type.family },
  title: { fontSize: type.size.title, fontWeight: type.weight.black, color: operatorTheme.text, fontFamily: type.family },

  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  scroll: { paddingHorizontal: space.xl, paddingTop: space.lg, paddingBottom: space.xxl, gap: space.lg },
  intro: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: operatorTheme.textSec,
    fontFamily: type.family,
    lineHeight: 22,
  },

  card: {
    backgroundColor: operatorTheme.surface,
    borderColor: operatorTheme.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.lg,
    gap: space.md,
  },
  cardTitle: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: operatorTheme.text, fontFamily: type.family },
  cardSub: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: operatorTheme.textSec,
    fontFamily: type.family,
    marginTop: -space.xs,
  },

  bars: { gap: space.md },
  barRow: { gap: space.xs },
  barHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  barLabel: { fontSize: type.size.label, fontWeight: type.weight.bold, color: operatorTheme.textSec, fontFamily: type.family },
  barLabelHi: { color: operatorTheme.text, fontWeight: type.weight.black },
  barPct: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: operatorTheme.textSec,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
  },
  barPctHi: { color: operatorTheme.accent, fontWeight: type.weight.black },
  barTrack: { height: 24, borderRadius: radius.pill, backgroundColor: operatorTheme.surfaceAlt, overflow: 'hidden' },
  barFill: { height: 24, borderRadius: radius.pill },

  note: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: operatorTheme.textSec,
    fontFamily: type.family,
  },

  gaugeHead: { flexDirection: 'row', alignItems: 'baseline', gap: space.md },
  gaugeValue: {
    fontSize: type.size.bigNum,
    fontWeight: type.weight.black,
    color: operatorTheme.text,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
  },
  gaugeTag: { fontSize: type.size.label, fontWeight: type.weight.bold, color: color.walk, fontFamily: type.family },
  gaugeTrack: { height: 14, borderRadius: radius.pill, backgroundColor: operatorTheme.surfaceAlt, overflow: 'hidden' },
  gaugeFill: { height: 14, borderRadius: radius.pill, backgroundColor: color.walk },
  gaugeScale: { flexDirection: 'row', justifyContent: 'space-between' },
  gaugeEnd: { fontSize: type.size.caption, fontWeight: type.weight.medium, color: operatorTheme.textSec, fontFamily: type.family },

  statRow: { flexDirection: 'row', gap: space.sm },
  statCell: { flex: 1 },

  pressed: { opacity: 0.6 },
});
