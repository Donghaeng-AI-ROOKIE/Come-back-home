/**
 * 경보 상세 (spec §3.4, §4.1). Root card, 라이트(color.surface).
 * 진입 시 수색 모드 진입(enterSearch critical) → 골든타임 카운트다운 기준 설정.
 * 긴급 배지 = criticalWash 배경 + criticalInk 텍스트(§4.1). 앰버 금지.
 * 실종자 카드(익명) + GoldenTimeChip(critical) + 회상 유도 카피.
 * '봤어요'(danger) → ReportChat, '못 봤어요'(ghost) → goBack.
 */
import { useEffect } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { color, radius, space, type, HIT } from '../theme/tokens';
import CTAButton from '../components/CTAButton';
import MissingPersonCard from '../components/MissingPersonCard';
import GoldenTimeChip from '../components/GoldenTimeChip';
import { useAppModeStore } from '../store/appModeStore';
import { useMissingPersonStore } from '../store/missingPersonStore';
import { DEMO_CASE_ID } from '../data/missing';
import type { RootStackParamList } from '../navigation/types';

export default function AlertDetailScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'AlertDetail'>>();
  const insets = useSafeAreaInsets();
  const enterSearch = useAppModeStore((s) => s.enterSearch);
  const lastSeen = useMissingPersonStore((s) => s.profile.lastSeen);
  const caseId = route.params?.caseId ?? DEMO_CASE_ID;

  // 진입 시 수색 모드(긴급) 보장 — enterSearch는 enteredSearchAt이 있으면 유지(멱등).
  useEffect(() => {
    enterSearch(DEMO_CASE_ID, 'critical');
  }, [enterSearch]);

  const onSeen = () => navigation.navigate('ReportChat', { caseId });
  const onNotSeen = () => navigation.goBack();

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <StatusBar style="dark" />

      {/* 헤더: 닫기 + 실종 경보 배지 */}
      <View style={styles.header}>
        <Pressable
          onPress={onNotSeen}
          accessibilityRole="button"
          accessibilityLabel="경보 닫기"
          hitSlop={space.sm}
          style={styles.back}
        >
          <Text style={styles.backGlyph} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            ✕
          </Text>
        </Pressable>

        <View style={styles.badge} accessible accessibilityRole="text" accessibilityLabel="실종 경보">
          <View style={styles.badgeDot} />
          <Text style={styles.badgeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            실종 경보
          </Text>
        </View>

        <View style={styles.headerSpacer} />
      </View>

      <ScrollView
        contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + space.xl }]}
        showsVerticalScrollIndicator={false}
      >
        <GoldenTimeChip emphasis="critical" />

        <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          혹시 이 어르신을 보셨나요?
        </Text>
        <Text style={styles.lede} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          내 주변에서 실종경보가 발령됐어요. 잠깐이라도 비슷한 분을 보셨다면 알려주세요.
        </Text>

        <View style={styles.cardGap}>
          <MissingPersonCard variant="full" anon showAppearanceChips />
        </View>

        {/* 최종 목격 — 구역·시간만(의료정보 비노출). 단일 소스 profile.lastSeen */}
        <View style={styles.lastSeenCard} accessible accessibilityLabel={`최종 목격 ${lastSeen}`}>
          <Text style={styles.lastSeenLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            최종 목격
          </Text>
          <Text style={styles.lastSeenValue} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {lastSeen}
          </Text>
        </View>

        <Text style={styles.anonNote} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          제보는 익명으로 전달되고, 내 위치·신원은 공개되지 않아요.
        </Text>
      </ScrollView>

      {/* 하단 액션바 */}
      <View style={[styles.actions, { paddingBottom: insets.bottom + space.md }]}>
        <CTAButton
          label="봤어요"
          onPress={onSeen}
          variant="danger"
          accessibilityHint="목격 제보 대화를 시작합니다"
        />
        <View style={styles.actionGap} />
        <CTAButton
          label="못 봤어요"
          onPress={onNotSeen}
          variant="ghost"
          accessibilityHint="경보를 닫고 이전 화면으로 돌아갑니다"
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.surface },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.xl,
    paddingVertical: space.md,
  },
  back: { width: HIT, height: HIT, alignItems: 'center', justifyContent: 'center' },
  backGlyph: { fontSize: 22, color: color.textBody, fontWeight: type.weight.bold, fontFamily: type.family },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: color.criticalWash,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
  },
  badgeDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: color.critical, marginRight: space.sm },
  badgeText: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.criticalInk,
    fontFamily: type.family,
  },
  headerSpacer: { width: HIT },
  body: { paddingHorizontal: space.xl, paddingTop: space.md },
  title: {
    marginTop: space.lg,
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    lineHeight: 28,
  },
  lede: {
    marginTop: space.sm,
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
    lineHeight: 24,
  },
  cardGap: { marginTop: space.lg },
  lastSeenCard: {
    marginTop: space.lg,
    backgroundColor: color.surfaceAlt,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
  },
  lastSeenLabel: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
  },
  lastSeenValue: {
    marginTop: space.xs,
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: color.text,
    fontFamily: type.family,
    lineHeight: 24,
  },
  anonNote: {
    marginTop: space.lg,
    fontSize: type.size.caption,
    color: color.textCaption,
    fontFamily: type.family,
    lineHeight: 20,
  },
  actions: {
    paddingHorizontal: space.xl,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: color.border,
    backgroundColor: color.surface,
  },
  actionGap: { height: space.md },
});
