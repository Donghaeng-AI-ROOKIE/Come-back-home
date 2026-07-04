/**
 * 제보 완료 (spec §3.3, CONTRACT screen #7). Root card, successWash 배경.
 * 종착 화면: (1) 확실한 완료감, (2) 기여 시각화 = 내 제보로 수색 구역이 좁혀짐(수치 delta).
 * 성공=그린 체크, 진행/기여=앰버. 닫기(X)·확인 → Search. 익명 전달 안내. 이모지 1개(🙏).
 */
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import Svg, { Circle, Defs, Line, Pattern, Rect } from 'react-native-svg';
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

const fmtKm = (n: number): string => n.toFixed(1);

/** Before→After 구역 축소 시각화 (spec §4.2 이중부호화: 색+명도+패턴+크기+수치). */
function AreaShrink({ before, after }: { before: number; after: number }) {
  const W = 260;
  const H = 152;
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
      {/* 제보 전: 넓은 구역 — 앰버, 파선 테두리 + 사선 해치 */}
      <Rect x={bx} y={by} width={beforeSide} height={beforeSide} rx={12} fill={hexToRgba(mid.fill, 0.16)} stroke={mid.border} strokeWidth={2} strokeDasharray="6 5" />
      <Rect x={bx} y={by} width={beforeSide} height={beforeSide} rx={12} fill="url(#areaHatch)" />
      {/* 제보 후: 좁혀진 구역 — 진홍 solid */}
      <Rect x={ax} y={ay} width={afterSide} height={afterSide} rx={9} fill={hexToRgba(high.fill, 0.9)} stroke={high.border} strokeWidth={2} />
      {/* 중심(최종 목격 추정) */}
      <Circle cx={W / 2} cy={H / 2} r={4.5} fill={color.surface} stroke={high.border} strokeWidth={1.6} />
    </Svg>
  );
}

function ContributionNumeric({ before, after, deltaPct }: { before: number; after: number; deltaPct: number }) {
  const pctText = `${deltaPct < 0 ? '−' : '+'}${Math.abs(deltaPct)}%`;
  const a11y = `당신의 제보로 예상 수색 구역이 ${fmtKm(before)}제곱킬로미터에서 ${fmtKm(after)}제곱킬로미터로 좁혀졌습니다. 약 ${Math.abs(deltaPct)}퍼센트 줄었어요.`;

  return (
    <View style={styles.contribCard} accessible accessibilityLabel={a11y}>
      <Text style={styles.contribKicker} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        내 제보의 힘
      </Text>
      <Text style={styles.contribTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
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
    <View style={styles.contribCard} accessible accessibilityLabel="제보가 수색팀에 반영됐어요">
      <Text style={styles.contribKicker} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        내 제보의 힘
      </Text>
      <Text style={styles.contribTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        제보가 수색팀에 반영됐어요
      </Text>
      <Text style={styles.contribBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        {MISSING_ANON}를 찾는 데 큰 힘이 됩니다. 수색 구역이 좁혀지면 여기서 알려드릴게요.
      </Text>
    </View>
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

      {/* 닫기 */}
      <View style={styles.topBar}>
        <Pressable
          onPress={goSearch}
          accessibilityRole="button"
          accessibilityLabel="닫기"
          hitSlop={12}
          style={({ pressed }) => [styles.closeBtn, pressed && styles.pressed]}
        >
          <Text style={styles.closeIcon} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            ✕
          </Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {/* 히어로 */}
        <View style={styles.hero} accessible accessibilityLabel="제보가 전달됐어요. 수색팀에 바로 전달됐어요. 큰 도움이 됩니다.">
          <View style={styles.badgeRing}>
            <View style={styles.badgeCore}>
              <Text style={styles.badgeCheck} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                ✓
              </Text>
            </View>
          </View>
          <Text style={styles.heroTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            제보가 전달됐어요
          </Text>
          <Text style={styles.heroSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            수색팀에 바로 전달됐어요. 큰 도움이 됩니다 🙏
          </Text>
        </View>

        {/* 기여 시각화 */}
        {hasDelta && beforeAreaKm2 != null && afterAreaKm2 != null && deltaPct != null ? (
          <ContributionNumeric before={beforeAreaKm2} after={afterAreaKm2} deltaPct={deltaPct} />
        ) : (
          <ContributionFallback />
        )}

        {/* 기여 요약 통계 */}
        <View style={styles.statRow}>
          <StatCard value="✓" label="내 제보 반영" accent={color.searchInk} />
          <StatCard value={fs.citizens} label="함께 찾는 이웃" accent={color.searchInk} />
          <StatCard value={fs.validTips} label="유효 제보" accent={color.searchInk} />
        </View>

        <Text style={styles.anonNote} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          익명으로 전달됐어요 · 제보자의 위치와 신원은 공개되지 않아요
        </Text>
      </ScrollView>

      {/* 하단 액션 */}
      <View style={styles.footer}>
        <CTAButton label="확인" onPress={goSearch} accent={color.search} accessibilityHint="수색 지도로 돌아갑니다" />
        <View style={styles.gapSm} />
        <CTAButton label="추가로 본 게 있어요" onPress={goReportChat} variant="ghost" accessibilityHint="제보를 이어서 작성합니다" />
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
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.successWash },
  topBar: { flexDirection: 'row', justifyContent: 'flex-end', paddingHorizontal: space.md, paddingTop: space.sm },
  closeBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: color.surface,
  },
  closeIcon: { fontSize: 20, fontWeight: type.weight.bold, color: color.textBody, fontFamily: type.family },
  content: { paddingHorizontal: space.xl, paddingBottom: space.xl, gap: space.xl },

  hero: { alignItems: 'center', gap: space.md, paddingTop: space.md },
  badgeRing: {
    width: 96,
    height: 96,
    borderRadius: radius.pill,
    borderWidth: 4,
    borderColor: color.search,
    backgroundColor: color.searchWash,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeCore: {
    width: 66,
    height: 66,
    borderRadius: radius.pill,
    backgroundColor: color.walk,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeCheck: { fontSize: 38, color: '#FFFFFF', fontWeight: type.weight.black, fontFamily: type.family },
  heroTitle: { fontSize: 26, fontWeight: type.weight.black, color: color.text, fontFamily: type.family, textAlign: 'center' },
  heroSub: {
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
    textAlign: 'center',
    lineHeight: 24,
  },

  contribCard: {
    backgroundColor: color.surface,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.xl,
    gap: space.md,
    alignItems: 'center',
  },
  contribKicker: { fontSize: type.size.label, fontWeight: type.weight.bold, color: color.searchInk, fontFamily: type.family, alignSelf: 'center' },
  contribTitle: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: color.text, fontFamily: type.family, textAlign: 'center' },
  contribBody: {
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
  deltaBadgeText: { fontSize: type.size.label, fontWeight: type.weight.black, color: '#FFFFFF', fontFamily: type.family, fontVariant: ['tabular-nums'] },

  statRow: { flexDirection: 'row', justifyContent: 'space-between', gap: space.sm },

  anonNote: { fontSize: type.size.caption, fontWeight: type.weight.medium, color: color.textCaption, fontFamily: type.family, textAlign: 'center', lineHeight: 20 },

  footer: {
    paddingHorizontal: space.xl,
    paddingTop: space.md,
    paddingBottom: space.sm,
    borderTopWidth: 1,
    borderTopColor: color.border,
    backgroundColor: color.successWash,
  },
  gapSm: { height: space.sm },
  link: { alignSelf: 'center', paddingVertical: space.md, minHeight: 44, justifyContent: 'center' },
  linkText: { fontSize: type.size.label, fontWeight: type.weight.bold, color: color.searchInk, fontFamily: type.family, textDecorationLine: 'underline' },
  pressed: { opacity: 0.7 },
});
