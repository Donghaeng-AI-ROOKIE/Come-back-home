/**
 * AlertSyncScreen (spec §3.2, 보호자) — 경찰 실종경보 자동 연동 알림·전환 화면.
 *
 * 개념(핵심 리프레임): 보호자는 앱에서 수동으로 '실종 발동/신고'하지 않는다.
 * 이 화면은 경찰 실종경보가 자동 연동되어 산책→수색 모드로 전환되고 AI 동선예측이
 * 시작됨을 알린다. → hold-to-activate 없음. 발동/신고 등 보호자-행위 동사 없음.
 *
 * 디자인: DesignSync activate-content.dc.html의 카드 비주얼(보호대상 카드+체크 배지,
 * "자동 입력됨" 그린 배지, 최종 목격 정보 행, AI 예측 체크리스트)을 재현하되,
 * hold 버튼·오발동 경고·"실종 신고" 헤더는 제거하고 아래 보정으로 대체한다.
 *
 * 색 위계(spec §4.1): 긴급 헤더 = 빨강 color.critical. 전환/수색 진행 chrome(전환 배너·
 * CTA·미니 아이콘)만 앰버 color.search. 앰버를 긴급에 쓰지 않는다.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Circle, Path } from 'react-native-svg';
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

// 긴급(빨강) 배경 위 텍스트 — CTAButton과 동일한 흰색 온-컬러 관용.
const ON_RED = '#FFFFFF';
const ON_RED_SUB = 'rgba(255,255,255,0.9)';

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

// ── 인라인 SVG 아이콘 (mockup 아이콘 재현) ─────────────
type IconProps = { size?: number; color: string };

function BackArrowIcon({ size = 24, color: c }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path d="M15 5l-7 7 7 7" stroke={c} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

function BellIcon({ size = 15, color: c }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9Z" stroke={c} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M13.7 21a2 2 0 0 1-3.4 0" stroke={c} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

function CheckIcon({ size = 14, color: c }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path d="M5 12l4.5 4.5L19 7" stroke={c} strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

function PinIcon({ size = 22, color: c }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 21s6.5-5.6 6.5-10.5a6.5 6.5 0 0 0-13 0C5.5 15.4 12 21 12 21Z"
        stroke={c}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Circle cx={12} cy={10.5} r={2.3} stroke={c} strokeWidth={2} fill="none" />
    </Svg>
  );
}

function ClockIcon({ size = 22, color: c }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx={12} cy={12} r={8.5} stroke={c} strokeWidth={2} fill="none" />
      <Path d="M12 7.5V12l3 2" stroke={c} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

// AI 예측 예고 체크리스트 (mockup 로딩 화면의 3단계 재현).
const AI_STEPS: ReadonlyArray<{ text: string; done: boolean }> = [
  { text: '자주 다니시던 경로 확인', done: true },
  { text: '예상 이동 반경 계산', done: true },
  { text: '주변 이웃에게 맞춤 경보 발송 중', done: false },
];

export default function AlertSyncScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const enterSearch = useAppModeStore((s) => s.enterSearch);
  const profile = useMissingPersonStore((s) => s.profile);

  const issuedText = formatIssued(buildAlert().issuedAt);

  // profile.lastSeen("정릉동 주민센터, 오후 3시 10분경")을 위치/시각으로 분해 — 단일 소스.
  const lsParts = profile.lastSeen.split(',');
  const lastSeenPlace = (lsParts[0] ?? profile.lastSeen).trim();
  const lastSeenTime = lsParts.length > 1 ? lsParts.slice(1).join(',').trim() : '시각 확인 중';

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

  const goSearch = () => navigation.navigate('CitizenTabs', { screen: 'Alerts' });

  // 무조작 시 자동으로 수색 현황(Search) 진입.
  useEffect(() => {
    if (remaining === 0) {
      navigation.navigate('CitizenTabs', { screen: 'Alerts' });
    }
  }, [remaining, navigation]);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right', 'bottom']}>
      <StatusBar style="dark" />

      {/* 배경: 상단 앰버 워시 → 표면 (mockup의 산책→수색 전환 워시 재현) */}
      <LinearGradient
        colors={[color.searchWash, color.surface]}
        start={{ x: 0.5, y: 0 }}
        end={{ x: 0.5, y: 0.55 }}
        style={StyleSheet.absoluteFill}
        pointerEvents="none"
      />

      {/* 1. 긴급 헤더 (빨강 배경/보더) — 접수시각 + 뒤로 */}
      <View style={styles.emergencyHeader} accessibilityLiveRegion="assertive">
        <View style={styles.headerTopRow}>
          <Pressable
            onPress={() => navigation.goBack()}
            accessibilityRole="button"
            accessibilityLabel="뒤로"
            accessibilityHint="이전 화면으로 돌아갑니다. 경보는 배너로 남아요."
            hitSlop={8}
            style={({ pressed }) => [styles.backBtn, pressed && styles.pressed]}
          >
            <BackArrowIcon color={ON_RED} />
          </Pressable>

          <View style={styles.emBadge}>
            <BellIcon color={ON_RED} />
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
        {/* 2. 전환 히어로 배너 (앰버) — mockup 헤드라인 재현 */}
        <View
          style={styles.banner}
          accessibilityRole="text"
          accessibilityLabel="산책 모드를 잠시 멈추고, 온 동네가 함께 찾을게요. 주변 이웃들에게 맞춤 경보가 전해지고 앱이 수색 모드로 전환돼요."
        >
          <View style={styles.bannerDot} />
          <View style={styles.bannerText}>
            <Text style={styles.bannerTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              산책 모드를 잠시 멈추고,{'\n'}온 동네가 함께 찾을게요
            </Text>
            <Text style={styles.bannerSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              주변 이웃들에게 맞춤 경보가 전해지고, 앱이 수색 모드로 전환돼요.
            </Text>
          </View>
        </View>

        {/* 3. 보호대상 — MissingPersonCard(full)+칩 + 그린 체크 배지(mockup) */}
        <Text style={styles.sectionLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          보호대상
        </Text>
        <View style={styles.personWrap}>
          <MissingPersonCard variant="full" showAppearanceChips />
          <View style={styles.personCheck} importantForAccessibility="no-hide-descendants">
            <CheckIcon size={16} color={ON_RED} />
          </View>
        </View>
        <Text style={styles.subCaption} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          {profile.rel} · 사전등록 완료
        </Text>

        {/* 4. 최종 목격 정보 — 헤더행(라벨 + 자동 입력됨 배지) + 정보행 + 미니 지도 */}
        <View style={styles.seenHeadRow}>
          <Text style={styles.sectionLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            최종 목격 정보
          </Text>
          <View style={styles.autoBadge}>
            <CheckIcon size={12} color={color.walkInk} />
            <Text style={styles.autoBadgeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              자동 입력됨
            </Text>
          </View>
        </View>

        <View style={styles.card}>
          <View
            style={styles.infoRow}
            accessible
            accessibilityLabel={`최종 목격 위치, ${lastSeenPlace}`}
          >
            <PinIcon color={color.searchInk} />
            <View style={styles.infoCol}>
              <Text style={styles.infoCap} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                최종 목격 위치
              </Text>
              <Text style={styles.infoVal} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                {lastSeenPlace}
              </Text>
            </View>
          </View>

          <View style={styles.divider} />

          <View
            style={styles.infoRow}
            accessible
            accessibilityLabel={`마지막으로 본 시각, ${lastSeenTime}`}
          >
            <ClockIcon color={color.searchInk} />
            <View style={styles.infoCol}>
              <Text style={styles.infoCap} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                마지막으로 본 시각
              </Text>
              <Text style={styles.infoVal} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                {lastSeenTime}
              </Text>
            </View>
          </View>

          <View style={styles.miniMapWrap}>
            <BaseMap
              style={styles.miniMap}
              scrollEnabled={false}
              accessibilityLabel={`최종 목격 위치 지도. ${lastSeenPlace}. ${profile.area} 인근.`}
            >
              <MapPin kind="lastSeen" coordinate={LAST_SEEN} title="최종 목격" description={lastSeenPlace} />
            </BaseMap>
          </View>

          <Text style={styles.caption} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            경찰 데이터와 사전등록 동선을 자동으로 불러왔어요.
          </Text>
        </View>

        {/* 5. AI 예측 예고 — mockup 로딩 화면의 예측 체크리스트 재현 */}
        <View style={styles.card}>
          <Text style={styles.cardTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            AI 동선 예측
          </Text>
          <Text style={styles.aiHeadline} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            AI가 동선을 예측하고 있어요
          </Text>
          <Text style={styles.cardBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {profile.name} 님이 자주 다니시던 길과 최근 산책 기록을 분석하고 있어요.
          </Text>

          <View
            style={styles.aiList}
            accessible
            accessibilityLabel="AI 예측 준비: 자주 다니시던 경로 확인 완료, 예상 이동 반경 계산 완료, 주변 이웃에게 맞춤 경보 발송 중."
          >
            {AI_STEPS.map((step) => (
              <View key={step.text} style={styles.aiItem}>
                <View style={styles.aiIcon}>
                  {step.done ? (
                    <CheckIcon size={16} color={color.walk} />
                  ) : (
                    <ActivityIndicator size="small" color={color.search} />
                  )}
                </View>
                <Text
                  style={[styles.aiItemText, !step.done && styles.aiItemPending]}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  {step.text}
                </Text>
              </View>
            ))}
          </View>
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

  // 긴급 헤더 (빨강, 상단 풀블리드 배너)
  emergencyHeader: {
    backgroundColor: color.critical,
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.lg,
    borderBottomLeftRadius: radius.xl,
    borderBottomRightRadius: radius.xl,
    shadowColor: color.criticalInk,
    shadowOpacity: 0.28,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 8,
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
  emBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    backgroundColor: color.criticalInk,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
  emBadgeText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.black,
    color: ON_RED,
    fontFamily: type.family,
  },
  emTitle: {
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    color: ON_RED,
    fontFamily: type.family,
    letterSpacing: -0.3,
  },
  emSub: {
    marginTop: space.xs,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: ON_RED_SUB,
    fontFamily: type.family,
  },

  scroll: {
    paddingHorizontal: space.lg,
    paddingTop: space.lg,
    paddingBottom: space.xl,
    gap: space.md,
  },

  // 전환 히어로 배너 (앰버)
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
    marginTop: 7,
    marginRight: space.md,
  },
  bannerText: { flex: 1 },
  bannerTitle: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.searchInk,
    fontFamily: type.family,
    lineHeight: 26,
    letterSpacing: -0.2,
  },
  bannerSub: {
    marginTop: space.sm,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.searchInk,
    fontFamily: type.family,
    lineHeight: 21,
  },

  sectionLabel: {
    marginTop: space.sm,
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: color.textCaption,
    fontFamily: type.family,
    letterSpacing: 0.2,
  },
  subCaption: {
    marginTop: -space.xs,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
  },

  // 보호대상 카드 + 그린 체크 배지
  personWrap: { position: 'relative' },
  personCheck: {
    position: 'absolute',
    top: space.md,
    right: space.md,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: color.walk,
    alignItems: 'center',
    justifyContent: 'center',
  },

  // 최종 목격 정보 헤더행
  seenHeadRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  autoBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
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

  // 일반 카드
  card: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    shadowColor: color.text,
    shadowOpacity: 0.05,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  cardTitle: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },
  aiHeadline: {
    marginTop: space.sm,
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.searchInk,
    fontFamily: type.family,
    letterSpacing: -0.2,
  },
  cardBody: {
    marginTop: space.xs,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
    lineHeight: 22,
  },
  caption: {
    marginTop: space.md,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
    lineHeight: 19,
  },

  // 최종 목격 정보 행
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.sm,
  },
  infoCol: { flex: 1, marginLeft: space.md },
  infoCap: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
  },
  infoVal: {
    marginTop: 2,
    fontSize: type.size.body,
    fontWeight: type.weight.bold,
    color: color.text,
    fontFamily: type.family,
  },
  divider: { height: 1, backgroundColor: color.border },

  miniMapWrap: {
    marginTop: space.md,
    borderRadius: radius.lg,
    overflow: 'hidden',
  },
  miniMap: { height: 180, minHeight: 180 },

  // AI 예측 예고 체크리스트
  aiList: { marginTop: space.md, gap: space.md },
  aiItem: { flexDirection: 'row', alignItems: 'center' },
  aiIcon: {
    width: 22,
    height: 22,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: space.md,
  },
  aiItemText: {
    flex: 1,
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.text,
    fontFamily: type.family,
  },
  aiItemPending: { color: color.searchInk },

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
