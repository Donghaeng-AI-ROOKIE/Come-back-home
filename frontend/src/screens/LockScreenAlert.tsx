/**
 * 잠금화면 경보 takeover (spec §3.4, §4.1). Root fullScreenModal.
 * iOS 잠금화면 룩(lockscreen-content.dc.html 목업 이식): 다크 그라디언트 배경 +
 * 상단 자물쇠·날짜·큰 시계 + 프로스티드 알림 카드(accent rail·앱아이콘·"내 주변" 배지·
 * 인상착의 썸네일·요약·"지금 확인" 그라디언트 CTA) + 하단 손전등/카메라 힌트.
 *
 * 보정(§4.1): 목업의 앰버(--srch:#E8703F) accent → 전량 빨강(color.critical)로 승격.
 *   rail·앱아이콘·"내 주변" 배지·썸네일 보더·"지금 확인" CTA = color.critical→criticalInk 그라디언트.
 *   앰버는 긴급에 쓰지 않는다(첫 접점 = 최고 심각도).
 * 실종자 표기는 MISSING/MISSING_ANON 단일 소스만 사용(하드코딩 금지).
 * 진입 즉시 assertive 낭독(accessibilityLiveRegion). 뒤로가기/닫기 → dismiss.
 */
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { TextStyle } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Circle, Path } from 'react-native-svg';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { color, radius, space, type, HIT } from '../theme/tokens';
import { hexToRgba } from '../utils/color';
import { DEMO_CASE_ID, LAST_SEEN, MISSING, MISSING_ANON } from '../data/missing';
import { useAppModeStore } from '../store/appModeStore';
import { useEngagementStore } from '../store/engagementStore';
import { useMyLocation } from '../hooks/useMyLocation';
import { distanceM, formatDistance, formatWalkTime } from '../utils/geo';
import type { RootStackParamList } from '../navigation/types';

// 시계 자릿수 흔들림 방지 — 고정폭 숫자.
const TABULAR: TextStyle = { fontVariant: ['tabular-nums'] };
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'] as const;
// '내 주변' 근거 — 경보 메타데이터(거리/도보시간), 실종자 프로필 아님.
// 위치 권한 거부·측위 실패·정확도 미달 시의 물러섬 문구. 숫자를 못 믿을 때
// 대충 지어내지 않고 이걸 쓴다(utils/geo.ts 참고).
const NEAR_LABEL_FALLBACK = '내 주변';
// 익명 요약 라인 — 실명·의료정보 비노출, 단일 소스 조합(§5).
const SUMMARY_BASE = `${MISSING.area} 근처 · ${MISSING_ANON} · ${MISSING.appearance[0]}`;

type IconProps = { size: number; color: string };

function LockGlyph({ size, color: c }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path
        d="M12 2a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5Zm3 8H9V7a3 3 0 0 1 6 0Z"
        fill={c}
      />
    </Svg>
  );
}

// 앱 아이콘 글리프 — "돌아오길"의 되돌아오는 화살표.
function ReturnGlyph({ size, color: c }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round">
      <Path d="M4 12a8 8 0 1 1 3 6.2" />
      <Path d="M4 19v-4h4" />
    </Svg>
  );
}

function PinGlyph({ size, color: c }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
      <Path d="M12 21s6.5-5.6 6.5-10.5a6.5 6.5 0 0 0-13 0C5.5 15.4 12 21 12 21Z" />
      <Circle cx={12} cy={10.5} r={2.2} />
    </Svg>
  );
}

// 인상착의 실루엣(실사진 미노출, 개인정보 최소 카드).
function PersonGlyph({ size, color: c }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      <Circle cx={12} cy={8.5} r={3.6} />
      <Path d="M5 20c0-3.9 3.1-7 7-7s7 3.1 7 7" />
    </Svg>
  );
}

function ChevronGlyph({ size, color: c }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
      <Path d="M9 5l7 7-7 7" />
    </Svg>
  );
}

function CameraGlyph({ size, color: c }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round">
      <Path d="M9 3h6l1.2 2.4A2 2 0 0 0 18 6.5h1A2 2 0 0 1 21 8.5v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2h1a2 2 0 0 0 1.8-1.1Z" />
      <Circle cx={12} cy={13} r={3.5} />
    </Svg>
  );
}

export default function LockScreenAlert() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'LockScreenAlert'>>();
  const insets = useSafeAreaInsets();
  const caseId = route.params?.caseId ?? DEMO_CASE_ID;

  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const clock = `${now.getHours()}:${String(now.getMinutes()).padStart(2, '0')}`;
  const dateLine = `${now.getMonth() + 1}월 ${now.getDate()}일 ${WEEKDAYS[now.getDay()]}요일`;

  // 최종 목격 지점까지의 실거리. 좌표는 기기 밖으로 나가지 않는다(useMyLocation 참고).
  const { point: myPoint, accuracyM } = useMyLocation();
  const meters = myPoint ? distanceM(myPoint, LAST_SEEN) : null;
  const distanceLabel = meters == null ? null : formatDistance(meters, accuracyM);
  const walkLabel = meters == null ? null : formatWalkTime(meters, accuracyM);
  // 배지는 거리와 도보시간을 합쳐 쓰되, 못 믿는 값은 통째로 빼고 '내 주변'만 남긴다.
  const nearLabel = walkLabel ? `${NEAR_LABEL_FALLBACK} · ${walkLabel}` : NEAR_LABEL_FALLBACK;
  // 거리는 요약 라인에 실제로 노출한다 — "내 주변"이라는 주장의 근거를
  // 숫자로 보여주는 게 이 기능(#2)의 목적이다.
  const summaryLine = distanceLabel ? `${SUMMARY_BASE} · ${distanceLabel}` : SUMMARY_BASE;

  const dismissCase = useAppModeStore((s) => s.dismissCase);
  // 피로 신호 — 여러 번 끄면 일반 예측 알림은 관문을 안 세운다(alertBudget).
  const recordDismissed = useEngagementStore((st) => st.recordDismissed);
  const recordOpened = useEngagementStore((st) => st.recordOpened);

  // 잠금화면은 벨·알림 탭으로만 들어온다(관문은 경보 상세로 직행) — 즉 여기
  // 도달한 것 자체가 자발적 열람이다. 상세로 넘어갈 때 관심 신호로 센다.
  const openDetail = () => {
    recordOpened();
    navigation.navigate('AlertDetail', { caseId });
  };
  const dismiss = () => navigation.goBack();
  // "안볼래요" — 닫기(✕)와 구분되는 별도 의사표시. ✕는 이번만 넘김,
  // 이쪽은 이 사건의 재촉을 끈다. 경보 재도달·벨 진입 경로는 그대로 남는다.
  const dismissNudge = () => {
    dismissCase(caseId);
    recordDismissed();
    navigation.goBack();
  };

  // 낭독에서는 거리가 무엇까지의 거리인지 명시한다(화면은 폭이 좁아 생략).
  const a11yDistance = distanceLabel
    ? `최종 목격 장소까지 ${distanceLabel}, ${walkLabel}. `
    : '';
  const a11ySummary = `긴급 실종경보. 실종자가 이 근처에 계실 수 있어요. ${MISSING.area} 근처 ${MISSING_ANON}. ${MISSING.appearance[0]} 착용. ${a11yDistance}지금 확인 버튼을 누르면 상세를 볼 수 있어요.`;

  return (
    <View style={styles.root}>
      <StatusBar style="light" />

      {/* 다크 잠금화면 배경 그라디언트(토큰 다크 팔레트) */}
      <LinearGradient
        colors={[color.operatorSurfaceAlt, color.operatorSurface, color.operatorBg]}
        start={{ x: 0.1, y: 0 }}
        end={{ x: 0.9, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      {/* 상·하단 비네트 */}
      <LinearGradient
        pointerEvents="none"
        colors={[hexToRgba('#000000', 0.28), 'transparent', 'transparent', hexToRgba('#000000', 0.42)]}
        locations={[0, 0.22, 0.74, 1]}
        style={StyleSheet.absoluteFill}
      />

      <View
        style={[
          styles.content,
          { paddingTop: insets.top + space.sm, paddingBottom: insets.bottom + space.md },
        ]}
      >
        {/* 상단: 닫기 */}
        <View style={styles.topBar}>
          <Pressable
            onPress={dismiss}
            accessibilityRole="button"
            accessibilityLabel="잠금화면 닫기"
            hitSlop={space.md}
            style={styles.dismiss}
          >
            <Text style={styles.dismissGlyph} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              ✕
            </Text>
          </Pressable>
        </View>

        {/* 자물쇠 + 날짜 + 시계 */}
        <View style={styles.clockBlock}>
          <LockGlyph size={16} color={color.operatorText} />
          <Text style={styles.date} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {dateLine}
          </Text>
          <Text style={[styles.clock, TABULAR]} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {clock}
          </Text>
        </View>

        <View style={styles.spacer} />

        {/* 프로스티드 알림 카드 */}
        <View style={styles.card}>
          {/* accent rail — 빨강 승격(§4.1) */}
          <LinearGradient
            colors={[color.critical, color.criticalInk]}
            start={{ x: 0, y: 0.5 }}
            end={{ x: 1, y: 0.5 }}
            style={styles.rail}
          />

          <View style={styles.cardBody}>
            {/* 앱 행 */}
            <View style={styles.appRow}>
              <View style={styles.appIcon}>
                <LinearGradient
                  colors={[color.critical, color.criticalInk]}
                  start={{ x: 0.2, y: 0 }}
                  end={{ x: 0.8, y: 1 }}
                  style={StyleSheet.absoluteFill}
                />
                <ReturnGlyph size={17} color="#FFFFFF" />
              </View>
              <Text style={styles.appName} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                돌아오길
              </Text>
              <View style={styles.spacer} />
              <Text style={styles.appTime} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                지금
              </Text>
            </View>

            {/* 헤드라인 + 정보(단일 접근성 그룹, assertive) */}
            <View
              style={styles.headRow}
              accessible
              accessibilityRole="text"
              accessibilityLiveRegion="assertive"
              accessibilityLabel={a11ySummary}
            >
              <View style={styles.headText}>
                {/* "내 주변" 배지 — 빨강 승격(§4.1) */}
                <View style={styles.nearBadge}>
                  <PinGlyph size={13} color={color.criticalWash} />
                  <Text style={styles.nearBadgeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    {nearLabel}
                  </Text>
                </View>
                {/* 확정하지 않는다 — "있어요"는 실종자가 여기 있다고 단정하는 말인데
                    우리가 가진 건 확률분포다. 한 번 틀린 확정 표현이 나가면 이후
                    모든 경보의 신뢰가 같이 떨어진다. 백엔드 알림 문구도 같은 원칙. */}
                <Text style={styles.headline} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  실종자가 이 근처에 계실 수 있어요
                </Text>
              </View>

              {/* 인상착의 썸네일 — 보더 빨강 승격(§4.1) */}
              <View style={styles.thumb}>
                <LinearGradient
                  colors={[color.operatorSurfaceAlt, color.operatorBorder]}
                  start={{ x: 0.2, y: 0 }}
                  end={{ x: 0.8, y: 1 }}
                  style={StyleSheet.absoluteFill}
                />
                <PersonGlyph size={46} color={hexToRgba('#FFFFFF', 0.85)} />
              </View>
            </View>

            {/* 요약 라인 */}
            <Text style={styles.summary} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {summaryLine}
            </Text>

            {/* 주 행동 — "지금 확인" 빨강 그라디언트 CTA(§4.1) */}
            <Pressable
              onPress={openDetail}
              accessibilityRole="button"
              accessibilityLabel="지금 확인"
              accessibilityHint="실종 경보 상세 화면을 엽니다"
              style={({ pressed }) => [styles.cta, pressed && styles.pressed]}
            >
              <LinearGradient
                colors={[color.critical, color.criticalInk]}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={StyleSheet.absoluteFill}
              />
              <View style={styles.ctaRow}>
                <Text style={styles.ctaLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
                  지금 확인
                </Text>
                <ChevronGlyph size={19} color="#FFFFFF" />
              </View>
            </Pressable>

            {/* 부차 행동 — "안볼래요"(넛지 억제). 긴급 CTA와 경쟁하지 않도록 저강조 텍스트. */}
            <Pressable
              onPress={dismissNudge}
              accessibilityRole="button"
              accessibilityLabel="이 사건은 그만 볼래요"
              accessibilityHint="이 사건의 알림 배지를 끕니다. 경보 자체는 계속 도착할 수 있어요"
              hitSlop={space.sm}
              style={({ pressed }) => [styles.optOut, pressed && styles.pressed]}
            >
              <Text style={styles.optOutLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                이 사건은 그만 볼래요
              </Text>
            </Pressable>
          </View>
        </View>

        {/* 출처 안내 */}
        <Text style={styles.footHint} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          경찰 112 실종경보를 기반으로 내 주변에만 전송됐어요
        </Text>

        {/* 하단 손전등/카메라 힌트(장식 — 접근성 숨김) */}
        <View
          style={styles.hints}
          accessible={false}
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
        >
          <View style={styles.hintBtn}>
            <LockGlyph size={22} color={hexToRgba('#FFFFFF', 0.92)} />
          </View>
          <View style={styles.hintBtn}>
            <CameraGlyph size={23} color={hexToRgba('#FFFFFF', 0.92)} />
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.operatorBg },
  content: { flex: 1, paddingHorizontal: space.lg },
  topBar: { alignItems: 'flex-end' },
  dismiss: { width: HIT, height: HIT, alignItems: 'center', justifyContent: 'center' },
  dismissGlyph: {
    fontSize: 22,
    color: color.operatorTextSec,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
  },
  clockBlock: { alignItems: 'center', marginTop: space.lg },
  date: {
    marginTop: space.md,
    fontSize: 18,
    fontWeight: type.weight.medium,
    color: color.operatorText,
    fontFamily: type.family,
    letterSpacing: 0.2,
  },
  clock: {
    fontSize: 76,
    fontWeight: type.weight.medium,
    color: color.operatorText,
    fontFamily: type.family,
    letterSpacing: -1.5,
    lineHeight: 84,
  },
  spacer: { flex: 1 },

  card: {
    borderRadius: radius.xl,
    overflow: 'hidden',
    backgroundColor: hexToRgba(color.operatorSurface, 0.72),
    borderWidth: 1,
    borderColor: hexToRgba('#FFFFFF', 0.1),
    shadowColor: '#000000',
    shadowOpacity: 0.34,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 16 },
    elevation: 14,
  },
  rail: { height: 4, width: '100%' },
  cardBody: { paddingHorizontal: space.lg, paddingTop: space.md, paddingBottom: space.lg },

  appRow: { flexDirection: 'row', alignItems: 'center' },
  appIcon: {
    width: 28,
    height: 28,
    borderRadius: radius.sm,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: space.sm,
    shadowColor: color.critical,
    shadowOpacity: 0.5,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
  },
  appName: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.operatorText,
    fontFamily: type.family,
    letterSpacing: 0.2,
  },
  appTime: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.operatorTextSec,
    fontFamily: type.family,
  },

  headRow: { marginTop: space.md, flexDirection: 'row', alignItems: 'flex-start' },
  headText: { flex: 1, minWidth: 0, paddingRight: space.md },
  nearBadge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    backgroundColor: hexToRgba(color.critical, 0.26),
    borderWidth: 1,
    borderColor: hexToRgba(color.critical, 0.55),
    borderRadius: radius.pill,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
  },
  nearBadgeText: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.criticalWash,
    fontFamily: type.family,
    letterSpacing: 0.2,
  },
  headline: {
    marginTop: space.md,
    fontSize: 22,
    fontWeight: type.weight.black,
    color: color.operatorText,
    fontFamily: type.family,
    letterSpacing: -0.4,
    lineHeight: 29,
  },
  thumb: {
    width: 78,
    height: 78,
    borderRadius: radius.lg,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: hexToRgba(color.critical, 0.6),
    shadowColor: '#000000',
    shadowOpacity: 0.3,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 5 },
    elevation: 6,
  },
  summary: {
    marginTop: space.md,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: hexToRgba('#FFFFFF', 0.86),
    fontFamily: type.family,
    lineHeight: 22,
  },

  cta: {
    marginTop: space.lg,
    height: 56,
    borderRadius: radius.lg,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: color.critical,
    shadowOpacity: 0.45,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },
  ctaRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  ctaLabel: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: '#FFFFFF',
    fontFamily: type.family,
    letterSpacing: -0.2,
  },
  pressed: { opacity: 0.9 },

  optOut: {
    marginTop: space.sm,
    minHeight: HIT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  optOutLabel: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.operatorTextSec,
    fontFamily: type.family,
    letterSpacing: 0.2,
  },

  footHint: {
    marginTop: space.md,
    fontSize: type.size.caption,
    color: color.operatorTextSec,
    textAlign: 'center',
    fontFamily: type.family,
    lineHeight: 18,
  },

  hints: {
    marginTop: space.lg,
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: space.xl,
  },
  hintBtn: {
    width: HIT,
    height: HIT,
    borderRadius: HIT / 2,
    backgroundColor: hexToRgba('#FFFFFF', 0.14),
    alignItems: 'center',
    justifyContent: 'center',
  },
});
