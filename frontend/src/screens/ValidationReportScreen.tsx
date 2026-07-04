/**
 * 검증 수치 리포트 (spec §3.4, §4.4, CONTRACT #11). 운영자 다크 card.
 * DesignSync `validation-content.dc.html` 목업을 다크 운영자 테마로 포팅.
 *  - 핵심 지표 2카드(발견률·오차거리) + ablation 수평 막대(돌아오길 AI 87% 하이라이트
 *    vs 고전 61% vs 유형평균 44%, 그라디언트 하이라이트) + % 라벨 + 요약 aria.
 *  - JSD 게이지(0.081, 초록→앰버→빨강 스케일 + 마커 · "완전일치에 가까움").
 *  - 누적 발견확률 84% 프로그레스 + hit@거리 380m + 홀드아웃 검증 통과 배지.
 * 교정: 목업 라이트 → 운영자 다크(operatorTheme). 저대비 #8B909A/--muted → operator 토큰.
 * 정보 그래픽은 요약 accessibilityLabel을 가진 View로 감싼다(spec §4.4). Back→goBack.
 */
import React from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { DimensionValue } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Path } from 'react-native-svg';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { color, poa, radius, space, type } from '../theme/tokens';
import { operatorTheme } from '../theme/theme';
import { hexToRgba } from '../utils/color';
import { useValidation } from '../hooks/queries';
import { DEMO_CASE_ID } from '../data/missing';
import type { AblationBar } from '../types/domain';
import type { OperatorStackParamList } from '../navigation/types';

type Nav = NativeStackNavigationProp<OperatorStackParamList>;

const pct = (v: number) => Math.round(v * 100);

/** spec §4.4 — ablation 막대 대체텍스트(확정 문구). */
const ABLATION_A11Y = '돌아오길 AI 87%, 고전모델 61%, 유형평균 44%';

/** 하이라이트 막대: 앰버 accent 그라디언트(목업 #F0913F→#E8703F). */
const BAR_GRADIENT = [color.search, color.searchInk] as const;
/** JSD 스케일: 완전일치(그린)→중간(앰버)→불일치(레드). poa.low.fill=#F5A623. */
const JSD_GRADIENT = [color.walk, poa.low.fill, color.critical] as const;
const JSD_LOCATIONS = [0, 0.55, 1] as const;
/** 하이라이트가 아닌 막대의 다크용 그레이(명도 하강). */
const CLASSIC_FILL = hexToRgba(color.operatorText, 0.45);
const TYPEAVG_FILL = hexToRgba(color.operatorText, 0.26);
/** 통과 배지 그린 워시(다크). */
const OK_WASH = hexToRgba(color.walk, 0.13);
const OK_BORDER = hexToRgba(color.walk, 0.34);
const GRAD_START = { x: 0, y: 0 };
const GRAD_END = { x: 1, y: 0 };

export default function ValidationReportScreen() {
  const navigation = useNavigation<Nav>();
  const { data: metrics, isLoading } = useValidation(DEMO_CASE_ID);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="light" />

      {/* 헤더 — 목업 카피 유지, 교정: 다크 표면 + operator 토큰 */}
      <View style={styles.header}>
        <Pressable
          onPress={() => navigation.goBack()}
          accessibilityRole="button"
          accessibilityLabel="뒤로"
          hitSlop={12}
          style={({ pressed }) => [styles.back, pressed && styles.pressed]}
        >
          <Svg width={24} height={24} viewBox="0 0 24 24" fill="none">
            <Path
              d="M15 5l-7 7 7 7"
              stroke={operatorTheme.text}
              strokeWidth={2.2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </Svg>
        </Pressable>
        <View style={styles.headerText}>
          <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
            왜 AI인가 · 검증 리포트
          </Text>
          <Text style={styles.subtitle} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
            사람의 눈이 아니라 수치로 증명합니다
          </Text>
        </View>
      </View>

      {isLoading || !metrics ? (
        <View style={styles.loading}>
          <ActivityIndicator color={operatorTheme.accent} />
        </View>
      ) : (
        (() => {
          const ablation: AblationBar[] = metrics.ablation;
          const heroBar = ablation.find((b) => b.highlight);
          const classicBar = ablation.find((b) => !b.highlight);
          const heroPct = heroBar ? pct(heroBar.value) : 0;
          const deltaP = heroBar && classicBar ? pct(heroBar.value) - pct(classicBar.value) : 0;
          const jsdPct = metrics.jsd * 100;
          const cumPct = pct(metrics.cumulativePoa);

          return (
            <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
              {/* 핵심 지표 2카드 */}
              <View style={styles.heroRow}>
                <View
                  style={styles.heroCard}
                  accessible
                  accessibilityLabel={`예측 반경 내 발견률 ${heroPct}퍼센트, 고전 대비 ${deltaP}%p 높음`}
                >
                  <Text style={styles.heroLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    예측 반경 내 발견률
                  </Text>
                  <View style={styles.heroValueRow}>
                    <Text style={styles.heroNumAcc} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      {heroPct}
                    </Text>
                    <Text style={styles.heroUnitAcc} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      %
                    </Text>
                  </View>
                  <View style={styles.okPill}>
                    <Svg width={12} height={12} viewBox="0 0 24 24" fill="none">
                      <Path
                        d="M6 15l6-6 6 6"
                        stroke={color.walk}
                        strokeWidth={3}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </Svg>
                    <Text style={styles.okPillText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      고전 대비 +{deltaP}%p
                    </Text>
                  </View>
                </View>

                <View
                  style={styles.heroCard}
                  accessible
                  accessibilityLabel={`예측-실제 오차 거리 ${metrics.hitAtDistanceM}미터, 중앙값`}
                >
                  <Text style={styles.heroLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    예측–실제 오차 거리
                  </Text>
                  <View style={styles.heroValueRow}>
                    <Text style={styles.heroNum} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      {metrics.hitAtDistanceM}
                    </Text>
                    <Text style={styles.heroUnit} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      m
                    </Text>
                  </View>
                  <View style={styles.grayPill}>
                    <Text style={styles.grayPillText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      중앙값 · n=1,204
                    </Text>
                  </View>
                </View>
              </View>

              {/* Ablation 수평 막대 */}
              <View style={styles.card}>
                <Text style={styles.cardTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  모델 비교 · 예측 반경 내 발견률
                </Text>
                <Text style={styles.cardSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  동일 테스트셋 기준 ablation
                </Text>

                <View style={styles.bars} accessible accessibilityLabel={ABLATION_A11Y}>
                  {ablation.map((bar) => {
                    const p = pct(bar.value);
                    const width = `${p}%` as DimensionValue;
                    const hi = !!bar.highlight;
                    return (
                      <View key={bar.label} style={styles.barBlock}>
                        <View style={styles.barHead}>
                          <Text
                            style={[styles.barLabel, hi && styles.barLabelHi]}
                            allowFontScaling
                            maxFontSizeMultiplier={type.maxScale}
                            numberOfLines={1}
                          >
                            {bar.label}
                          </Text>
                          <Text
                            style={[styles.barPct, hi && styles.barPctHi]}
                            allowFontScaling
                            maxFontSizeMultiplier={type.maxScale}
                            numberOfLines={1}
                          >
                            {p}%
                          </Text>
                        </View>
                        <View style={styles.barTrack}>
                          {hi ? (
                            <LinearGradient
                              colors={BAR_GRADIENT}
                              start={GRAD_START}
                              end={GRAD_END}
                              style={[styles.barFill, { width }]}
                            />
                          ) : (
                            <View
                              style={[
                                styles.barFill,
                                { width, backgroundColor: bar === classicBar ? CLASSIC_FILL : TYPEAVG_FILL },
                              ]}
                            />
                          )}
                        </View>
                      </View>
                    );
                  })}
                </View>
              </View>

              {/* JSD 게이지 */}
              <View
                style={styles.card}
                accessible
                accessibilityLabel={`이동분포 유사도 JSD ${metrics.jsd.toFixed(3)}, 완전일치에 가까움`}
              >
                <View style={styles.jsdHead}>
                  <View style={styles.jsdHeadText}>
                    <Text style={styles.cardTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      집단 이동분포 유사도
                    </Text>
                    <Text style={styles.cardSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      예측 분포 vs 실제 이동 분포 (Jensen–Shannon)
                    </Text>
                  </View>
                  <View style={styles.jsdValueBox}>
                    <Text style={styles.jsdTag} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      JSD
                    </Text>
                    <Text style={styles.jsdValue} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      {metrics.jsd.toFixed(3)}
                    </Text>
                  </View>
                </View>

                <View style={styles.jsdTrackWrap}>
                  <LinearGradient
                    colors={JSD_GRADIENT}
                    locations={JSD_LOCATIONS}
                    start={GRAD_START}
                    end={GRAD_END}
                    style={styles.jsdTrack}
                  />
                  <View style={[styles.jsdMarker, { left: `${jsdPct}%` as DimensionValue }]} />
                </View>

                <View style={styles.scaleRow}>
                  <Text style={styles.scaleEnd} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    0 · 완전 일치
                  </Text>
                  <Text style={styles.scaleTag} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    완전일치에 가까움
                  </Text>
                  <Text style={styles.scaleEnd} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    1 · 불일치
                  </Text>
                </View>
              </View>

              {/* 누적 발견확률 */}
              <View
                style={styles.card}
                accessible
                accessibilityLabel={`누적 발견확률 ${cumPct}퍼센트`}
              >
                <View style={styles.jsdHead}>
                  <View style={styles.jsdHeadText}>
                    <Text style={styles.cardTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      누적 발견 확률
                    </Text>
                    <Text style={styles.cardSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      예측 반경 6시간 누적 커버리지
                    </Text>
                  </View>
                  <View style={styles.cumValueRow}>
                    <Text style={styles.cumValue} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      {cumPct}
                    </Text>
                    <Text style={styles.cumUnit} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      %
                    </Text>
                  </View>
                </View>
                <View style={styles.cumTrack}>
                  <View style={[styles.cumFill, { width: `${cumPct}%` as DimensionValue }]} />
                </View>
              </View>

              {/* 통과 배지 */}
              <View style={styles.badgeRow}>
                <View
                  style={styles.passBadge}
                  accessible
                  accessibilityLabel="페르소나 일관성 통과, 재현 편차 3퍼센트 미만"
                >
                  <View style={styles.passTile}>
                    <Svg width={19} height={19} viewBox="0 0 24 24" fill="none">
                      <Path
                        d="M5 12l4.5 4.5L19 7"
                        stroke="#FFFFFF"
                        strokeWidth={2.6}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </Svg>
                  </View>
                  <Text style={styles.passTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    페르소나 일관성
                  </Text>
                  <Text style={styles.passSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    {'통과 · 재현 편차 <3%'}
                  </Text>
                </View>

                <View
                  style={styles.passBadge}
                  accessible
                  accessibilityLabel="데이터 오염 테스트 통과, 누출 없음"
                >
                  <View style={styles.passTile}>
                    <Svg width={19} height={19} viewBox="0 0 24 24" fill="none">
                      <Path
                        d="M12 3.5 5 6.2v4.6c0 4.2 2.9 7.4 7 8.7 4.1-1.3 7-4.5 7-8.7V6.2L12 3.5Z"
                        stroke="#FFFFFF"
                        strokeWidth={2.2}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                      <Path
                        d="M9 11.5l2.2 2.2 3.8-4"
                        stroke="#FFFFFF"
                        strokeWidth={2.2}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </Svg>
                  </View>
                  <Text style={styles.passTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    데이터 오염 테스트
                  </Text>
                  <Text style={styles.passSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    통과 · 누출 없음
                  </Text>
                </View>
              </View>

              <Text style={styles.footer} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                테스트셋 n=1,204 실제 실종 사례 · 홀드아웃 검증 · 학습·평가 지역 분리
              </Text>
            </ScrollView>
          );
        })()
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: operatorTheme.bg },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    backgroundColor: operatorTheme.surface,
    borderBottomWidth: 1,
    borderBottomColor: operatorTheme.border,
  },
  back: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  headerText: { flex: 1, minWidth: 0 },
  title: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: operatorTheme.text,
    fontFamily: type.family,
    letterSpacing: -0.3,
  },
  subtitle: {
    marginTop: 1,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: operatorTheme.textSec,
    fontFamily: type.family,
  },

  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  scroll: { paddingHorizontal: space.lg, paddingTop: space.lg, paddingBottom: space.xxl, gap: space.md },

  // 핵심 지표
  heroRow: { flexDirection: 'row', gap: space.md },
  heroCard: {
    flex: 1,
    backgroundColor: operatorTheme.surface,
    borderColor: operatorTheme.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.lg,
    shadowColor: '#000000',
    shadowOpacity: 0.28,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 3,
  },
  heroLabel: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: operatorTheme.textSec,
    fontFamily: type.family,
    lineHeight: 20,
  },
  heroValueRow: { flexDirection: 'row', alignItems: 'baseline', marginTop: space.sm },
  heroNum: {
    fontSize: type.size.bigNum,
    fontWeight: type.weight.black,
    color: operatorTheme.text,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
    letterSpacing: -1,
  },
  heroNumAcc: {
    fontSize: type.size.bigNum,
    fontWeight: type.weight.black,
    color: operatorTheme.accent,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
    letterSpacing: -1,
  },
  heroUnit: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: operatorTheme.text,
    fontFamily: type.family,
    marginLeft: 2,
  },
  heroUnitAcc: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: operatorTheme.accent,
    fontFamily: type.family,
    marginLeft: 2,
  },
  okPill: {
    marginTop: space.sm,
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    backgroundColor: OK_WASH,
    borderRadius: radius.pill,
    paddingVertical: 3,
    paddingHorizontal: space.sm,
  },
  okPillText: { fontSize: type.size.caption, fontWeight: type.weight.black, color: color.walk, fontFamily: type.family },
  grayPill: {
    marginTop: space.sm,
    alignSelf: 'flex-start',
    backgroundColor: operatorTheme.surfaceAlt,
    borderRadius: radius.pill,
    paddingVertical: 3,
    paddingHorizontal: space.sm,
  },
  grayPillText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: operatorTheme.textSec,
    fontFamily: type.family,
  },

  // 카드 공통
  card: {
    backgroundColor: operatorTheme.surface,
    borderColor: operatorTheme.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.lg,
    gap: space.md,
    shadowColor: '#000000',
    shadowOpacity: 0.28,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 3,
  },
  cardTitle: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: operatorTheme.text,
    fontFamily: type.family,
    letterSpacing: -0.2,
  },
  cardSub: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: operatorTheme.textSec,
    fontFamily: type.family,
    marginTop: -space.sm,
  },

  // ablation
  bars: { gap: space.md, marginTop: space.xs },
  barBlock: { gap: space.sm },
  barHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  barLabel: { fontSize: type.size.label, fontWeight: type.weight.bold, color: operatorTheme.textSec, fontFamily: type.family },
  barLabelHi: { color: operatorTheme.accent, fontWeight: type.weight.black },
  barPct: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: operatorTheme.textSec,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
  },
  barPctHi: { color: operatorTheme.accent },
  barTrack: { height: 16, borderRadius: radius.pill, backgroundColor: operatorTheme.surfaceAlt, overflow: 'hidden' },
  barFill: { height: 16, borderRadius: radius.pill },

  // JSD
  jsdHead: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: space.md },
  jsdHeadText: { flex: 1, minWidth: 0, gap: space.md },
  jsdValueBox: { alignItems: 'flex-end' },
  jsdTag: { fontSize: type.size.caption, fontWeight: type.weight.bold, color: operatorTheme.textSec, fontFamily: type.family },
  jsdValue: {
    fontSize: type.size.bigNum,
    fontWeight: type.weight.black,
    color: color.walk,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
    letterSpacing: -0.5,
    lineHeight: type.size.bigNum,
  },
  jsdTrackWrap: { height: 16, justifyContent: 'center' },
  jsdTrack: { height: 8, borderRadius: radius.pill, opacity: 0.9 },
  jsdMarker: {
    position: 'absolute',
    width: 16,
    height: 16,
    borderRadius: 8,
    marginLeft: -8,
    backgroundColor: '#FFFFFF',
    borderWidth: 3,
    borderColor: color.walk,
  },
  scaleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  scaleEnd: { fontSize: type.size.caption, fontWeight: type.weight.medium, color: operatorTheme.textSec, fontFamily: type.family },
  scaleTag: { fontSize: type.size.caption, fontWeight: type.weight.bold, color: color.walk, fontFamily: type.family },

  // 누적 발견확률
  cumValueRow: { flexDirection: 'row', alignItems: 'baseline' },
  cumValue: {
    fontSize: type.size.bigNum,
    fontWeight: type.weight.black,
    color: operatorTheme.accent,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
    letterSpacing: -0.5,
    lineHeight: type.size.bigNum,
  },
  cumUnit: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: operatorTheme.accent, fontFamily: type.family, marginLeft: 2 },
  cumTrack: { height: 12, borderRadius: radius.pill, backgroundColor: operatorTheme.surfaceAlt, overflow: 'hidden' },
  cumFill: { height: 12, borderRadius: radius.pill, backgroundColor: operatorTheme.accent },

  // 통과 배지
  badgeRow: { flexDirection: 'row', gap: space.md },
  passBadge: {
    flex: 1,
    backgroundColor: OK_WASH,
    borderColor: OK_BORDER,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  passTile: {
    width: 34,
    height: 34,
    borderRadius: radius.md,
    backgroundColor: color.walk,
    alignItems: 'center',
    justifyContent: 'center',
  },
  passTitle: {
    marginTop: space.md,
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: operatorTheme.text,
    fontFamily: type.family,
  },
  passSub: {
    marginTop: space.xs,
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: color.walk,
    fontFamily: type.family,
  },

  footer: {
    marginTop: space.xs,
    textAlign: 'center',
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: operatorTheme.textSec,
    fontFamily: type.family,
    lineHeight: 20,
  },

  pressed: { opacity: 0.6 },
});
