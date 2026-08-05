/**
 * 수색 탭 (spec §3.4, search-content). 라이트 소비자 화면.
 *
 * 목업 재현: 전면 지도 위 상태 pill·경과 chip·"내가 확인할 구역" 주석·현재위치 마커,
 * 하단 시트(인상착의 카드 · 112 안내 · 제보 CTA)를 그대로 옮긴다.
 *
 * 적용한 정정(§3.4/§4.1/§4.2/§4.5):
 *  - 목업의 라벨없는 SVG blob → 실 타일맵 <BaseMap> + <PoaHeatmap>(usePoaPrediction) +
 *    최종 목격 <MapPin lastSeen> + 현재위치 <MapPin me> + 확인구역 <PredictionRadius>.
 *  - 색약 대비 <HeatLegend>(수치·패턴 범례)를 지도 위에 부유.
 *  - 심각도 색: '수색 진행 중' chrome = 앰버(useModeTheme().accent). 긴급(critical)은
 *    ModeStatusBar가 severity로 자동 승격(빨강). 이 화면에 앰버 긴급 badge 없음.
 *  - 주 CTA "제보하기" → ReportChat. 112 안내 병기.
 *  - 실종자 = MissingPersonCard(compact·anon) 단일 소스. "남성"/"84세" 하드코딩 없음.
 *  - 모드 전환 트리거 없음 — 색만 셸 강조.
 */
import React from 'react';
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import { color, radius, space, type } from '../theme/tokens';
import { useModeTheme } from '../theme/theme';
import { usePoaPrediction, useGoldenTime, usePresenceCount } from '../hooks/queries';
import { DEMO_CASE_ID, LAST_SEEN, MISSING } from '../data/missing';
import { hexToRgba } from '../utils/color';
import { useAuthStore } from '../store/authStore';
import { useAppModeStore } from '../store/appModeStore';
import { useMissingPersonStore } from '../store/missingPersonStore';
import { toAnonView } from '../data/missingView';
import { useMyLocation } from '../hooks/useMyLocation';
import { distanceM, formatWalkTime } from '../utils/geo';
import type { RootStackParamList } from '../navigation/types';

import BaseMap from '../components/BaseMap';
import PoaHeatmap from '../components/PoaHeatmap';
import MapPin from '../components/MapPin';
import PredictionRadius from '../components/PredictionRadius';
import HeatLegend from '../components/HeatLegend';
import MissingPersonCard from '../components/MissingPersonCard';
import PresenceBadge from '../components/PresenceBadge';
import ModeStatusBar from '../components/ModeStatusBar';

/** '내가 확인할 구역' 반경(m). '수색 진행' 요소 → 앰버 계열. */
const ZONE_RADIUS_M = 240;

export default function SearchScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const theme = useModeTheme();
  // 표시 컴포넌트에 넘길 데이터는 화면이 가져온다(디자인 교체 대비).
  const mode = useAppModeStore((s) => s.mode);
  const severity = useAppModeStore((s) => s.severity);
  const profile = useMissingPersonStore((s) => s.profile);
  const watching = usePresenceCount(DEMO_CASE_ID);
  const role = useAuthStore((s) => s.role);
  const golden = useGoldenTime();
  const poa = usePoaPrediction(DEMO_CASE_ID, 1);

  const grid = poa.data;
  const cumPct = grid ? Math.round(grid.cumulative * 100) : null;
  const elapsedMin = golden ? Math.floor(golden.elapsedSec / 60) : null;

  // 실측 내 위치 — 지도 마커는 OS(showsUserLocation)에 맡기고, 거리·도보시간만 직접 쓴다.
  const { point: myPoint, accuracyM, status: locStatus } = useMyLocation();
  const located = locStatus === 'granted' && myPoint != null;
  const meters = myPoint ? distanceM(myPoint, LAST_SEEN) : null;
  const walkLabel = meters == null ? null : formatWalkTime(meters, accuracyM);

  const mapA11y = grid
    ? `발견 확률 히트맵. 최고 구역 ${grid.topLabel}. 누적 발견확률 ${cumPct}%. 최종 목격 위치와 ${
        located ? '현재 위치, ' : ''
      }내가 확인할 구역이 표시돼 있어요.`
    : '발견 확률 지도를 불러오는 중입니다.';

  const onReport = () => navigation.navigate('ReportChat', { caseId: DEMO_CASE_ID });

  return (
    <View style={styles.root}>
      <StatusBar style="dark" />

      {/* ── 지도 레이어 (전면) ─────────────────────────── */}
      <View style={styles.mapLayer}>
        <BaseMap style={styles.mapFill} accessibilityLabel={mapA11y} showsUserLocation={located}>
          {grid ? <PoaHeatmap grid={grid} /> : null}
          <PredictionRadius center={LAST_SEEN} radiusM={ZONE_RADIUS_M} color={theme.accent} />
          <MapPin
            kind="lastSeen"
            coordinate={LAST_SEEN}
            title="최종 목격 위치"
            description="정릉동 주민센터, 오후 3시 10분경"
          />
          {/* 내 위치 마커는 OS 기본(showsUserLocation)에 맡긴다 — 방향·불확실성까지
              센서융합으로 그려주고, 측위 실패 시 가짜 좌표를 찍지 않는다. */}
        </BaseMap>
      </View>

      {/* ── 지도 로딩 오버레이 ─────────────────────────── */}
      {poa.isLoading ? (
        <View
          style={styles.loadOverlay}
          accessible
          accessibilityLabel="예측 지도를 불러오는 중입니다"
        >
          <ActivityIndicator color={theme.accent} size="large" />
          <Text style={styles.loadText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            예측 지도를 불러오는 중…
          </Text>
        </View>
      ) : null}

      {/* ── 상단 스크림(칩 가독성 확보) ────────────────── */}
      <LinearGradient
        pointerEvents="none"
        colors={[hexToRgba(color.surface, 0.98), hexToRgba(color.surface, 0)] as const}
        style={[styles.topScrim, { height: insets.top + 132 }]}
      />

      {/* ── 상단 바: 모드 상태 + 경과 chip ─────────────── */}
      <View style={[styles.topBar, { top: insets.top + space.sm }]}>
        <ModeStatusBar mode={mode} severity={severity} />
        {elapsedMin != null ? (
          <View
            style={[styles.elapsedChip, { backgroundColor: theme.accentWash }]}
            accessible
            accessibilityLabel={`수색 시작 ${elapsedMin}분 경과`}
          >
            <Text
              style={[styles.elapsedText, { color: theme.accentInk }]}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
              numberOfLines={1}
            >
              {elapsedMin}분 전 시작
            </Text>
          </View>
        ) : null}
      </View>

      {/* ── 지도 위 주석 + 범례 (그리드 준비 후) ──────────── */}
      {grid && !poa.isLoading ? (
        <>
          <View
            style={[styles.zoneAnno, { top: insets.top + 150 }]}
            pointerEvents="none"
            accessible
            accessibilityLabel={`내가 확인할 구역.${walkLabel ? ` ${walkLabel} 거리.` : ''} 누적 발견확률 ${cumPct}퍼센트.`}
          >
            <View style={styles.zonePill}>
              <View style={[styles.zoneDot, { backgroundColor: theme.accent }]} />
              <Text style={styles.zonePillText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                내가 확인할 구역
              </Text>
            </View>
            <View style={[styles.distChip, { backgroundColor: theme.accent }]}>
              <Text style={styles.distText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                {walkLabel ? `${walkLabel} 거리 · ` : ''}누적 {cumPct}%
              </Text>
            </View>
          </View>

          <View style={[styles.legendFloat, { top: insets.top + 60 }]}>
            <HeatLegend compact />
          </View>
        </>
      ) : null}

      {/* ── 지도 로드 실패 → 재시도 ─────────────────────── */}
      {poa.isError ? (
        <Pressable
          onPress={() => poa.refetch()}
          accessibilityRole="button"
          accessibilityLabel="지도 다시 불러오기"
          style={({ pressed }) => [
            styles.errorCard,
            { top: insets.top + 160 },
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.errorText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            지도를 불러오지 못했어요. 눌러서 다시 시도해 주세요.
          </Text>
        </Pressable>
      ) : null}

      {/* ── 하단 시트 ─────────────────────────────────── */}
      <View style={[styles.sheet, { paddingBottom: insets.bottom + space.lg }]}>
        <View style={styles.grabber} />

        {/* 참여자 수는 경보 상세뿐 아니라 수색 탭에서도 보여야 한다 — 경보를
            지나친 뒤에 이 탭으로 들어와 수색하는 흐름이 오히려 본류다.
            헤더 문구가 이미 "함께 찾고 있어요"라 배지는 짧은 변형을 쓴다. */}
        <View style={styles.sheetHead}>
          <Text style={styles.sheetKicker} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            지금 함께 찾고 있어요
          </Text>
          {watching != null && <PresenceBadge watching={watching} compact />}
        </View>

        {/* 시민 화면 — 익명 뷰 */}
        <MissingPersonCard view={toAnonView(profile)} variant="compact" showAppearanceChips />

        <View style={styles.lastSeenRow} accessible accessibilityLabel={`마지막 목격 · ${MISSING.area} 인근`}>
          <Text style={styles.lastSeenIcon} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            📍
          </Text>
          <Text
            style={[styles.lastSeenText, { color: theme.accentInk }]}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
            numberOfLines={1}
          >
            마지막 목격 · {MISSING.area} 인근
          </Text>
        </View>

        {/* 112 안내 (mockup copy) — 안전 지침 */}
        <View
          style={[styles.info112, { backgroundColor: theme.accentWash }]}
          accessible
          accessibilityLabel="발견하면 가까이 가지 말고 112로 신고해 주세요. 이 앱은 신고 채널이 아니라 함께 찾는 도구예요."
        >
          <Text style={styles.info112Icon} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            ℹ️
          </Text>
          <Text
            style={[styles.info112Text, { color: theme.accentInk }]}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
          >
            발견하면 가까이 가지 말고{' '}
            <Text style={styles.info112Strong} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              112
            </Text>
            로 신고해 주세요. 이 앱은 신고 채널이 아니라, 예측과 제보로 함께 찾는 도구예요.
          </Text>
        </View>

        {/* 주 CTA: 제보하기 → ReportChat (앰버 그라디언트) */}
        <Pressable
          onPress={onReport}
          accessibilityRole="button"
          accessibilityLabel="제보하기"
          accessibilityHint="본 것을 알려주면 수색 구역을 좁힐 수 있어요"
          style={({ pressed }) => [styles.ctaWrap, pressed && styles.pressed]}
        >
          <LinearGradient
            colors={[theme.accent, theme.accentInk] as const}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={[styles.ctaGradient, { shadowColor: theme.accent }]}
          >
            <Text style={styles.ctaIcon} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              👁️
            </Text>
            <Text style={styles.ctaLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
              목격 내용 제보하기
            </Text>
          </LinearGradient>
        </Pressable>

        {role === 'operator' ? (
          <View
            style={styles.operatorNote}
            accessible
            accessibilityLabel="운영자 전용 안내. AI 예측 지도 전체보기는 관제 콘솔에서 제공돼요."
          >
            <Text style={styles.operatorText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              운영자 · AI 예측 지도 전체보기는 관제 콘솔에서 제공돼요
            </Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

const SHADOW = Platform.OS === 'android' ? { elevation: 8 } : {
  shadowColor: color.text,
  shadowOpacity: 0.14,
  shadowRadius: 16,
  shadowOffset: { width: 0, height: -6 },
};

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.surface },

  mapLayer: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 },
  mapFill: { flex: 1, borderRadius: 0, borderWidth: 0 },

  loadOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(255,255,255,0.72)',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
  },
  loadText: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
  },

  topScrim: { position: 'absolute', top: 0, left: 0, right: 0 },

  topBar: {
    position: 'absolute',
    left: space.lg,
    right: space.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.sm,
  },
  elapsedChip: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
  },
  elapsedText: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
  },

  zoneAnno: { position: 'absolute', left: 0, right: 0, alignItems: 'center', gap: space.sm },
  zonePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: color.surface,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    shadowColor: color.text,
    shadowOpacity: 0.16,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 4,
  },
  zoneDot: { width: 9, height: 9, borderRadius: 5 },
  zonePillText: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },
  distChip: {
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
  distText: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.surface,
    fontFamily: type.family,
  },

  legendFloat: { position: 'absolute', right: space.lg },

  errorCard: {
    position: 'absolute',
    left: space.lg,
    right: space.lg,
    backgroundColor: color.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    shadowColor: color.text,
    shadowOpacity: 0.12,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
  errorText: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
    textAlign: 'center',
  },

  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: color.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    gap: space.md,
    ...SHADOW,
  },
  grabber: {
    width: 42,
    height: 5,
    borderRadius: radius.pill,
    backgroundColor: color.border,
    alignSelf: 'center',
    marginBottom: space.xs,
  },
  // 큰 글자 설정에서 배지가 밀려 잘리지 않도록 줄바꿈 허용.
  sheetHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: space.sm,
  },
  sheetKicker: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },

  lastSeenRow: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  lastSeenIcon: { fontSize: 15 },
  lastSeenText: {
    flex: 1,
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
  },

  info112: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    borderRadius: radius.md,
    padding: space.md,
    gap: space.sm,
  },
  info112Icon: { fontSize: 18 },
  info112Text: {
    flex: 1,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    lineHeight: 22,
  },
  info112Strong: { fontWeight: type.weight.black },

  ctaWrap: {
    borderRadius: radius.lg,
    marginTop: space.xs,
  },
  ctaGradient: {
    minHeight: 60,
    borderRadius: radius.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    paddingHorizontal: space.xl,
    shadowOpacity: 0.4,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 10 },
    elevation: 8,
  },
  ctaIcon: { fontSize: 20 },
  ctaLabel: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.surface,
    fontFamily: type.family,
  },

  operatorNote: {
    backgroundColor: color.surfaceAlt,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.md,
  },
  operatorText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
  },

  pressed: { opacity: 0.9 },
});
