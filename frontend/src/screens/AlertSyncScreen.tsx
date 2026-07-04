/**
 * AlertSyncScreen (spec §3.2, 보호자) — 경찰 실종경보 자동 연동 알림·전환 화면.
 *
 * 개념: 보호자는 앱에서 수동으로 '실종 발동'하지 않는다. 이 화면은 경찰 실종경보가
 * 자동 연동되어 산책→수색 모드로 전환되고 AI 동선예측이 시작됨을 알린다.
 * → hold-to-activate 없음. 발동/신고 등 보호자-행위 동사 없음.
 *
 * 색 위계(spec §4.1): 긴급 헤더 = 빨강 color.critical. 수색 진행 chrome(전환 배너·CTA)
 * 만 앰버 color.search. 앰버를 긴급에 쓰지 않는다.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import dayjs from 'dayjs';

import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import { DEMO_CASE_ID, LAST_SEEN } from '../data/missing';
import { buildAlert } from '../data/mock';
import { useAppModeStore } from '../store/appModeStore';
import { useMissingPersonStore } from '../store/missingPersonStore';
import CTAButton from '../components/CTAButton';
import MissingPersonCard from '../components/MissingPersonCard';
import BaseMap from '../components/BaseMap';
import MapPin from '../components/MapPin';

// 긴급(빨강) 배경 위 텍스트 — CTAButton과 동일하게 흰색 계열 사용.
const ON_RED = '#FFFFFF';
const ON_RED_SUB = 'rgba(255,255,255,0.88)';

// 무조작 시 자동으로 수색 현황으로 넘어가는 카운트다운(초).
const AUTO_SECONDS = 15;

/** buildAlert().issuedAt(ISO)을 한국어 접수시각 문구로. dayjs로 시/분 파싱. */
function formatIssued(iso: string): string {
  const d = dayjs(iso);
  const h24 = d.hour();
  const ampm = h24 < 12 ? '오전' : '오후';
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  const mm = d.minute().toString().padStart(2, '0');
  return `${ampm} ${h12}시 ${mm}분 접수`;
}

export default function AlertSyncScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const enterSearch = useAppModeStore((s) => s.enterSearch);
  const profile = useMissingPersonStore((s) => s.profile);

  const issuedText = formatIssued(buildAlert().issuedAt);

  // 마운트 시 수색 모드 진입(긴급) — 경찰경보 자동 연동 부수효과.
  useEffect(() => {
    enterSearch(DEMO_CASE_ID, 'critical');
  }, [enterSearch]);

  // 자동 전환 카운트다운(경량 setInterval, JS state).
  const [remaining, setRemaining] = useState(AUTO_SECONDS);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          return 0;
        }
        return r - 1;
      });
    }, 1000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const goSearch = () => navigation.navigate('CitizenTabs', { screen: 'Search' });

  // 무조작 시 자동으로 수색 현황(Search) 진입.
  useEffect(() => {
    if (remaining === 0) {
      navigation.navigate('CitizenTabs', { screen: 'Search' });
    }
  }, [remaining, navigation]);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right', 'bottom']}>
      <StatusBar style="dark" />

      {/* 1. 긴급 헤더 (빨강 배경/보더) — 접수시각 + 뒤로 */}
      <View
        style={styles.emergencyHeader}
        accessibilityLiveRegion="assertive"
      >
        <View style={styles.headerTopRow}>
          <Pressable
            onPress={() => navigation.goBack()}
            accessibilityRole="button"
            accessibilityLabel="뒤로"
            accessibilityHint="이전 화면으로 돌아갑니다. 경보는 배너로 남아요."
            hitSlop={8}
            style={({ pressed }) => [styles.backBtn, pressed && styles.pressed]}
          >
            <Text style={styles.backGlyph} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              ←
            </Text>
          </Pressable>

          <View style={styles.emBadge}>
            <Text style={styles.emBadgeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              긴급
            </Text>
          </View>
        </View>

        <Text style={styles.emTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          경찰 실종경보 연동됨 · 자동 전환
        </Text>
        <Text style={styles.emSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          112 경찰 실종경보 기반 · {issuedText}
        </Text>
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* 2. 전환 배너 (앰버) */}
        <View style={styles.banner} accessibilityRole="text" accessibilityLabel="온 동네가 함께 찾을게요. 산책 모드를 잠시 멈추고 수색 모드로 전환 중이에요.">
          <View style={styles.bannerDot} />
          <View style={styles.bannerText}>
            <Text style={styles.bannerTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              온 동네가 함께 찾을게요 · 산책 모드를 잠시 멈춰요
            </Text>
            <Text style={styles.bannerSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              산책 모드 → 수색 모드 전환 중 · 앱이 대신 이웃에게 알리고 있어요
            </Text>
          </View>
        </View>

        {/* 3. 보호 대상 카드 */}
        <Text style={styles.sectionLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          보호 대상
        </Text>
        <MissingPersonCard variant="full" showAppearanceChips />
        <Text style={styles.subCaption} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          {profile.rel} · 사전등록 완료
        </Text>

        {/* 4. 최종 목격 카드 (자동 프리필 + 미니 지도) */}
        <View style={styles.card}>
          <View style={styles.cardHeadRow}>
            <Text style={styles.cardTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              최종 목격
            </Text>
            <View style={styles.autoBadge}>
              <Text style={styles.autoBadgeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                자동 입력됨
              </Text>
            </View>
          </View>

          <Text style={styles.cardBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {profile.lastSeen}
          </Text>

          <View style={styles.miniMapWrap}>
            <BaseMap
              style={styles.miniMap}
              scrollEnabled={false}
              accessibilityLabel={`최종 목격 위치 지도. ${profile.lastSeen}. ${profile.area} 인근.`}
            >
              <MapPin kind="lastSeen" coordinate={LAST_SEEN} title="최종 목격" description={profile.lastSeen} />
            </BaseMap>
          </View>

          <Text style={styles.caption} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            경찰 데이터와 사전등록 동선을 자동으로 불러왔어요.
          </Text>
        </View>

        {/* 5. AI 예측 예고 */}
        <View style={styles.card}>
          <Text style={styles.cardTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            AI 예측 예고
          </Text>
          <Text style={styles.cardBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            자주 다니시던 길과 최근 산책 기록으로 이동 동선을 예측합니다.
          </Text>
          <Text style={styles.caption} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            경로 확인 · 반경 계산 · 이웃 맞춤 경보를 준비하고 있어요.
          </Text>
        </View>
      </ScrollView>

      {/* 6. 하단 액션바 — 단일 주 CTA(앰버) + 보조 고스트 + 자동전환 카운트다운 */}
      <View style={styles.bottomBar}>
        <Text
          style={styles.countdown}
          allowFontScaling
          maxFontSizeMultiplier={type.maxScale}
          accessibilityLabel={`${remaining}초 후 수색 현황으로 자동 전환됩니다.`}
        >
          {remaining}초 후 수색 현황으로 자동 전환돼요
        </Text>
        <CTAButton
          label="수색 현황 보기"
          onPress={goSearch}
          accent={color.search}
          accessibilityHint="AI 예측 지도와 수색 현황으로 이동합니다."
        />
        <View style={styles.gap} />
        <CTAButton
          label="나중에"
          onPress={() => navigation.goBack()}
          variant="ghost"
          accessibilityHint="지금은 넘어갑니다. 경보는 배너로 남아요."
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surface },

  // 긴급 헤더 (빨강)
  emergencyHeader: {
    backgroundColor: color.critical,
    borderWidth: 1,
    borderColor: color.criticalInk,
    marginHorizontal: space.lg,
    marginTop: space.sm,
    borderRadius: radius.lg,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  headerTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.sm,
  },
  backBtn: {
    width: 44,
    height: 44,
    marginLeft: -space.sm,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.pill,
  },
  backGlyph: { fontSize: 24, fontWeight: type.weight.bold, color: ON_RED, fontFamily: type.family },
  emBadge: {
    backgroundColor: color.criticalInk,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
  emBadgeText: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: ON_RED,
    fontFamily: type.family,
  },
  emTitle: {
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    color: ON_RED,
    fontFamily: type.family,
  },
  emSub: {
    marginTop: space.xs,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: ON_RED_SUB,
    fontFamily: type.family,
  },

  scroll: { paddingHorizontal: space.lg, paddingTop: space.lg, paddingBottom: space.xl, gap: space.md },

  // 전환 배너 (앰버)
  banner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: color.searchWash,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.search,
    padding: space.lg,
  },
  bannerDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: color.search,
    marginTop: 5,
    marginRight: space.md,
  },
  bannerText: { flex: 1 },
  bannerTitle: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.searchInk,
    fontFamily: type.family,
  },
  bannerSub: {
    marginTop: space.xs,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.searchInk,
    fontFamily: type.family,
    lineHeight: 19,
  },

  sectionLabel: {
    marginTop: space.sm,
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
  },
  subCaption: {
    marginTop: -space.xs,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
  },

  // 일반 카드
  card: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
  },
  cardHeadRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  cardTitle: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },
  cardBody: {
    marginTop: space.sm,
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
    lineHeight: 23,
  },
  caption: {
    marginTop: space.sm,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
    lineHeight: 19,
  },

  // 자동 입력됨 배지 (그린)
  autoBadge: {
    backgroundColor: color.walkWash,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
  autoBadgeText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: color.walkInk,
    fontFamily: type.family,
  },

  miniMapWrap: { marginTop: space.md, borderRadius: radius.lg, overflow: 'hidden' },
  miniMap: { height: 190, minHeight: 190 },

  // 하단 액션바
  bottomBar: {
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.sm,
    borderTopWidth: 1,
    borderTopColor: color.border,
    backgroundColor: color.surface,
  },
  countdown: {
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: color.searchInk,
    fontFamily: type.family,
    textAlign: 'center',
    marginBottom: space.sm,
  },
  gap: { height: space.sm },
  pressed: { opacity: 0.6 },
});
