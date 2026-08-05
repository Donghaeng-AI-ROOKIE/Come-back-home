/**
 * 경보 상세 (spec §3.4, §4.1). Root card, 라이트(color.surface).
 * DesignSync alert-content.dc.html 목업을 RN으로 이식 — 대표 실루엣 이미지, 최종 목격 카드,
 * 실지도(§4.5 BaseMap) 프레이밍, 회상 유도 카드, 그라디언트 하단 버튼.
 *
 * §4.1 색 교정(목업 앰버 → 빨강): "실종 경보" 배지(criticalWash/criticalInk),
 * 골든타임(critical), "봤어요" 주 버튼 빨강 그라디언트(critical→criticalInk), 지도 배지·예상반경 빨강.
 * 진입 시 enterSearch(critical)로 골든타임 카운트다운 기준 설정.
 * 실종자 = MissingPersonCard(full, anon) 단일 소스, GoldenTimeChip(critical).
 * '봤어요' → ReportChat, '못 봤어요' → goBack.
 */
import { useEffect } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Path, Circle as SvgCircle } from 'react-native-svg';
import { Circle } from 'react-native-maps';
import { color, radius, space, type, HIT } from '../theme/tokens';
import CTAButton from '../components/CTAButton';
import MissingPersonCard from '../components/MissingPersonCard';
import GoldenTimeChip from '../components/GoldenTimeChip';
import PresenceBadge from '../components/PresenceBadge';
import BaseMap from '../components/BaseMap';
import MapPin from '../components/MapPin';
import { useAppModeStore } from '../store/appModeStore';
import { useEngagementStore } from '../store/engagementStore';
import { useMissingPersonStore } from '../store/missingPersonStore';
import { useMyLocation } from '../hooks/useMyLocation';
import { useAreaStatus } from '../hooks/useAreaStatus';
import { DEMO_CASE_ID, LAST_SEEN } from '../data/missing';
import { alertToView, toCitizenView } from '../data/missingView';
import { useGoldenTime, usePresenceCount, useActiveAlerts } from '../hooks/queries';
import { hexToRgba, toLatLng } from '../utils/color';
import type { RootStackParamList } from '../navigation/types';

// 온-컬러(빨강 필 위) 텍스트 — GoldenTimeChip/CTAButton과 동일 idiom.
const ON_CRITICAL = '#FFFFFF';
// "봤어요" 빨강 그라디언트(§4.1: #D62839 계열) — 토큰 critical→criticalInk.
const SEEN_GRADIENT = [color.critical, color.criticalInk] as const;
// 대표 실루엣 배경 — 사진 없음 플레이스홀더(중립 그레이, 심각도색 아님).
const SILHOUETTE_GRADIENT = [color.textBody, color.text] as const;

// 최종 목격 = 예상 이동 반경 중심.
const MAP_REGION = {
  latitude: LAST_SEEN.lat,
  longitude: LAST_SEEN.lng,
  latitudeDelta: 0.012,
  longitudeDelta: 0.012,
};
const PREDICT_RADIUS_M = 260;

export default function AlertDetailScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'AlertDetail'>>();
  const insets = useSafeAreaInsets();
  const enterSearch = useAppModeStore((s) => s.enterSearch);
  const profile = useMissingPersonStore((s) => s.profile);
  const caseId = route.params?.caseId ?? DEMO_CASE_ID;
  // 서버 경보가 진실이다 — 스토어는 목업 상수라 실제 신고와 나이·인상착의가 다르다.
  const { data: liveAlerts } = useActiveAlerts();
  const liveAlert = liveAlerts?.find((a) => a.caseId === caseId) ?? liveAlerts?.[0];
  // 실제 알림이 있으면 그쪽이 진실이다 — 목업 profile 은 "78세 어르신"처럼 값이
  // 박혀 있어 82세 신고에도 78세가 뜬다(2026-08-05 실측).
  //
  // 다만 **실데이터 경로에는 아직 실명이 없다.** #125 는 시민 화면 실명 노출을
  // 허용했지만(경찰 실종경보 베이스라인 + 호명 반응), 알림 payload 는 익명화
  // 원칙으로 이름을 빼고 내려온다. 그래서 지금은 실데이터면 이름 없이, 목업이면
  // toCitizenView 로 이름이 나온다 — 서버가 시민용 이름을 내려주게 하는 것은 후속.
  const view = liveAlert ? alertToView(liveAlert) : toCitizenView(profile);

  // 진입 시 수색 모드(긴급) 보장 — enterSearch는 enteredSearchAt이 있으면 유지(멱등).
  useEffect(() => {
    enterSearch(DEMO_CASE_ID, 'critical');
  }, [enterSearch]);

  // 표시 컴포넌트에 넘길 데이터는 화면이 가져온다 — 컴포넌트를 갈아끼워도
  // 데이터 연결이 남아 있도록(디자인 교체 대비).
  const goldenTime = useGoldenTime();
  const watching = usePresenceCount(caseId);

  // 내 위치 — 지도의 OS 마커와 거리 문구에 함께 쓴다. 좌표는 기기 밖으로 나가지 않는다.
  const { point: myPoint, status: locStatus } = useMyLocation();
  const located = locStatus === 'granted' && myPoint != null;
  // 거리(m·분) 대신 "예측 구역 안/밖 + 확률 등급" — 근거는 utils/areaStatus.ts.
  const area = useAreaStatus(caseId);

  // 지도는 시각 정보라 스크린리더에는 거리를 말로 대신 준다.
  const mapA11yLabel = [
    `내 주변 지도. ${profile.area} 최종 목격 위치와 예상 이동 반경을 표시합니다.`,
    located ? '내 위치도 함께 표시됩니다.' : '위치 권한이 없어 내 위치는 표시되지 않습니다.',
    area.label,
  ]
    .filter(Boolean)
    .join(' ');

  // 진입 관문으로 떠 있는가 = 뒤로 갈 곳이 없는가. 관문일 때 이 화면이 스택의
  // 루트라 goBack 이 아무 일도 안 하므로, 통과 경로를 명시적으로 만들어야 한다.
  const isGate = !navigation.canGoBack();
  const dismissCase = useAppModeStore((s) => s.dismissCase);
  // 피로 신호 — 여러 번 끄면 일반 예측 알림은 관문을 안 세운다(alertBudget).
  const recordDismissed = useEngagementStore((st) => st.recordDismissed);
  const leaveGate = () => navigation.reset({ index: 0, routes: [{ name: 'CitizenTabs' }] });

  const onSeen = () => navigation.navigate('ReportChat', { caseId: DEMO_CASE_ID });

  // "못 봤어요" = 목격 여부에 답한 것일 뿐 "그만 보겠다"가 아니다. 억제로 치지
  // 않으므로 앱을 다시 켜면 관문이 또 선다 — 넛지를 유지하는 압력이 이쪽이다.
  const onNotSeen = () => (isGate ? leaveGate() : navigation.goBack());

  // "그만 볼래요" = 명시적 영구 억제. 관문을 통과하는 유일한 '끄는' 경로.
  const onDismissCase = () => {
    dismissCase(caseId);
    recordDismissed();
    if (isGate) leaveGate();
    else navigation.goBack();
  };

  // 문구도 실데이터에서 만든다 — 인상착의가 비면 그 대목을 통째로 뺀다.
  // "  차림의" 처럼 빈 자리가 남으면 신뢰를 잃는다.
  const recallCopy = view.appearance.length
    ? `지난 한 시간, ${view.meta}에서 ${view.appearance.join(', ')} 차림의 어르신을 보셨다면 작은 기억도 큰 도움이 돼요.`
    : `지난 한 시간, ${view.meta}에서 홀로 걷고 계신 어르신을 보셨다면 작은 기억도 큰 도움이 돼요.`;

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <StatusBar style="dark" />

      {/* 헤더: 뒤로 + 타이틀 + 실종 경보 배지(§4.1 빨강) */}
      <View style={styles.header}>
        {/* 관문일 때는 뒤로 화살표를 감춘다 — 돌아갈 곳이 없어 눌러도 아무 일이
            없는 버튼은 고장으로 읽힌다. 통과는 하단 두 버튼으로만 한다. */}
        {isGate ? (
          <View style={styles.back} />
        ) : (
          <Pressable
            onPress={onNotSeen}
            accessibilityRole="button"
            accessibilityLabel="뒤로"
            hitSlop={space.sm}
            style={styles.back}
          >
            <Svg width={24} height={24} viewBox="0 0 24 24">
              <Path
                d="M15 5l-7 7 7 7"
                stroke={color.text}
                strokeWidth={2.2}
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </Svg>
          </Pressable>
        )}

        <Text
          style={styles.headerTitle}
          allowFontScaling
          maxFontSizeMultiplier={type.maxScale}
          numberOfLines={1}
        >
          실종자를 찾고 있어요
        </Text>

        <View
          style={styles.badge}
          accessible
          accessibilityRole="text"
          accessibilityLabel="실종 경보"
        >
          <View style={styles.badgeDot} />
          <Text style={styles.badgeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            실종 경보
          </Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + space.xl }]}
        showsVerticalScrollIndicator={false}
      >
        {/* 대표 실루엣 이미지 — 실사진 대신 플레이스홀더(개인정보/2차가해 방지) */}
        <View
          style={[styles.heroCard, styles.cardShadow]}
          accessible
          accessibilityRole="image"
          accessibilityLabel="실종 어르신 대표 실루엣 이미지"
        >
          <LinearGradient
            colors={SILHOUETTE_GRADIENT}
            start={{ x: 0, y: 0 }}
            end={{ x: 0.4, y: 1 }}
            style={styles.heroFill}
          >
            <Svg width={84} height={84} viewBox="0 0 24 24">
              <SvgCircle
                cx={12}
                cy={8.5}
                r={3.6}
                stroke="rgba(255,255,255,0.9)"
                strokeWidth={1.4}
                fill="none"
              />
              <Path
                d="M5 20c0-3.9 3.1-7 7-7s7 3.1 7 7"
                stroke="rgba(255,255,255,0.9)"
                strokeWidth={1.4}
                fill="none"
                strokeLinecap="round"
              />
            </Svg>
          </LinearGradient>
        </View>

        {/* 골든타임(§4.1 빨강) + 익명 동시 참여자(중립 — 심각도색 아님) */}
        <View style={styles.goldenRow}>
          <GoldenTimeChip goldenTime={goldenTime} emphasis="critical" />
          {watching != null && <PresenceBadge watching={watching} />}
        </View>

        {/* 실종자 카드 — 단일 소스(익명, 인상착의 칩) */}
        <View style={styles.block}>
          {/* 앱 안 시민 화면 — 실명·나이는 노출, 진단명은 제외(민감정보).
              노출 범위 결정은 #125, 데이터 출처는 실제 알림 우선(view 주석 참고). */}
          <MissingPersonCard view={view} variant="full" showAppearanceChips />
        </View>

        {/* 최종 목격 — 구역·시간만(의료정보 비노출). 단일 소스 profile.lastSeen */}
        <View
          style={[styles.seenCard, styles.cardShadow]}
          accessible
          accessibilityLabel={`최종 목격 장소 ${profile.lastSeen}`}
        >
          <View style={styles.seenHead}>
            <Svg width={16} height={16} viewBox="0 0 24 24">
              <Path
                d="M12 21s6.5-5.6 6.5-10.5a6.5 6.5 0 0 0-13 0C5.5 15.4 12 21 12 21Z"
                stroke={color.criticalInk}
                strokeWidth={2}
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <SvgCircle cx={12} cy={10.5} r={2.2} stroke={color.criticalInk} strokeWidth={2} fill="none" />
            </Svg>
            <Text style={styles.seenLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              최종 목격 장소
            </Text>
          </View>
          <Text
            style={styles.seenValue}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
            numberOfLines={2}
          >
            {profile.lastSeen}
          </Text>
        </View>

        {/* 미니 지도(§4.5 실 타일맵) — 최종 목격·예상 이동 반경·내 위치 */}
        <View style={styles.mapCard}>
          <BaseMap
            region={MAP_REGION}
            scrollEnabled={false}
            style={styles.map}
            showsUserLocation={located}
            accessibilityLabel={mapA11yLabel}
          >
            <Circle
              center={toLatLng(LAST_SEEN)}
              radius={PREDICT_RADIUS_M}
              strokeColor={color.critical}
              strokeWidth={2}
              fillColor={hexToRgba(color.critical, 0.13)}
            />
            <MapPin kind="lastSeen" coordinate={LAST_SEEN} title="최종 목격 위치" description={profile.area} />
            {/* 내 위치는 OS 기본 마커(showsUserLocation)가 그린다 — 직접 핀을 찍으면
                방향·불확실성 표현을 잃고, 무엇보다 측위 실패 시 가짜 좌표를 찍게 된다.
                권한이 없을 때만 아무것도 안 보이는 게 정직한 동작. */}
          </BaseMap>

          {/* 지도 배지(§4.1 빨강) — 정보성, 지도 위 오버레이 */}
          <View style={styles.mapBadge} pointerEvents="none">
            <Svg width={13} height={13} viewBox="0 0 24 24">
              <Path
                d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7Zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5Z"
                fill={ON_CRITICAL}
              />
            </Svg>
            {/* 배지는 좁으니 안/밖까지만. 등급은 아래 캡션이 말한다. */}
            <Text style={styles.mapBadgeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {area.short ? `${area.short} · 예상 동선` : '예상 동선'}
            </Text>
          </View>
        </View>

        {/* 이 미니 지도에는 히트맵이 없다(예상 반경 원만 있음) — 내가 얼마나 유력한
            구역에 있는지는 색으로 안 보이므로 문장으로 말해준다. */}
        <Text style={styles.areaCaption} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          {area.label}
        </Text>

        {/* 회상 유도(§4.1 빨강 워시) */}
        <View style={styles.recallCard} accessible accessibilityLabel={`혹시 이런 분, 스쳐 지나가지 않으셨어요? ${recallCopy}`}>
          <View style={styles.recallHead}>
            <Svg width={20} height={20} viewBox="0 0 24 24">
              <Path
                d="M9.5 16.5c-3-1-5-3.8-5-7A7 7 0 0 1 18.5 9c0 2.2-1 4-2.5 5.3-.8.7-1 1.2-1 2.2v.5h-5v-.5Z"
                stroke={color.criticalInk}
                strokeWidth={1.9}
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <Path
                d="M9.5 20.5h5"
                stroke={color.criticalInk}
                strokeWidth={1.9}
                fill="none"
                strokeLinecap="round"
              />
            </Svg>
            <Text style={styles.recallTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              혹시 이런 분, 스쳐 지나가지 않으셨어요?
            </Text>
          </View>
          <Text style={styles.recallBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {recallCopy}
          </Text>
        </View>

        <Text style={styles.anonNote} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          제보는 익명으로 전달되고, 내 위치·신원은 공개되지 않아요.
        </Text>
      </ScrollView>

      {/* 하단 액션바 */}
      <View style={[styles.actions, { paddingBottom: insets.bottom + space.md }]}>
        <View style={styles.actionRow}>
          {/* '봤어요' — 빨강 그라디언트(§4.1), 주 행동 */}
          <Pressable
            onPress={onSeen}
            accessibilityRole="button"
            accessibilityLabel="봤어요"
            accessibilityHint="목격 내용을 대화로 남길 수 있어요"
            style={({ pressed }) => [styles.seenBtnWrap, pressed && styles.pressed]}
          >
            <LinearGradient
              colors={SEEN_GRADIENT}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.seenBtn}
            >
              <Svg width={22} height={22} viewBox="0 0 24 24">
                <Path
                  d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"
                  stroke={ON_CRITICAL}
                  strokeWidth={2.1}
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <SvgCircle cx={12} cy={12} r={3} stroke={ON_CRITICAL} strokeWidth={2.1} fill="none" />
              </Svg>
              <Text style={styles.seenBtnText} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
                봤어요
              </Text>
            </LinearGradient>
          </Pressable>

          {/* '못 봤어요' — 관문일 땐 이번 진입만 통과(억제 아님) */}
          <CTAButton
            label="못 봤어요"
            onPress={onNotSeen}
            variant="ghost"
            fullWidth={false}
            style={styles.notSeenBtn}
            accessibilityHint={
              isGate
                ? '이번에는 넘어갑니다. 앱을 다시 열면 이 경보가 먼저 보여요'
                : '경보를 닫고 이전 화면으로 돌아갑니다'
            }
          />
        </View>

        <Text style={styles.helperText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          ‘봤어요’를 누르면 목격 내용을 대화로 편하게 남길 수 있어요
        </Text>

        {/* 영구 억제 — 관문을 끄는 유일한 경로. 저강조로 두되 반드시 도달 가능해야
            한다(한 번의 명시적 선택을 요구하는 것이 넛지, 못 빠져나가게 하는 건 함정). */}
        {isGate && (
          <Pressable
            onPress={onDismissCase}
            accessibilityRole="button"
            accessibilityLabel="이 사건은 그만 볼래요"
            accessibilityHint="앞으로 이 경보가 먼저 뜨지 않아요. 새로운 긴급 알림은 계속 받습니다"
            hitSlop={space.sm}
            style={({ pressed }) => [styles.optOut, pressed && styles.pressed]}
          >
            <Text style={styles.optOutLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              이 사건은 그만 볼래요
            </Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.surface },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    gap: space.sm,
  },
  back: { width: HIT, height: HIT, alignItems: 'center', justifyContent: 'center' },
  headerTitle: {
    flex: 1,
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    letterSpacing: -0.3,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: color.criticalWash,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    borderRadius: radius.pill,
  },
  badgeDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: color.critical, marginRight: space.xs },
  badgeText: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.criticalInk,
    fontFamily: type.family,
  },

  body: { paddingHorizontal: space.lg, paddingTop: space.sm },

  cardShadow: {
    shadowColor: color.text,
    shadowOpacity: 0.09,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 6 },
    elevation: 3,
  },

  heroCard: {
    height: 176,
    borderRadius: radius.xl,
    overflow: 'hidden',
    borderWidth: 2,
    borderColor: color.criticalWash,
    backgroundColor: color.surfaceAlt,
  },
  heroFill: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  // 참여자 배지가 붙어 두 칩이 되므로 줄바꿈 허용 — 큰 글자 설정에서 잘리면 안 된다.
  goldenRow: { marginTop: space.lg, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space.sm },

  block: { marginTop: space.lg },

  seenCard: {
    marginTop: space.lg,
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
  },
  seenHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  seenLabel: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
  },
  seenValue: {
    marginTop: space.sm,
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    lineHeight: 24,
  },

  mapCard: {
    marginTop: space.lg,
    height: 176,
    borderRadius: radius.lg,
    overflow: 'hidden',
  },
  map: { flex: 1 },
  mapBadge: {
    position: 'absolute',
    top: space.md,
    left: space.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    backgroundColor: color.critical,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  mapBadgeText: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: ON_CRITICAL,
    fontFamily: type.family,
  },

  recallCard: {
    marginTop: space.lg,
    backgroundColor: color.criticalWash,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  recallHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  recallTitle: {
    flex: 1,
    fontSize: type.size.body,
    fontWeight: type.weight.black,
    color: color.criticalInk,
    fontFamily: type.family,
  },
  recallBody: {
    marginTop: space.sm,
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: color.textBody,
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
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: color.border,
    backgroundColor: color.surface,
  },
  actionRow: { flexDirection: 'row', gap: space.md },
  seenBtnWrap: {
    flex: 1.4,
    borderRadius: radius.lg,
    overflow: 'hidden',
    shadowColor: color.critical,
    shadowOpacity: 0.4,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 6,
  },
  seenBtn: {
    minHeight: 64,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    paddingHorizontal: space.lg,
  },
  seenBtnText: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: ON_CRITICAL,
    fontFamily: type.family,
  },
  notSeenBtn: {
    flex: 1,
    minHeight: 64,
    borderWidth: 1.5,
    borderColor: color.border,
    backgroundColor: color.surface,
  },
  pressed: { opacity: 0.9 },

  areaCaption: {
    marginTop: space.sm,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
    lineHeight: 21,
  },
  helperText: {
    marginTop: space.md,
    textAlign: 'center',
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
    lineHeight: 18,
  },
  optOut: { marginTop: space.sm, minHeight: HIT, alignItems: 'center', justifyContent: 'center' },
  optOutLabel: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
    textDecorationLine: 'underline',
  },
});
