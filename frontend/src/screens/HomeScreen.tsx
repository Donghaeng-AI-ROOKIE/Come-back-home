/**
 * 홈 (CitizenTabs · Home, 라이트) — spec §3.1.
 * 평상시 산책 모드의 홈. 걷기 활동 + "미리 등록해두면 빨리 찾는다" 예방 가치 전달.
 * 핵심 원칙: 홈에서 실종발동/모드전환 트리거를 만들지 않는다(spec §3.1 정정).
 *  - 벨 → 락스크린 경보 데모 진입
 *  - 걸음 히어로(WALK_STATS) · [분리A] 동네 안심 카드(비인터랙티브) · [분리B] 가족 예방 등록 카드(→Reg)
 *  - 최근 산책 경로 지도(Polyline + 내 위치) + 산책 시작(모드 전환 아님) · 추천 코스 캐러셀
 *  - 최하단 디버그 칩: 데모용 경찰경보 연동(enterSearch → AlertSync)
 * 이모지는 🌿 1개만(카피 톤: 따뜻·차분·일상).
 */
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { TextProps } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Polyline } from 'react-native-maps';
import Svg, { Path } from 'react-native-svg';
import { color, radius, space, type, HIT } from '../theme/tokens';
import { WALK_COURSES, WALK_STATS } from '../data/mock';
import { DEMO_CASE_ID } from '../data/missing';
import { useAppModeStore } from '../store/appModeStore';
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
const CURRENT_POS = ROUTE[ROUTE.length - 1];

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const enterSearch = useAppModeStore((s) => s.enterSearch);

  const [walking, setWalking] = useState(false);
  const [selectedCourseId, setSelectedCourseId] = useState<string | null>(null);

  const progressPct = Math.min(100, Math.round((WALK_STATS.steps / WALK_STATS.goal) * 100));

  const openAlerts = () => navigation.navigate('LockScreenAlert', { caseId: DEMO_CASE_ID });
  const openReg = () => navigation.navigate('CitizenTabs', { screen: 'Reg' });
  const toggleWalk = () => setWalking((w) => !w);
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
            <AppText style={styles.greeting}>오늘도 평안한 하루예요</AppText>
            <View
              style={styles.statusPill}
              accessible
              accessibilityRole="text"
              accessibilityLabel="우리 동네는 지금 평온해요"
            >
              <View style={styles.statusDot} />
              <AppText style={styles.statusPillText}>우리 동네는 지금 평온해요</AppText>
            </View>
          </View>
          <Pressable
            onPress={openAlerts}
            accessibilityRole="button"
            accessibilityLabel="알림"
            accessibilityHint="경찰 실종경보 알림 화면을 엽니다"
            hitSlop={8}
            style={({ pressed }) => [styles.bellBtn, pressed && styles.pressed]}
          >
            <Svg width={22} height={22} viewBox="0 0 24 24">
              <Path
                d="M12 2a2 2 0 0 0-2 2v.6A6 6 0 0 0 6 10v4l-1.5 2.2A1 1 0 0 0 5.3 18h13.4a1 1 0 0 0 .8-1.8L18 14v-4a6 6 0 0 0-4-5.4V4a2 2 0 0 0-2-2Zm0 20a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Z"
                fill={color.walk}
              />
            </Svg>
            <View style={styles.bellBadge} />
          </Pressable>
        </View>

        {/* 2. 오늘의 걸음 히어로 (그린) */}
        <View
          style={styles.hero}
          accessible
          accessibilityLabel={`오늘의 걸음 ${fmt(WALK_STATS.steps)}걸음, 목표 ${fmt(
            WALK_STATS.goal,
          )}걸음의 ${progressPct}퍼센트. 거리 ${WALK_STATS.distanceKm}킬로미터, 걸은 시간 ${WALK_STATS.durationMin}분.`}
        >
          <View style={styles.heroTopRow}>
            <AppText style={styles.heroKicker}>오늘의 걸음</AppText>
            <AppText style={styles.heroGoal}>목표 {fmt(WALK_STATS.goal)}걸음</AppText>
          </View>
          <View style={styles.heroNumRow}>
            <AppText style={styles.heroNum}>{fmt(WALK_STATS.steps)}</AppText>
            <AppText style={styles.heroUnit}>걸음</AppText>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${progressPct}%` as `${number}%` }]} />
          </View>
          <View style={styles.heroStatsRow}>
            <View style={styles.heroStat}>
              <AppText style={styles.heroStatVal}>{WALK_STATS.distanceKm}</AppText>
              <AppText style={styles.heroStatUnit}>km</AppText>
            </View>
            <View style={styles.heroDivider} />
            <View style={styles.heroStat}>
              <AppText style={styles.heroStatVal}>{WALK_STATS.durationMin}</AppText>
              <AppText style={styles.heroStatUnit}>분</AppText>
            </View>
            <View style={styles.heroDivider} />
            <View style={styles.heroStat}>
              <AppText style={styles.heroStatVal}>{progressPct}</AppText>
              <AppText style={styles.heroStatUnit}>%</AppText>
            </View>
          </View>
        </View>

        {/* 3. [분리 A] 동네 안심 상태 카드 — 비인터랙티브, chevron/activate 없음 */}
        <View
          style={styles.safeCard}
          accessible
          accessibilityRole="text"
          accessibilityLabel="동네 안심 상태. 우리 동네는 지금 평온해요. 이번 달 이웃 세 명이 무사히 집으로 돌아왔어요."
        >
          <View style={styles.safeIconWrap}>
            <AppText style={styles.safeEmoji}>🌿</AppText>
          </View>
          <View style={styles.flex1}>
            <AppText style={styles.safeTitle}>우리 동네는 지금 평온해요</AppText>
            <AppText style={styles.safeSub}>이번 달 이웃 3명 무사 귀가</AppText>
          </View>
        </View>

        {/* 4. [분리 B] 가족 예방 등록 카드 — 카드 전체가 Reg 탭 진입 */}
        <Pressable
          onPress={openReg}
          accessibilityRole="button"
          accessibilityLabel="가족 예방 등록"
          accessibilityHint="가족을 미리 등록하는 화면으로 이동합니다"
          style={({ pressed }) => [styles.regCard, pressed && styles.pressed]}
        >
          <View style={styles.regIconWrap}>
            <Svg width={22} height={22} viewBox="0 0 24 24">
              <Path d="M12 3 3 10.5V21h6v-6h6v6h6V10.5L12 3Z" fill={color.walk} />
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
        <View style={styles.sectionHead}>
          <AppText style={styles.sectionTitle}>최근 산책 경로</AppText>
        </View>
        <View style={styles.mapWrap}>
          <BaseMap
            region={WALK_REGION}
            scrollEnabled={false}
            accessibilityLabel={`최근 산책 경로 지도. 정릉천 일대를 ${WALK_STATS.distanceKm}킬로미터 걸었어요.`}
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
          <Pressable
            onPress={toggleWalk}
            accessibilityRole="button"
            accessibilityLabel={walking ? '산책 기록 정지' : '산책 시작'}
            accessibilityHint={walking ? '산책 걷기 기록을 멈춥니다' : '산책 걷기 기록을 시작합니다'}
            accessibilityState={{ selected: walking }}
            hitSlop={8}
            style={({ pressed }) => [styles.walkFab, pressed && styles.pressed]}
          >
            <View style={[styles.walkFabDot, walking && styles.walkFabDotOn]} />
            <AppText style={styles.walkFabText}>{walking ? '산책 기록 중' : '산책 시작'}</AppText>
          </Pressable>
        </View>

        {/* 6. 추천 코스 캐러셀 */}
        <View style={styles.sectionHead}>
          <AppText style={styles.sectionTitle}>추천 코스</AppText>
          <AppText style={styles.sectionSub}>가볍게 걷기 좋은 동네 길</AppText>
        </View>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.carousel}
        >
          {WALK_COURSES.map((c) => {
            const selected = selectedCourseId === c.id;
            return (
              <Pressable
                key={c.id}
                onPress={() => setSelectedCourseId(selected ? null : c.id)}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                accessibilityLabel={`${c.name}, ${c.distanceKm}킬로미터, ${c.durationMin}분, ${c.tag}`}
                accessibilityHint="이 코스를 선택합니다"
                style={({ pressed }) => [
                  styles.courseCard,
                  selected && styles.courseCardOn,
                  pressed && styles.pressed,
                ]}
              >
                <View style={styles.courseTag}>
                  <AppText style={styles.courseTagText}>{c.tag}</AppText>
                </View>
                <AppText style={styles.courseName} numberOfLines={2}>
                  {c.name}
                </AppText>
                <AppText style={styles.courseMeta}>
                  {c.distanceKm}km · {c.durationMin}분
                </AppText>
                {selected ? <AppText style={styles.courseSelected}>선택됨</AppText> : null}
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
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surface },
  scroll: { paddingHorizontal: space.lg, paddingTop: space.md, gap: space.lg },
  flex1: { flex: 1 },
  pressed: { opacity: 0.85 },

  // 헤더
  header: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  headerText: { flex: 1, gap: space.sm },
  greeting: {
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: color.walkWash,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    borderRadius: radius.pill,
    gap: space.sm,
  },
  statusDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: color.walk },
  statusPillText: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.walkInk,
    fontFamily: type.family,
  },
  bellBtn: {
    width: HIT,
    height: HIT,
    borderRadius: radius.pill,
    backgroundColor: color.walkWash,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: space.md,
  },
  bellBadge: {
    position: 'absolute',
    top: 11,
    right: 13,
    width: 9,
    height: 9,
    borderRadius: 5,
    backgroundColor: color.walk,
    borderWidth: 1.5,
    borderColor: color.surface,
  },

  // 걸음 히어로
  hero: { backgroundColor: color.walkInk, borderRadius: radius.xl, padding: space.xl },
  heroTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  heroKicker: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.surface,
    fontFamily: type.family,
  },
  heroGoal: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: hexToRgba(color.surface, 0.92),
    fontFamily: type.family,
  },
  heroNumRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    marginTop: space.sm,
    marginBottom: space.md,
  },
  heroNum: {
    fontSize: type.size.bigNum,
    fontWeight: type.weight.black,
    color: color.surface,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
  },
  heroUnit: {
    fontSize: type.size.body,
    fontWeight: type.weight.bold,
    color: color.surface,
    marginLeft: space.sm,
    fontFamily: type.family,
  },
  progressTrack: {
    height: 10,
    borderRadius: radius.pill,
    backgroundColor: hexToRgba(color.surface, 0.25),
    overflow: 'hidden',
  },
  progressFill: { height: '100%', borderRadius: radius.pill, backgroundColor: color.surface },
  heroStatsRow: { flexDirection: 'row', alignItems: 'center', marginTop: space.lg },
  heroStat: { flexDirection: 'row', alignItems: 'baseline', gap: space.xs },
  heroStatVal: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.surface,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
  },
  heroStatUnit: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: hexToRgba(color.surface, 0.92),
    fontFamily: type.family,
  },
  heroDivider: {
    width: 1,
    height: 18,
    backgroundColor: hexToRgba(color.surface, 0.32),
    marginHorizontal: space.lg,
  },

  // [분리 A] 동네 안심 카드
  safeCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: color.walkWash,
    borderRadius: radius.lg,
    padding: space.lg,
    gap: space.md,
  },
  safeIconWrap: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: color.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  safeEmoji: { fontSize: 22, fontFamily: type.family },
  safeTitle: {
    fontSize: type.size.body,
    fontWeight: type.weight.black,
    color: color.walkInk,
    fontFamily: type.family,
  },
  safeSub: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textBody,
    marginTop: 2,
    fontFamily: type.family,
  },

  // [분리 B] 가족 예방 등록 카드
  regCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: color.surface,
    borderRadius: radius.lg,
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
    fontWeight: type.weight.black,
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
  },
  regBadgeText: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.surface,
    fontFamily: type.family,
  },

  // 섹션 헤더
  sectionHead: { gap: 2 },
  sectionTitle: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },
  sectionSub: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
  },

  // 지도 + 산책 시작
  mapWrap: { height: 210, borderRadius: radius.lg, position: 'relative' },
  walkFab: {
    position: 'absolute',
    left: space.md,
    bottom: space.md,
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: color.walk,
    borderRadius: radius.pill,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    gap: space.sm,
    shadowColor: color.text,
    shadowOpacity: 0.25,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
  },
  walkFabDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: hexToRgba(color.surface, 0.7),
  },
  walkFabDotOn: { backgroundColor: color.surface },
  walkFabText: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.surface,
    fontFamily: type.family,
  },

  // 추천 코스 캐러셀
  carousel: { gap: space.md, paddingVertical: space.xs, paddingRight: space.md },
  courseCard: {
    width: 168,
    backgroundColor: color.surfaceAlt,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    gap: space.sm,
  },
  courseCardOn: { borderWidth: 2, borderColor: color.walk, backgroundColor: color.walkWash },
  courseTag: {
    alignSelf: 'flex-start',
    backgroundColor: color.surface,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    borderWidth: 1,
    borderColor: color.border,
  },
  courseTagText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
  },
  courseName: {
    fontSize: type.size.body,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },
  courseMeta: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
  },
  courseSelected: {
    fontSize: type.size.caption,
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
