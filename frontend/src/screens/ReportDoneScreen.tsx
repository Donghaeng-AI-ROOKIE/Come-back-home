/**
 * 제보 완료 (spec §3.3, CONTRACT screen #7). Root card, successWash 배경.
 * found-content.dc.html의 시각 언어(히어로 pop + 펄스 링 + 화이트 라운드 카드 + 소프트 섀도 +
 * 요약 통계 + 그라디언트 하단 CTA)를 시민 "제보 완료" 종착 화면으로 각색.
 *
 * 교정(§3.3): 성공=그린 체크(pop) 위 "앰버 링"(진행/기여 색), 배경 successWash,
 * 닫기(X)·확인 → Search, 기여 시각화는 수치 delta(㎢/%) + 풀어쓴 접근성 라벨,
 * delta 미산출 시 정성 fallback, 익명 전달 안내. 이모지 1개(🙏).
 */
import React, { useEffect, useRef } from 'react';
import { Animated, Easing, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Circle, Defs, Line, Path, Pattern, Rect } from 'react-native-svg';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import { poaMeta } from '../theme/poa';
import { hexToRgba } from '../utils/color';
import CTAButton from '../components/CTAButton';
import StatCard from '../components/StatCard';
import { DEMO_CASE_ID, MISSING_ANON } from '../data/missing';
import { buildFoundSummary } from '../data/mock';

// 컬러가 있는 표면 위 흰 전경 (CTAButton/StatCard와 동일 관용구).
const WHITE = '#FFFFFF';
// 히어로: 안심 그린워시 → successWash 로 은은하게 페이드 (found의 그라디언트 히어로 차용).
const HERO_GRADIENT = [color.walkWash, color.successWash] as const;
// 성공 체크 코어: 그린 그라디언트 (found의 그린 코어).
const CORE_GRADIENT = [color.walk, color.walkInk] as const;
// 진행/기여 CTA: 앰버 그라디언트.
const AMBER_GRADIENT = [color.search, color.searchInk] as const;

const fmtKm = (n: number): string => n.toFixed(1);

/**
 * 그린 체크 pop + 앰버 링 펄스.
 * 교정: found는 그린 링이지만 본 화면은 "성공=그린 체크 / 진행·기여=앰버" 위계에 따라
 * 링을 앰버(color.search)로 대체한다.
 */
function SuccessBadge() {
  const pop = useRef(new Animated.Value(0)).current;
  const pulseA = useRef(new Animated.Value(0)).current;
  const pulseB = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.spring(pop, { toValue: 1, friction: 5, tension: 70, useNativeDriver: true }).start();
    const mkPulse = (v: Animated.Value, delay: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(delay),
          Animated.timing(v, {
            toValue: 1,
            duration: 2400,
            easing: Easing.out(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(v, { toValue: 0, duration: 0, useNativeDriver: true }),
        ]),
      );
    const a = mkPulse(pulseA, 0);
    const b = mkPulse(pulseB, 1200);
    a.start();
    b.start();
    return () => {
      a.stop();
      b.stop();
    };
  }, [pop, pulseA, pulseB]);

  const coreScale = pop.interpolate({ inputRange: [0, 1], outputRange: [0.4, 1] });
  const ringTransform = (v: Animated.Value) => ({
    transform: [{ scale: v.interpolate({ inputRange: [0, 1], outputRange: [0.7, 1.85] }) }],
    opacity: v.interpolate({ inputRange: [0, 1], outputRange: [0.45, 0] }),
  });

  return (
    <View style={styles.badgeWrap} importantForAccessibility="no-hide-descendants">
      <Animated.View style={[styles.pulseRing, ringTransform(pulseA)]} />
      <Animated.View style={[styles.pulseRing, ringTransform(pulseB)]} />
      <View style={styles.amberRing}>
        <Animated.View style={[styles.coreShadow, { opacity: pop, transform: [{ scale: coreScale }] }]}>
          <LinearGradient colors={CORE_GRADIENT} start={{ x: 0.1, y: 0 }} end={{ x: 0.9, y: 1 }} style={styles.core}>
            <Svg width={46} height={46} viewBox="0 0 24 24" fill="none">
              <Path d="M5 12.5l4.5 4.5L19 7.5" stroke={WHITE} strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" />
            </Svg>
          </LinearGradient>
        </Animated.View>
      </View>
    </View>
  );
}

/** Before→After 구역 축소 시각화 (spec §4.2 이중부호화: 색+명도+패턴+크기+수치). */
function AreaShrink({ before, after }: { before: number; after: number }) {
  const W = 260;
  const H = 150;
  const maxSide = 112;
  const ratio = before > 0 ? Math.sqrt(Math.max(after, 0.05) / before) : 0.6;
  const beforeSide = maxSide;
  const afterSide = Math.max(30, Math.min(maxSide, maxSide * ratio));
  const bx = (W - beforeSide) / 2;
  const by = (H - beforeSide) / 2;
  const ax = (W - afterSide) / 2;
  const ay = (H - afterSide) / 2;
  const mid = poaMeta.mid;
  const high = poaMeta.high;

  return (
    <Svg width={W} height={H}>
      <Defs>
        <Pattern id="areaHatch" width={9} height={9} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <Line x1={0} y1={0} x2={0} y2={9} stroke={mid.border} strokeWidth={1.4} />
        </Pattern>
      </Defs>
      {/* 제보 전: 넓은 구역 — 앰버, 파선 테두리 + 45° 해치 (저확신·넓음) */}
      <Rect x={bx} y={by} width={beforeSide} height={beforeSide} rx={12} fill={hexToRgba(mid.fill, 0.16)} stroke={mid.border} strokeWidth={2} strokeDasharray="6 5" />
      <Rect x={bx} y={by} width={beforeSide} height={beforeSide} rx={12} fill="url(#areaHatch)" />
      {/* 제보 후: 좁혀진 구역 — 진홍 solid (고확신·좁음) */}
      <Rect x={ax} y={ay} width={afterSide} height={afterSide} rx={9} fill={hexToRgba(high.fill, 0.9)} stroke={high.border} strokeWidth={2} />
      {/* 중심(최종 목격 추정) */}
      <Circle cx={W / 2} cy={H / 2} r={4.5} fill={color.surface} stroke={high.border} strokeWidth={1.6} />
    </Svg>
  );
}

/** 기여 카드 상단 앰버 뱃지 (found의 그린 "시민 제보로 발견" 뱃지 → 앰버 진행색). */
function ContribBadge() {
  return (
    <View style={styles.kickerPill}>
      <Svg width={14} height={14} viewBox="0 0 24 24" fill="none">
        <Path d="M5 12l4.5 4.5L19 7" stroke={color.searchInk} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
      </Svg>
      <Text style={styles.kickerText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        내 제보 반영
      </Text>
    </View>
  );
}

function ContributionNumeric({ before, after, deltaPct }: { before: number; after: number; deltaPct: number }) {
  const pctText = `${deltaPct < 0 ? '−' : '+'}${Math.abs(deltaPct)}%`;
  const a11y = `당신의 제보로 예상 수색 구역이 ${fmtKm(before)}제곱킬로미터에서 ${fmtKm(after)}제곱킬로미터로 좁혀졌습니다. 약 ${Math.abs(deltaPct)}퍼센트 줄었어요.`;

  return (
    <View style={[styles.card, styles.cardShadow]} accessible accessibilityLabel={a11y}>
      <ContribBadge />
      <Text style={styles.cardTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        수색 구역이 좁혀졌어요
      </Text>

      <View style={styles.vizWrap} importantForAccessibility="no-hide-descendants">
        <AreaShrink before={before} after={after} />
      </View>

      <View style={styles.legendRow} importantForAccessibility="no-hide-descendants">
        <View style={styles.legendItem}>
          <View style={[styles.legendSwatch, { backgroundColor: hexToRgba(poaMeta.mid.fill, 0.16), borderColor: poaMeta.mid.border, borderStyle: 'dashed' }]} />
          <Text style={styles.legendText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            제보 전 {fmtKm(before)}㎢
          </Text>
        </View>
        <View style={styles.legendItem}>
          <View style={[styles.legendSwatch, { backgroundColor: hexToRgba(poaMeta.high.fill, 0.9), borderColor: poaMeta.high.border }]} />
          <Text style={styles.legendText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            제보 후 {fmtKm(after)}㎢
          </Text>
        </View>
      </View>

      <View style={styles.deltaRow} importantForAccessibility="no-hide-descendants">
        <Text style={styles.deltaText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          예상 수색 구역 {fmtKm(before)}㎢ → {fmtKm(after)}㎢
        </Text>
        <View style={styles.deltaBadge}>
          <Text style={styles.deltaBadgeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {pctText}
          </Text>
        </View>
      </View>
    </View>
  );
}

function ContributionFallback() {
  return (
    <View style={[styles.card, styles.cardShadow]} accessible accessibilityLabel="제보가 수색팀에 반영됐어요. 수색 구역이 좁혀지면 알려드릴게요.">
      <ContribBadge />
      <Text style={styles.cardTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        제보가 수색팀에 반영됐어요
      </Text>
      <Text style={styles.cardBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        {MISSING_ANON}을 찾는 데 큰 힘이 됩니다. 수색 구역이 좁혀지면 여기서 알려드릴게요.
      </Text>
    </View>
  );
}

/** 앰버 그라디언트 주 CTA (found의 그라디언트 프라이머리 버튼 차용). */
function PrimaryButton({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint="수색 지도로 돌아갑니다"
      style={({ pressed }) => [styles.primaryWrap, pressed && styles.pressed]}
    >
      <LinearGradient colors={AMBER_GRADIENT} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.primaryGrad}>
        <Svg width={22} height={22} viewBox="0 0 24 24" fill="none">
          <Path d="M5 12l4.5 4.5L19 7" stroke={WHITE} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
        </Svg>
        <Text style={styles.primaryLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
          {label}
        </Text>
      </LinearGradient>
    </Pressable>
  );
}

export default function ReportDoneScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'ReportDone'>>();
  const { caseId, beforeAreaKm2, afterAreaKm2, deltaPct } = route.params;
  const targetCaseId = caseId ?? DEMO_CASE_ID;
  const fs = buildFoundSummary();

  const goSearch = () => navigation.navigate('CitizenTabs', { screen: 'Search' });
  const goReportChat = () => navigation.navigate('ReportChat', { caseId: targetCaseId });

  const hasDelta =
    typeof beforeAreaKm2 === 'number' && typeof afterAreaKm2 === 'number' && typeof deltaPct === 'number';

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="dark" />

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* 히어로 */}
        <LinearGradient colors={HERO_GRADIENT} start={{ x: 0, y: 0 }} end={{ x: 0, y: 1 }} style={styles.hero}>
          <View
            style={styles.heroInner}
            accessible
            accessibilityLabel="제보가 전달됐어요. 수색팀에 바로 전달됐어요. 큰 도움이 됩니다."
          >
            <SuccessBadge />
            <Text style={styles.heroTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              제보가 전달됐어요
            </Text>
            <Text style={styles.heroSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              수색팀에 바로 전달됐어요. 큰 도움이 됩니다 🙏
            </Text>
          </View>
        </LinearGradient>

        <View style={styles.content}>
          {/* [핵심] 기여 시각화 */}
          {hasDelta && beforeAreaKm2 != null && afterAreaKm2 != null && deltaPct != null ? (
            <ContributionNumeric before={beforeAreaKm2} after={afterAreaKm2} deltaPct={deltaPct} />
          ) : (
            <ContributionFallback />
          )}

          {/* 기여 요약 통계 (found "함께한 기록" 패턴 · 앰버 잉크) */}
          <View>
            <Text style={styles.sectionLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              지금 함께 찾고 있어요
            </Text>
            <View style={styles.statRow}>
              <View style={styles.statCell}>
                <StatCard value="✓" label="내 제보 반영" accent={color.searchInk} />
              </View>
              <View style={styles.statCell}>
                <StatCard value={fs.citizens} label="함께 찾는 이웃" accent={color.searchInk} />
              </View>
              <View style={styles.statCell}>
                <StatCard value={fs.validTips} label="유효 제보" accent={color.searchInk} />
              </View>
            </View>
          </View>

          {/* 익명 안내 (found 회수 배너 패턴) */}
          <View style={styles.anonPill}>
            <Svg width={18} height={18} viewBox="0 0 24 24" fill="none" style={styles.anonIcon}>
              <Path
                d="M12 3l7 3v5c0 4.6-3.1 7.7-7 9-3.9-1.3-7-4.4-7-9V6l7-3Z"
                stroke={color.searchInk}
                strokeWidth={1.9}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <Path d="M9 12l2 2 4-4" stroke={color.searchInk} strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" />
            </Svg>
            <Text style={styles.anonText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              익명으로 전달됐어요 · 제보자의 위치와 신원은 공개되지 않아요
            </Text>
          </View>
        </View>
      </ScrollView>

      {/* 하단 액션바 (found의 화이트 풋터 + 그라디언트 프라이머리 + 아웃라인 세컨더리) */}
      <View style={styles.footer}>
        <PrimaryButton label="확인" onPress={goSearch} />
        <View style={styles.gapSm} />
        <CTAButton
          label="추가로 본 게 있어요"
          onPress={goReportChat}
          variant="ghost"
          accessibilityHint="제보를 이어서 작성합니다"
        />
        <Pressable
          onPress={goSearch}
          accessibilityRole="button"
          accessibilityLabel="내 주변 계속 살펴보기"
          hitSlop={8}
          style={({ pressed }) => [styles.link, pressed && styles.pressed]}
        >
          <Text style={styles.linkText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            내 주변 계속 살펴보기
          </Text>
        </Pressable>
      </View>

      {/* 닫기 (히어로 위 플로팅) */}
      <Pressable
        onPress={goSearch}
        accessibilityRole="button"
        accessibilityLabel="닫기"
        hitSlop={12}
        style={({ pressed }) => [styles.closeBtn, pressed && styles.pressed]}
      >
        <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
          <Path d="M6 6l12 12M18 6L6 18" stroke={color.text} strokeWidth={2.2} strokeLinecap="round" />
        </Svg>
      </Pressable>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.successWash },
  scroll: { paddingBottom: space.xl },

  closeBtn: {
    position: 'absolute',
    top: space.md,
    right: space.md,
    width: 40,
    height: 40,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: hexToRgba(color.surface, 0.82),
    shadowColor: color.text,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.12,
    shadowRadius: 10,
    elevation: 3,
    zIndex: 30,
  },

  // ── 히어로 ──
  hero: { paddingTop: space.xxl, paddingBottom: space.xl, paddingHorizontal: space.xl, overflow: 'hidden' },
  heroInner: { alignItems: 'center', gap: space.md },
  badgeWrap: { width: 120, height: 120, alignItems: 'center', justifyContent: 'center' },
  pulseRing: {
    position: 'absolute',
    top: 12,
    left: 12,
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: hexToRgba(color.search, 0.18),
  },
  amberRing: {
    width: 108,
    height: 108,
    borderRadius: 54,
    borderWidth: 5,
    borderColor: color.search,
    backgroundColor: color.searchWash,
    alignItems: 'center',
    justifyContent: 'center',
  },
  coreShadow: {
    borderRadius: 40,
    shadowColor: color.walkInk,
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.4,
    shadowRadius: 22,
    elevation: 8,
  },
  core: {
    width: 78,
    height: 78,
    borderRadius: 39,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  heroTitle: {
    fontSize: 27,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    textAlign: 'center',
    letterSpacing: -0.5,
    marginTop: space.sm,
  },
  heroSub: {
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
    textAlign: 'center',
    lineHeight: 24,
  },

  // ── 콘텐츠 ──
  content: { paddingHorizontal: space.xl, paddingTop: space.md, gap: space.lg },

  card: {
    backgroundColor: color.surface,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.xl,
    gap: space.md,
    alignItems: 'center',
  },
  cardShadow: {
    shadowColor: color.text,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.08,
    shadowRadius: 22,
    elevation: 3,
  },
  kickerPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    backgroundColor: color.searchWash,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    alignSelf: 'center',
  },
  kickerText: { fontSize: type.size.label, fontWeight: type.weight.black, color: color.searchInk, fontFamily: type.family },
  cardTitle: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: color.text, fontFamily: type.family, textAlign: 'center' },
  cardBody: {
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
    textAlign: 'center',
    lineHeight: 24,
  },
  vizWrap: { alignItems: 'center', justifyContent: 'center', paddingVertical: space.sm },
  legendRow: { flexDirection: 'row', justifyContent: 'center', flexWrap: 'wrap', gap: space.lg },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  legendSwatch: { width: 18, height: 18, borderRadius: radius.sm, borderWidth: 1.5 },
  legendText: { fontSize: type.size.caption, fontWeight: type.weight.bold, color: color.textBody, fontFamily: type.family },
  deltaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    flexWrap: 'wrap',
    gap: space.sm,
    backgroundColor: color.searchWash,
    borderRadius: radius.md,
    paddingVertical: space.md,
    paddingHorizontal: space.lg,
    alignSelf: 'stretch',
  },
  deltaText: { fontSize: type.size.label, fontWeight: type.weight.black, color: color.searchInk, fontFamily: type.family },
  deltaBadge: { backgroundColor: color.search, borderRadius: radius.pill, paddingHorizontal: space.md, paddingVertical: space.xs },
  deltaBadgeText: { fontSize: type.size.label, fontWeight: type.weight.black, color: WHITE, fontFamily: type.family, fontVariant: ['tabular-nums'] },

  // ── 통계 ──
  sectionLabel: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.textCaption,
    fontFamily: type.family,
    marginBottom: space.sm,
    marginLeft: space.xs,
  },
  statRow: { flexDirection: 'row', gap: space.sm },
  statCell: { flex: 1 },

  // ── 익명 안내 ──
  anonPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: color.searchWash,
    borderRadius: radius.lg,
    paddingVertical: space.md,
    paddingHorizontal: space.lg,
  },
  anonIcon: { flexShrink: 0 },
  anonText: {
    flex: 1,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.searchInk,
    fontFamily: type.family,
    lineHeight: 19,
  },

  // ── 풋터 ──
  footer: {
    paddingHorizontal: space.xl,
    paddingTop: space.md,
    paddingBottom: space.sm,
    borderTopWidth: 1,
    borderTopColor: color.border,
    backgroundColor: color.surface,
  },
  primaryWrap: {
    borderRadius: radius.lg,
    shadowColor: color.search,
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.3,
    shadowRadius: 20,
    elevation: 6,
  },
  primaryGrad: {
    minHeight: 58,
    borderRadius: radius.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    paddingHorizontal: space.xl,
    overflow: 'hidden',
  },
  primaryLabel: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: WHITE, fontFamily: type.family },
  gapSm: { height: space.sm },
  link: { alignSelf: 'center', paddingVertical: space.md, minHeight: 44, justifyContent: 'center' },
  linkText: { fontSize: type.size.label, fontWeight: type.weight.bold, color: color.searchInk, fontFamily: type.family, textDecorationLine: 'underline' },
  pressed: { opacity: 0.85 },
});
