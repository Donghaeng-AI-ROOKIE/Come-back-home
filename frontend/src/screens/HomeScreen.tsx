/**
 * 홈 (CitizenTabs · Home, 라이트) — spec §3.1.
 * 평상시 산책 모드의 홈. 걷기 활동 + "미리 등록해두면 빨리 찾는다" 예방 가치 전달.
 * 핵심 원칙: 홈에서 실종발동/모드전환 트리거를 만들지 않는다(spec §3.1 정정).
 *  - 벨 → 락스크린 경보 데모 진입
 *  - 걸음 히어로(WALK_STATS, 그린 그라디언트) · [분리A] 동네 안심 카드(비인터랙티브)
 *    · [분리B] 가족 예방 등록 카드(→Reg)
 *  - 최근 산책 경로 지도(BaseMap + Polyline + 내 위치) : 경로 칩 · 내 위치 버튼 · 산책 시작 FAB(모드 전환 아님)
 *  - 추천 코스 캐러셀(WALK_COURSES)
 *  - 최하단 디버그 칩: 데모용 경찰경보 연동(enterSearch → AlertSync)
 * 목업(home-content) 대비 정정: 단일 onActivate 카드 → 2개 독립 카드로 분리, chevron/activate 제거.
 * 이모지는 🌿 1개만(카피 톤: 따뜻·차분·일상).
 */
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { TextProps } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { LinearGradient } from 'expo-linear-gradient';
import { Polyline } from 'react-native-maps';
import Svg, { Circle, Line, Path, Rect } from 'react-native-svg';
import dayjs from 'dayjs';
import { color, radius, space, type, HIT } from '../theme/tokens';
import { WALK_COURSES, WALK_STATS, WALKER_NAME } from '../data/mock';
import { DEMO_CASE_ID } from '../data/missing';
import { useAppModeStore, useIsCaseDismissed } from '../store/appModeStore';
import { useDebugStore } from '../store/debugStore';
import { useAlertsForMe } from '../hooks/useAlertGate';
import { useMyLocation } from '../hooks/useMyLocation';
import { usePoaPrediction } from '../hooks/queries';
import { distanceM, formatDistance, pointInPolygon } from '../utils/geo';
import { TIER_LABEL, TIER_RANGE } from '../theme/poa';
import { hexToRgba, toLatLng } from '../utils/color';
import BaseMap from '../components/BaseMap';
import MapPin from '../components/MapPin';
import type { RootStackParamList } from '../navigation/types';

/** 모든 <Text>에 Dynamic Type 규칙(allowFontScaling + maxFontSizeMultiplier) 강제 (spec §4.3). */
function AppText(props: TextProps) {
  return <Text allowFontScaling maxFontSizeMultiplier={type.maxScale} {...props} />;
}

/** 천 단위 콤마 (Intl 비의존, 결정론적). */
function fmt(n: number): string {
  return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'] as const;

/** 히어로 그린 그라디언트(목업 linear-gradient 근사, 토큰만 사용). */
const HERO_GRADIENT = [color.walk, color.walkInk] as const;

// 산책 경로 기준 지도 리전/현재 위치 (WALK_STATS는 상수 → 모듈 스코프에서 1회 계산).
const ROUTE = WALK_STATS.route;
const ROUTE_LATS = ROUTE.map((p) => p.lat);
const ROUTE_LNGS = ROUTE.map((p) => p.lng);
const WALK_REGION = {
  latitude: (Math.min(...ROUTE_LATS) + Math.max(...ROUTE_LATS)) / 2,
  longitude: (Math.min(...ROUTE_LNGS) + Math.max(...ROUTE_LNGS)) / 2,
  latitudeDelta: 0.012,
  longitudeDelta: 0.012,
};
const CURRENT_POS = ROUTE[ROUTE.length - 1] ?? WALK_STATS.route[0];

// 추천 코스 썸네일용 미니 경로(장식) — 카드별로 순환.
const THUMBS = [
  { d: 'M26 88 C 42 62 32 46 66 48 C 98 50 94 76 130 62 C 152 54 152 32 174 32', cx: 26, cy: 88 },
  { d: 'M22 30 C 60 34 58 66 96 66 C 128 66 128 40 158 44 C 172 46 176 66 168 86', cx: 22, cy: 30 },
  {
    d: 'M30 92 C 30 66 54 60 54 36 C 54 18 78 16 96 24 C 120 34 108 66 138 66 C 158 66 164 48 162 30',
    cx: 30,
    cy: 92,
  },
] as const;

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const enterSearch = useAppModeStore((s) => s.enterSearch);
  // "안볼래요" 처리된 사건이면 벨의 미확인 배지(재촉)를 끈다. 벨 자체는 살려둬
  // 접근 경로는 유지 — 억제하는 건 재촉이지 정보가 아니다.
  const alertDismissed = useIsCaseDismissed(DEMO_CASE_ID);

  // 지오펜스를 통과한(= 나에게 해당되는) 경보만 본다. 구역 밖이면 alert 는 null 이고
  // 홈은 "평온해요" 그대로다 — 9km 떨어진 사람에게 수색 문구를 띄우는 게 거짓말이므로.
  const { alerts: myAlerts } = useAlertsForMe();
  const activeAlert = myAlerts[0] ?? null;
  const { point: myPoint, accuracyM } = useMyLocation();
  // 경보가 나에게 해당될 때만 POA 조회(빈 caseId 면 훅이 비활성).
  const poa = usePoaPrediction(activeAlert?.caseId ?? '', 1);

  // "동선 예측 확률과 얼마나 가까운가" — 내 위치가 실제로 POA 셀 안인지까지 본다.
  const myCell =
    myPoint && poa.data
      ? (poa.data.cells.find((c) => pointInPolygon(myPoint, c.polygon)) ?? null)
      : null;
  const alertMeters = activeAlert && myPoint ? distanceM(myPoint, activeAlert.targetCenter) : null;
  const alertDistance = alertMeters == null ? null : formatDistance(alertMeters, accuracyM);

  const statusLine = activeAlert
    ? `${activeAlert.area} 인근 수색이 진행 중이에요`
    : '우리 동네는 지금 평온해요';

  // 카드 본문: 예측 구역 안이면 확률까지, 밖이면 거리만, 위치를 모르면 숫자 없이.
  const alertCardSub = myCell
    ? `내 위치가 예측 구역 안이에요 · 발견확률 ${TIER_LABEL[myCell.tier]} (${TIER_RANGE[myCell.tier]})`
    : alertDistance
      ? `최종 목격지에서 ${alertDistance} · 예측 구역 주변이에요`
      : '위치를 확인할 수 없어 거리는 표시하지 않아요';

  const forceInAlertArea = useDebugStore((s) => s.forceInAlertArea);
  const setForceInAlertArea = useDebugStore((s) => s.setForceInAlertArea);

  const [walking, setWalking] = useState(false);
  const [selectedCourseId, setSelectedCourseId] = useState<string | null>(null);
  // 내 위치 버튼: key 변경으로 BaseMap을 재마운트 → initialRegion(내 산책 리전)으로 재중심.
  const [mapKey, setMapKey] = useState(0);

  const { steps, goal, distanceKm, durationMin } = WALK_STATS;
  const progressPct = Math.min(100, Math.round((steps / goal) * 100));
  const remaining = Math.max(0, goal - steps);

  const now = dayjs();
  const hour = now.hour();
  const greeting =
    hour < 12
      ? `좋은 아침이에요, ${WALKER_NAME} 님`
      : hour < 18
        ? `좋은 오후예요, ${WALKER_NAME} 님`
        : `편안한 저녁이에요, ${WALKER_NAME} 님`;
  const dateLabel = `${now.month() + 1}월 ${now.date()}일 ${WEEKDAYS[now.day()]}요일`;

  const openAlerts = () => navigation.navigate('LockScreenAlert', { caseId: DEMO_CASE_ID });
  const openReg = () => navigation.navigate('CitizenTabs', { screen: 'Reg' });
  const toggleWalk = () => setWalking((w) => !w);
  const recenter = () => setMapKey((k) => k + 1);
  // 최하단 디버그 칩 전용: 데모용 경찰경보 연동(수색 모드 진입 → 연동 화면). 홈의 유일한 모드 트리거.
  const onDemoAlertSync = () => {
    enterSearch(DEMO_CASE_ID, 'critical');
    navigation.navigate('AlertSync', { caseId: DEMO_CASE_ID });
  };

  return (
    <View style={[styles.safe, { paddingTop: insets.top }]}>
      <StatusBar style="dark" />
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + space.xxl }]}
      >
        {/* 1. 헤더 — 인사말 + 상태 pill + 벨(→락스크린) */}
        <View style={styles.header}>
          <View style={styles.headerText}>
            <AppText style={styles.greeting} numberOfLines={1}>
              {greeting}
            </AppText>
            <View
              style={styles.statusPill}
              accessible
              accessibilityRole="text"
              accessibilityLabel={statusLine}
            >
              {/* 경보가 나에게 해당되면 심각도색으로. 평온하지 않은데 그린 점을
                  띄우면 색이 상태를 잘못 부호화한다(§4.1). */}
              <View style={[styles.statusRing, activeAlert && styles.statusRingAlert]}>
                <View style={[styles.statusDot, activeAlert && styles.statusDotAlert]} />
              </View>
              <AppText style={[styles.statusPillText, activeAlert && styles.statusPillTextAlert]}>
                {statusLine}
              </AppText>
            </View>
          </View>
          <Pressable
            onPress={openAlerts}
            accessibilityRole="button"
            accessibilityLabel={alertDismissed ? '알림' : '알림, 확인하지 않은 경보 있음'}
            accessibilityHint="경찰 실종경보 알림 화면을 엽니다"
            hitSlop={8}
            style={({ pressed }) => [styles.bellBtn, pressed && styles.pressed]}
          >
            <Svg width={24} height={24} viewBox="0 0 24 24">
              <Path
                d="M6 9a6 6 0 0 1 12 0c0 4.2 1.2 5.4 2 6.5H4c.8-1.1 2-2.3 2-6.5Z"
                fill="none"
                stroke={color.textBody}
                strokeWidth={1.9}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <Path
                d="M10 20a2 2 0 0 0 4 0"
                fill="none"
                stroke={color.textBody}
                strokeWidth={1.9}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </Svg>
            {!alertDismissed && <View style={styles.bellBadge} />}
          </Pressable>
        </View>

        {/* 2. 오늘의 걸음 히어로 (그린 그라디언트) */}
        <LinearGradient
          colors={HERO_GRADIENT}
          start={{ x: 0.05, y: 0 }}
          end={{ x: 0.95, y: 1 }}
          style={styles.hero}
        >
          <View
            style={styles.heroBody}
            accessible
            accessibilityLabel={`오늘의 걸음 ${fmt(steps)}걸음, 목표 ${fmt(
              goal,
            )}걸음의 ${progressPct}퍼센트. 목표까지 ${fmt(
              remaining,
            )}걸음. 거리 ${distanceKm}킬로미터, 걸은 시간 ${durationMin}분.`}
          >
            <View style={styles.heroDeco1} />
            <View style={styles.heroDeco2} />
            <View style={styles.heroTopRow}>
              <AppText style={styles.heroKicker}>오늘의 걸음</AppText>
              <AppText style={styles.heroDate}>{dateLabel}</AppText>
            </View>
            <View style={styles.heroNumRow}>
              <AppText style={styles.heroNum}>{fmt(steps)}</AppText>
              <AppText style={styles.heroUnit}>걸음</AppText>
            </View>
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${progressPct}%` as `${number}%` }]} />
            </View>
            <View style={styles.heroMetaRow}>
              <AppText style={styles.heroRemain}>
                목표 {fmt(goal)}걸음까지 {fmt(remaining)}걸음
              </AppText>
              <View style={styles.heroMetrics}>
                <AppText style={styles.heroMetric}>
                  {distanceKm}
                  <AppText style={styles.heroMetricUnit}> km</AppText>
                </AppText>
                <View style={styles.heroMetricDivider} />
                <AppText style={styles.heroMetric}>
                  {durationMin}
                  <AppText style={styles.heroMetricUnit}> 분</AppText>
                </AppText>
              </View>
            </View>
          </View>
        </LinearGradient>

        {/* 3. [분리 A] 동네 상태 카드 — 비인터랙티브, chevron/activate 없음.
            나에게 해당되는 경보가 있으면 "평온해요" 대신 수색 상황을 말한다.
            경보 중에 평온하다고 쓰는 건 이 화면에서 가장 눈에 띄는 거짓말이었다. */}
        <View
          style={[styles.safeCard, activeAlert && styles.safeCardAlert]}
          accessible
          accessibilityRole="text"
          accessibilityLabel={
            activeAlert
              ? `동네 상태. ${activeAlert.area} 인근에서 실종자를 찾고 있어요. ${alertCardSub}`
              : '동네 안심 상태. 우리 동네는 지금 평온해요. 이번 달 이웃 세 명이 무사히 집으로 돌아왔어요.'
          }
        >
          <View style={[styles.safeIconWrap, activeAlert && styles.safeIconWrapAlert]}>
            <Svg width={24} height={24} viewBox="0 0 24 24">
              {activeAlert ? (
                // 위치 핀 — 수색 진행 중
                <>
                  <Path
                    d="M12 21s6.5-5.6 6.5-10.5a6.5 6.5 0 0 0-13 0C5.5 15.4 12 21 12 21Z"
                    fill="none"
                    stroke={color.surface}
                    strokeWidth={1.9}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <Circle cx={12} cy={10.5} r={2.2} fill="none" stroke={color.surface} strokeWidth={1.9} />
                </>
              ) : (
                // 방패 + 체크 — 평온
                <>
                  <Path
                    d="M12 3.4 5 6.1v4.7c0 4.2 2.9 7.4 7 8.7 4.1-1.3 7-4.5 7-8.7V6.1L12 3.4Z"
                    fill="none"
                    stroke={color.surface}
                    strokeWidth={1.9}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <Path
                    d="M9 11.7l2.2 2.2 3.9-4"
                    fill="none"
                    stroke={color.surface}
                    strokeWidth={1.9}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </>
              )}
            </Svg>
          </View>
          <View style={styles.flex1}>
            <AppText style={[styles.safeTitle, activeAlert && styles.safeTitleAlert]}>
              {activeAlert ? `${activeAlert.area} 인근에서 실종자를 찾고 있어요` : '우리 동네는 지금 평온해요 🌿'}
            </AppText>
            <AppText style={[styles.safeSub, activeAlert && styles.safeSubAlert]}>
              {activeAlert ? alertCardSub : '이번 달 이웃 3명이 무사히 집으로 돌아왔어요'}
            </AppText>
          </View>
        </View>

        {/* 4. [분리 B] 가족 예방 등록 카드 — 그린 아웃라인, 카드 전체가 Reg 탭 진입 */}
        <Pressable
          onPress={openReg}
          accessibilityRole="button"
          accessibilityLabel="가족 예방 등록"
          accessibilityHint="가족을 미리 등록하는 화면으로 이동합니다"
          style={({ pressed }) => [styles.regCard, pressed && styles.pressed]}
        >
          <View style={styles.regIconWrap}>
            <Svg width={22} height={22} viewBox="0 0 24 24">
              <Circle cx={10} cy={8} r={3.3} fill="none" stroke={color.walk} strokeWidth={1.9} />
              <Path
                d="M4 19c0-3.3 2.7-6 6-6"
                fill="none"
                stroke={color.walk}
                strokeWidth={1.9}
                strokeLinecap="round"
              />
              <Path
                d="M17.5 13.5v5M15 16h5"
                fill="none"
                stroke={color.walk}
                strokeWidth={1.9}
                strokeLinecap="round"
              />
            </Svg>
          </View>
          <View style={styles.flex1}>
            <AppText style={styles.regTitle}>가족을 미리 등록해 두세요</AppText>
            <AppText style={styles.regSub}>치매가 걱정된다면 실종 시 더 빨리 도울 수 있어요</AppText>
          </View>
          <View style={styles.regBadge}>
            <AppText style={styles.regBadgeText}>등록</AppText>
          </View>
        </Pressable>

        {/* 5. 최근 산책 경로 지도 + 산책 시작(모드 전환 아님) */}
        <View style={styles.mapWrap}>
          <BaseMap
            key={mapKey}
            region={WALK_REGION}
            scrollEnabled={false}
            style={styles.mapFill}
            accessibilityLabel={`최근 산책 경로 지도. 오늘 ${distanceKm}킬로미터를 걸었어요.`}
          >
            <Polyline
              coordinates={ROUTE.map(toLatLng)}
              strokeColor={color.walk}
              strokeWidth={5}
              lineCap="round"
              lineJoin="round"
            />
            <MapPin kind="me" coordinate={CURRENT_POS} title="현재 위치" />
          </BaseMap>

          {/* 최근 산책 경로 칩 (좌상단, 장식 라벨) */}
          <View style={styles.routeChip} accessible accessibilityRole="text" accessibilityLabel="최근 산책 경로">
            <View style={styles.routeChipLine} />
            <AppText style={styles.routeChipText}>최근 산책 경로</AppText>
          </View>

          {/* 내 위치 버튼 (우상단) */}
          <Pressable
            onPress={recenter}
            accessibilityRole="button"
            accessibilityLabel="내 위치"
            accessibilityHint="지도를 내 위치로 다시 맞춰요"
            hitSlop={6}
            style={({ pressed }) => [styles.locateBtn, pressed && styles.pressed]}
          >
            <Svg width={22} height={22} viewBox="0 0 24 24">
              <Circle cx={12} cy={12} r={3.6} fill="none" stroke={color.walkInk} strokeWidth={2} />
              <Path
                d="M12 2.5v3.2M12 18.3v3.2M2.5 12h3.2M18.3 12h3.2"
                fill="none"
                stroke={color.walkInk}
                strokeWidth={2}
                strokeLinecap="round"
              />
            </Svg>
          </Pressable>

          {/* 산책 시작 FAB (중앙 하단, 그린 — 모드 전환 아님) */}
          <View style={styles.fabWrap} pointerEvents="box-none">
            <Pressable
              onPress={toggleWalk}
              accessibilityRole="button"
              accessibilityLabel={walking ? '산책 기록 정지' : '산책 시작'}
              accessibilityHint={walking ? '산책 걷기 기록을 멈춥니다' : '산책 걷기 기록을 시작합니다'}
              accessibilityState={{ selected: walking }}
              style={({ pressed }) => [styles.walkFab, pressed && styles.pressed]}
            >
              {walking ? (
                <View style={styles.walkFabStop} />
              ) : (
                <Svg width={18} height={18} viewBox="0 0 24 24">
                  <Path
                    d="M7 5.2v13.6a1 1 0 0 0 1.53.85l10.5-6.8a1 1 0 0 0 0-1.7L8.53 4.35A1 1 0 0 0 7 5.2Z"
                    fill={color.surface}
                  />
                </Svg>
              )}
              <AppText style={styles.walkFabText}>{walking ? '산책 기록 중' : '산책 시작'}</AppText>
            </Pressable>
          </View>
        </View>

        {/* 6. 추천 코스 캐러셀 */}
        <View style={styles.sectionHead}>
          <View style={styles.flex1}>
            <AppText style={styles.sectionTitle}>추천 코스</AppText>
            <AppText style={styles.sectionSub}>우리 동네 걷기 좋은 길</AppText>
          </View>
          <AppText style={styles.sectionLink}>전체보기</AppText>
        </View>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.carousel}
        >
          {WALK_COURSES.map((c, idx) => {
            const selected = selectedCourseId === c.id;
            const thumb = THUMBS[idx % THUMBS.length] ?? THUMBS[0];
            const hard = c.tag !== '초급';
            return (
              <Pressable
                key={c.id}
                onPress={() => setSelectedCourseId(selected ? null : c.id)}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                accessibilityLabel={`${c.name}, ${c.distanceKm}킬로미터, 약 ${c.durationMin}분, ${c.tag}`}
                accessibilityHint="이 코스를 선택합니다"
                style={({ pressed }) => [
                  styles.courseCard,
                  selected && styles.courseCardOn,
                  pressed && styles.pressed,
                ]}
              >
                <View style={styles.courseThumb}>
                  <Svg width="100%" height="100%" viewBox="0 0 188 106" preserveAspectRatio="xMidYMid slice">
                    <Rect x={0} y={0} width={188} height={106} fill={color.walkWash} />
                    <Line x1={-6} y1={42} x2={196} y2={42} stroke={color.surface} strokeWidth={6} strokeLinecap="round" />
                    <Line x1={74} y1={-6} x2={74} y2={112} stroke={color.surface} strokeWidth={6} strokeLinecap="round" />
                    <Path d={thumb.d} fill="none" stroke={color.walk} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />
                    <Circle cx={thumb.cx} cy={thumb.cy} r={5} fill={color.surface} stroke={color.walk} strokeWidth={3} />
                  </Svg>
                  <View style={[styles.courseBadge, hard ? styles.courseBadgeHard : styles.courseBadgeEasy]}>
                    <AppText style={[styles.courseBadgeText, hard ? styles.courseBadgeTextHard : styles.courseBadgeTextEasy]}>
                      {c.tag}
                    </AppText>
                  </View>
                </View>
                <View style={styles.courseInfo}>
                  <AppText style={styles.courseName} numberOfLines={1}>
                    {c.name}
                  </AppText>
                  <View style={styles.courseMetaRow}>
                    <AppText style={styles.courseMeta}>{c.distanceKm} km</AppText>
                    <View style={styles.courseMetaDot} />
                    <AppText style={styles.courseMeta}>약 {c.durationMin}분</AppText>
                    {selected ? <AppText style={styles.courseSelected}>· 선택됨</AppText> : null}
                  </View>
                </View>
              </Pressable>
            );
          })}
        </ScrollView>

        {/* 최하단 디버그 칩 — 데모용 경찰경보 연동 트리거 */}
        <Pressable
          onPress={onDemoAlertSync}
          accessibilityRole="button"
          accessibilityLabel="데모, 경찰 실종경보 연동"
          accessibilityHint="데모용으로 경찰경보 연동 화면을 엽니다"
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
          style={({ pressed }) => [styles.debugChip, pressed && styles.pressed]}
        >
          <AppText style={styles.debugText}>데모: 경찰경보 연동</AppText>
        </Pressable>

        {/* 데모용 지오펜스 우회. 경보는 대상 구역(정릉동 반경 1.5km) 안에서만
            뜨는 게 맞는 동작인데, 그러면 정릉동 밖에서는 경보 플로우를 시연할
            방법이 없다. 이 칩이 그 유일한 우회로다. */}
        <Pressable
          onPress={() => setForceInAlertArea(!forceInAlertArea)}
          accessibilityRole="switch"
          accessibilityState={{ checked: forceInAlertArea }}
          accessibilityLabel="데모, 경보 구역 안에 있다고 가정"
          accessibilityHint="실제 위치와 무관하게 알림 대상 구역 안으로 간주합니다"
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
          style={({ pressed }) => [styles.debugChip, pressed && styles.pressed]}
        >
          <AppText style={styles.debugText}>
            {forceInAlertArea ? '데모: 경보 구역 안 (켜짐)' : '데모: 경보 구역 안이라고 가정'}
          </AppText>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surface },
  scroll: { paddingHorizontal: space.lg, paddingTop: space.md, gap: space.lg },
  flex1: { flex: 1, minWidth: 0 },
  pressed: { opacity: 0.85 },

  // 헤더
  header: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  headerText: { flex: 1, gap: space.sm },
  greeting: {
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    letterSpacing: -0.4,
  },
  statusPill: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: space.sm },
  statusRing: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: color.walkWash,
    alignItems: 'center',
    justifyContent: 'center',
  },
  statusDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: color.walk },
  statusPillText: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
  },
  // 경보 변형 — 그린(평시) 대신 심각도색. 색만으로 전달하지 않도록 문구도 함께 바뀐다.
  statusRingAlert: { backgroundColor: color.criticalWash },
  statusDotAlert: { backgroundColor: color.critical },
  statusPillTextAlert: { color: color.criticalInk, fontWeight: type.weight.bold },
  bellBtn: {
    width: 50,
    height: 50,
    borderRadius: radius.lg,
    backgroundColor: color.surface,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: space.md,
    shadowColor: color.text,
    shadowOpacity: 0.1,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 5 },
    elevation: 3,
  },
  bellBadge: {
    position: 'absolute',
    top: 12,
    right: 13,
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: color.walk,
    borderWidth: 2.5,
    borderColor: color.surface,
  },

  // 걸음 히어로 (그라디언트)
  hero: { borderRadius: radius.xl, overflow: 'hidden' },
  heroBody: { padding: space.xl },
  heroDeco1: {
    position: 'absolute',
    right: -38,
    top: -46,
    width: 150,
    height: 150,
    borderRadius: 75,
    backgroundColor: hexToRgba(color.surface, 0.1),
  },
  heroDeco2: {
    position: 'absolute',
    right: 24,
    top: 70,
    width: 82,
    height: 82,
    borderRadius: 41,
    backgroundColor: hexToRgba(color.surface, 0.07),
  },
  heroTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  heroKicker: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: hexToRgba(color.surface, 0.92),
    fontFamily: type.family,
  },
  heroDate: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: hexToRgba(color.surface, 0.82),
    fontFamily: type.family,
  },
  heroNumRow: { flexDirection: 'row', alignItems: 'baseline', marginTop: space.xs },
  heroNum: {
    fontSize: 48,
    fontWeight: type.weight.black,
    color: color.surface,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
    letterSpacing: -1,
  },
  heroUnit: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.bold,
    color: hexToRgba(color.surface, 0.92),
    marginLeft: space.sm,
    fontFamily: type.family,
  },
  progressTrack: {
    marginTop: space.md,
    height: 9,
    borderRadius: radius.pill,
    backgroundColor: hexToRgba(color.surface, 0.26),
    overflow: 'hidden',
  },
  progressFill: { height: '100%', borderRadius: radius.pill, backgroundColor: color.surface },
  heroMetaRow: {
    marginTop: space.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
  },
  heroRemain: {
    flex: 1,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: hexToRgba(color.surface, 0.94),
    fontFamily: type.family,
  },
  heroMetrics: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  heroMetric: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.surface,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
  },
  heroMetricUnit: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: hexToRgba(color.surface, 0.85),
    fontFamily: type.family,
  },
  heroMetricDivider: { width: 1, height: 13, backgroundColor: hexToRgba(color.surface, 0.4) },

  // [분리 A] 동네 안심 카드
  safeCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: color.walkWash,
    borderRadius: radius.xl,
    padding: space.lg,
    gap: space.md,
  },
  safeIconWrap: {
    width: 46,
    height: 46,
    borderRadius: radius.lg,
    backgroundColor: color.walk,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: color.walk,
    shadowOpacity: 0.35,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 5 },
    elevation: 3,
  },
  safeTitle: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.walkInk,
    fontFamily: type.family,
    letterSpacing: -0.2,
  },
  safeSub: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textBody,
    marginTop: 3,
    fontFamily: type.family,
  },
  // 경보 변형 — 워시 배경 + 잉크 텍스트. 심각도색 계열은 지키되 채도 높은 필은
  // 쓰지 않는다: 사용자가 이미 관문을 통과한 뒤의 홈이라, 여기서 다시 전면
  // 경보처럼 굴면 "그만 볼래요"를 누른 의사를 뒤집는 셈이 된다.
  safeCardAlert: { backgroundColor: color.criticalWash },
  safeIconWrapAlert: { backgroundColor: color.critical, shadowColor: color.critical },
  safeTitleAlert: { color: color.criticalInk },
  safeSubAlert: { color: color.text },

  // [분리 B] 가족 예방 등록 카드
  regCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: color.surface,
    borderRadius: radius.xl,
    borderWidth: 1.5,
    borderColor: color.walk,
    padding: space.lg,
    gap: space.md,
  },
  regIconWrap: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: color.walkWash,
    alignItems: 'center',
    justifyContent: 'center',
  },
  regTitle: {
    fontSize: type.size.body,
    fontWeight: type.weight.bold,
    color: color.text,
    fontFamily: type.family,
  },
  regSub: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textBody,
    marginTop: 2,
    lineHeight: 21,
    fontFamily: type.family,
  },
  regBadge: {
    backgroundColor: color.walk,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    shadowColor: color.walk,
    shadowOpacity: 0.4,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  regBadgeText: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.surface,
    fontFamily: type.family,
  },

  // 지도 + 오버레이
  mapWrap: {
    height: 190,
    borderRadius: radius.xl,
    position: 'relative',
    backgroundColor: color.surfaceAlt,
    shadowColor: color.text,
    shadowOpacity: 0.14,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 12 },
    elevation: 4,
  },
  mapFill: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, borderRadius: radius.xl },
  routeChip: {
    position: 'absolute',
    top: space.md,
    left: space.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: hexToRgba(color.surface, 0.93),
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    shadowColor: color.text,
    shadowOpacity: 0.12,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 3,
  },
  routeChipLine: { width: 16, height: 3.5, borderRadius: 2, backgroundColor: color.walk },
  routeChipText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: color.text,
    fontFamily: type.family,
  },
  locateBtn: {
    position: 'absolute',
    top: space.md,
    right: space.md,
    width: HIT,
    height: HIT,
    borderRadius: radius.lg,
    backgroundColor: hexToRgba(color.surface, 0.93),
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: color.text,
    shadowOpacity: 0.14,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 3,
  },
  fabWrap: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: space.md,
    alignItems: 'center',
  },
  walkFab: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: color.walk,
    borderRadius: radius.pill,
    paddingHorizontal: space.xl,
    gap: space.sm,
    shadowColor: color.walk,
    shadowOpacity: 0.45,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 10 },
    elevation: 6,
  },
  walkFabStop: { width: 15, height: 15, borderRadius: 4, backgroundColor: color.surface },
  walkFabText: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.surface,
    fontFamily: type.family,
    letterSpacing: -0.2,
  },

  // 추천 코스
  sectionHead: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    gap: space.md,
  },
  sectionTitle: {
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    letterSpacing: -0.4,
  },
  sectionSub: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textBody,
    marginTop: space.xs,
    fontFamily: type.family,
  },
  sectionLink: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.walkInk,
    fontFamily: type.family,
  },
  carousel: { gap: space.md, paddingVertical: space.xs, paddingRight: space.md },
  courseCard: {
    width: 188,
    backgroundColor: color.surface,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: color.border,
    overflow: 'hidden',
    shadowColor: color.text,
    shadowOpacity: 0.1,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 9 },
    elevation: 3,
  },
  courseCardOn: { borderWidth: 2, borderColor: color.walk },
  courseThumb: { height: 106, backgroundColor: color.walkWash, position: 'relative' },
  courseBadge: {
    position: 'absolute',
    top: space.md,
    left: space.md,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
  courseBadgeEasy: { backgroundColor: color.walkWash },
  courseBadgeHard: { backgroundColor: color.searchWash },
  courseBadgeText: { fontSize: type.size.caption, fontWeight: type.weight.bold, fontFamily: type.family },
  courseBadgeTextEasy: { color: color.walkInk },
  courseBadgeTextHard: { color: color.searchInk },
  courseInfo: { padding: space.lg, gap: space.sm },
  courseName: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    letterSpacing: -0.2,
  },
  courseMetaRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  courseMeta: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
  },
  courseMetaDot: { width: 3, height: 3, borderRadius: 2, backgroundColor: color.textCaption },
  courseSelected: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.walkInk,
    fontFamily: type.family,
  },

  // 디버그 칩
  debugChip: {
    alignSelf: 'center',
    marginTop: space.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    backgroundColor: color.surfaceAlt,
    borderWidth: 1,
    borderColor: color.border,
  },
  debugText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
  },
});
