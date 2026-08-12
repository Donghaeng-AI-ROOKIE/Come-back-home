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
import React, { useState } from 'react';
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import { color, radius, space, type } from '../theme/tokens';
import { useModeTheme } from '../theme/theme';
import {
  useActiveAlerts,
  useGoldenTime,
  useGuidance,
  usePoaPrediction,
  usePresenceCount,
} from '../hooks/queries';
import { DEMO_CASE_ID, LAST_SEEN, MISSING } from '../data/missing';
import { hexToRgba } from '../utils/color';
import type { GeoPoint, PoaGrid, TimeAxis, PoaCell } from '../types/domain';
import { useAuthStore } from '../store/authStore';
import { useAppModeStore } from '../store/appModeStore';
import { useMissingPersonStore } from '../store/missingPersonStore';
import { alertToView, toCitizenView } from '../data/missingView';
import { useMyLocation } from '../hooks/useMyLocation';
import { useAreaStatus } from '../hooks/useAreaStatus';
import type { RootStackParamList } from '../navigation/types';

import BaseMap from '../components/BaseMap';
import WebMap from '../components/WebMap';
import PoaHeatmap from '../components/PoaHeatmap';
import MapPin from '../components/MapPin';
import PredictionRadius from '../components/PredictionRadius';
import HeatLegend from '../components/HeatLegend';
import MissingPersonCard from '../components/MissingPersonCard';
import PresenceBadge from '../components/PresenceBadge';
import ModeStatusBar from '../components/ModeStatusBar';

/** '내가 확인할 구역' 반경(m). '수색 진행' 요소 → 앰버 계열. */
const ZONE_RADIUS_M = 240;

/**
 * 시간축 — "만약 t시간 경과라면" 의 지도를 본다. 0 = 지금 실제 경과시간.
 *
 * **시작점(최종 목격 위치)은 안 움직인다.** 바뀌는 것은 "그 사람이 얼마나 걸을
 * 수 있었나" 하나다 — 물감 한 방울처럼 떨어뜨린 자리는 그대로고 퍼진 범위만
 * 커진다. 82세 치매 보행속도(2.9km/h) 기준 30분이면 최대 1.44km, 1시간이면
 * 2.88km 라 상한부터 두 배 다르다.
 */
const TIME_STOPS: { t: TimeAxis; label: string }[] = [
  { t: 0.5, label: '30분' },
  { t: 1, label: '1시간' },
  { t: 2, label: '2시간' },
  { t: 4, label: '4시간' },
  { t: 8, label: '8시간' },
  { t: 0, label: '현재' },
];

/**
 * "몇 시간 시점 지도이고 언제 계산됐는가".
 *
 * 서버가 45분마다 다시 예측하지만(phase2.refresher) 화면에 안 보이면 수색대는
 * 지도가 최신인지 알 수 없다. 갱신이 실패해 오래된 지도를 계속 보고 있어도
 * 모르게 되므로 반드시 표시한다.
 */
function freshnessLabel(grid?: PoaGrid): string | null {
  if (!grid?.computedAt) return null;
  const ageMin = Math.max(0, Math.round((Date.now() - Date.parse(grid.computedAt)) / 60000));
  const elapsed = grid.elapsedHours != null ? `실종 ${grid.elapsedHours.toFixed(1)}시간 시점` : null;
  const age = ageMin < 1 ? '방금 갱신' : `${ageMin}분 전 갱신`;
  return [elapsed, age].filter(Boolean).join(' · ');
}

/**
 * 예측 품질 저하 경고 문구. 두 가지 폴백이 **둘 다 조용히** 일어난다 —
 * POA 도 지도도 정상으로 나오므로 화면만으로는 구분할 수 없다.
 *
 *  - prior 폴백  : AI 호출 실패/미연결 → 연령·유형 평균 (개인화 없음)
 *  - 도로망 폴백 : 도로망 로딩 실패 → 연속 공간 (도로 제약 없음)
 *
 * 개인화 손실이 더 크므로 prior 를 먼저 알린다. 정책이라 표시 컴포넌트가 아니라
 * 여기(화면)에 둔다 — 컴포넌트 안에 두면 디자인 교체 시 조용히 사라진다.
 */
function degradedNotice(grid?: PoaGrid): { label: string; a11y: string } | null {
  if (!grid) return null;
  if (grid.priorSource === 'stub') {
    return {
      label: '⚠️ AI 미연결 — 연령·유형 평균 지도입니다',
      a11y: '이 지도는 개인 맞춤 예측이 아닙니다. AI가 연결되지 않아 연령·유형 평균으로 표시됩니다.',
    };
  }
  if (grid.priorSource === 'fallback') {
    return {
      label: '⚠️ AI 예측 실패 — 연령·유형 평균 지도입니다',
      a11y: '이 지도는 개인 맞춤 예측이 아닙니다. AI 예측에 실패해 연령·유형 평균으로 표시됩니다.',
    };
  }
  // 도로망 폴백은 개인화는 살아 있고 지형 제약만 빠진 상태다 — 문구를 구분한다.
  if (!grid.roadnetUsed && grid.roadnetFallbackReason !== 'off') {
    return {
      label: '⚠️ 도로망 미적용 — 길 따라 걷는 제약이 빠진 지도입니다',
      a11y: '도로망을 불러오지 못해 길 제약 없이 계산된 예측입니다. 실제 이동 가능 범위와 다를 수 있습니다.',
    };
  }
  return null;
}

export default function SearchScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const theme = useModeTheme();
  // 표시 컴포넌트에 넘길 데이터는 화면이 가져온다(디자인 교체 대비).
  const mode = useAppModeStore((s) => s.mode);
  const severity = useAppModeStore((s) => s.severity);
  const profile = useMissingPersonStore((s) => s.profile);
  // 서버 경보가 있으면 그쪽이 진실이다 — 스토어는 목업 상수를 들고 있어
  // 실제 신고가 82세여도 78세로 보인다(2026-08-05 실측).
  const { data: liveAlerts } = useActiveAlerts();
  const liveAlert = liveAlerts?.[0];
  // **살아있는 경보의 케이스를 본다.** 종전에는 DEMO_CASE_ID 가 박혀 있어, 그
  // 데모 케이스를 지우면 화면이 404 를 붙들고 "지도를 불러오지 못했어요"를 띄운
  // 채 프로필은 목업으로 폴백했다(2026-08-05 실측 — 제목 78세·부제 82세 모순).
  // 수색 안내(#125)도 같은 케이스를 봐야 한다 — 지도는 실제 사건, 안내 문구는
  // 데모 케이스로 갈리면 "어디를 보라"가 다른 사람 기준이 된다.
  const caseId = liveAlert?.caseId ?? DEMO_CASE_ID;
  const watching = usePresenceCount(caseId);
  /** 사용자가 누른 셀 — 확률을 띄우기 위한 것뿐이라 화면 안에서만 산다. */
  const [pickedCell, setPickedCell] = useState<PoaCell | null>(null);
  const guidance = useGuidance(caseId).data?.text ?? '';
  const role = useAuthStore((s) => s.role);
  const golden = useGoldenTime();
  const [axis, setAxis] = useState<TimeAxis>(0);
  const poa = usePoaPrediction(caseId, axis);
  const degraded = degradedNotice(poa.data);
  const freshness = freshnessLabel(poa.data);

  // 최종 목격 위치도 경보에서 받는다 — LAST_SEEN 은 목업 좌표라 실제 신고와 다르다.
  const lastSeen = liveAlert?.lkp ?? LAST_SEEN;
  const grid = poa.data;
  const cumPct = grid ? Math.round(grid.cumulative * 100) : null;
  const elapsedMin = golden ? Math.floor(golden.elapsedSec / 60) : null;

  // 실측 내 위치 — 지도 마커는 OS(showsUserLocation)에 맡기고, 거리·도보시간만 직접 쓴다.
  const { point: myPoint, status: locStatus } = useMyLocation();
  const located = locStatus === 'granted' && myPoint != null;
  // 거리(m·분) 대신 "예측 구역 안/밖 + 확률 등급" — 근거는 utils/areaStatus.ts.
  // 실경보가 있으면 그 사건 기준, 없으면 데모 사건(caseId 는 위에서 정해진다).
  const area = useAreaStatus(caseId);

  const mapA11y = grid
    ? `발견 확률 히트맵. 최고 구역 ${grid.topLabel}. 누적 발견확률 ${cumPct}%. 최종 목격 위치와 ${
        located ? '현재 위치, ' : ''
      }내가 확인할 구역이 표시돼 있어요.`
    : '발견 확률 지도를 불러오는 중입니다.';

  const onReport = () => navigation.navigate('ReportChat', { caseId });

  return (
    <View style={styles.root}>
      <StatusBar style="dark" />

      {/* ── 지도 레이어 (전면) ─────────────────────────── */}
      <View style={styles.mapLayer}>
        {/* 웹(폰 브라우저·홈 화면 설치본)에서는 BaseMap 이 자리표시자라 지도가
            회색으로만 보였다. 실제 타일맵으로 그리고, 폰에는 마우스 오버가 없으니
            **셀을 누르면 확률을 띄우고 손가락으로 밀 수 있게** 한다(요청 08-11). */}
        {Platform.OS === 'web' ? (
          <WebMap
            style={styles.mapFill}
            center={lastSeen}
            grid={grid ?? undefined}
            marker={lastSeen}
            zoom={15}
            pannable
            onCellPress={setPickedCell}
            accessibilityLabel={mapA11y}
          />
        ) : (
        <BaseMap style={styles.mapFill} accessibilityLabel={mapA11y} showsUserLocation={located}>
          {grid ? <PoaHeatmap grid={grid} /> : null}
          <PredictionRadius center={lastSeen} radiusM={ZONE_RADIUS_M} color={theme.accent} />
          <MapPin
            kind="lastSeen"
            coordinate={lastSeen}
            title="최종 목격 위치"
            description="정릉동 주민센터, 오후 3시 10분경"
          />
          {/* 내 위치 마커는 OS 기본(showsUserLocation)에 맡긴다 — 방향·불확실성까지
              센서융합으로 그려주고, 측위 실패 시 가짜 좌표를 찍지 않는다. */}
        </BaseMap>
        )}

        {/* 누른 셀의 발견확률 — 지도 위에 작은 알림으로 띄운다. 다시 누르면 사라진다. */}
        {pickedCell ? (
          <Pressable style={styles.cellCallout} onPress={() => setPickedCell(null)} accessibilityRole="button">
            <Text style={styles.cellCalloutTitle}>이 구역 발견확률</Text>
            <Text style={styles.cellCalloutValue}>{(pickedCell.prob * 100).toFixed(1)}%</Text>
            <Text style={styles.cellCalloutHint}>눌러서 닫기</Text>
          </Pressable>
        ) : null}
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
            accessibilityLabel={`내가 확인할 구역. ${area.label}. 누적 발견확률 ${cumPct}퍼센트.`}
          >
            <View style={styles.zonePill}>
              <View style={[styles.zoneDot, { backgroundColor: theme.accent }]} />
              <Text style={styles.zonePillText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                내가 확인할 구역
              </Text>
            </View>
            <View style={[styles.distChip, { backgroundColor: theme.accent }]}>
              <Text style={styles.distText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                {area.short ? `${area.short} · ` : ''}누적 {cumPct}%
              </Text>
            </View>
          </View>

          <View style={[styles.legendFloat, { top: insets.top + 60 }]}>
            <HeatLegend compact />
          </View>

          <View style={[styles.timeAxis, { top: insets.top + 96 }]}>
            {TIME_STOPS.map((stop) => {
              const on = stop.t === axis;
              return (
                <Pressable
                  key={stop.label}
                  onPress={() => setAxis(stop.t)}
                  accessibilityRole="button"
                  accessibilityState={{ selected: on }}
                  accessibilityLabel={`경과 ${stop.label} 시점 지도 보기`}
                  style={[styles.timeChip, on && { backgroundColor: theme.accent }]}
                >
                  <Text
                    style={[styles.timeChipText, on && styles.timeChipTextOn]}
                    allowFontScaling
                    maxFontSizeMultiplier={type.maxScale}
                  >
                    {stop.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          {freshness ? (
            <View
              style={[styles.freshnessChip, { top: insets.top + 20 }]}
              pointerEvents="none"
              accessible
              accessibilityLabel={`이 지도는 ${freshness}된 예측입니다`}
            >
              <Text
                style={styles.freshnessText}
                allowFontScaling
                maxFontSizeMultiplier={type.maxScale}
              >
                {freshness}
              </Text>
            </View>
          ) : null}

          {/* 예측 품질이 떨어진 상태를 숨기지 않는다. 두 폴백 다 조용해서
              (POA·지도는 정상으로 나온다) 표시하지 않으면 통계 평균이나 도로
              제약 없는 예측을 "AI 예측"으로 보여주게 된다. */}
          {degraded ? (
            <View
              style={[styles.degradedBanner, { top: insets.top + 110 }]}
              accessible
              accessibilityLabel={`주의. ${degraded.a11y}`}
            >
              <Text
                style={styles.degradedText}
                allowFontScaling
                maxFontSizeMultiplier={type.maxScale}
              >
                {degraded.label}
              </Text>
            </View>
          ) : null}
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

        {/* 앱 안 시민 화면 — 실명·나이는 노출, 진단명은 제외(#125).
            데이터는 실제 경보 우선, 없으면 목업 — 실데이터 경로에는 아직 이름이
            없다(알림 payload 가 익명화로 이름을 빼고 내려온다). 후속 과제. */}
        <MissingPersonCard
          view={liveAlert ? alertToView(liveAlert) : toCitizenView(profile)}
          variant="compact"
          showAppearanceChips
        />

        {/* 수색 안내 — "어디를 봐야 하는지". 이 화면에 없던 정보다(지도와 인상착의는
            있어도 행동 지시가 없었다). 서버가 페르소나에서 만들어 내려준다.
            문구가 없거나 조회 실패면 조용히 사라진다 — 지도·인상착의가 본질이고
            안내는 보탬이라, 이것 때문에 에러 UI 를 띄울 이유가 없다. */}
        {guidance ? (
          <View
            style={[styles.guidanceCard, { backgroundColor: theme.accentWash }]}
            accessible
            accessibilityLabel={`수색 안내. ${guidance}`}
          >
            <Text style={styles.guidanceIcon} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              🔎
            </Text>
            <Text
              style={[styles.guidanceText, { color: theme.accentInk }]}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
            >
              {guidance}
            </Text>
          </View>
        ) : null}

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

        {/* 운영자 안내는 제거됐다 — 관제는 앱이 아니라 백엔드 /dashboard 웹 화면이 맡는다
            (와이어프레임 2026-08-05, 역할은 시민·보호자 둘). */}
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
  // 누른 셀의 확률을 지도 위에 띄우는 알림.
  cellCallout: {
    position: 'absolute', left: 16, top: 16, minWidth: 136,
    borderRadius: 12, paddingVertical: 10, paddingHorizontal: 14,
    backgroundColor: 'rgba(255,255,255,0.96)',
  },
  cellCalloutTitle: { fontFamily: type.family, fontSize: 11, lineHeight: 14, color: '#8E8E93' },
  cellCalloutValue: { fontFamily: type.familyBold, fontSize: 20, lineHeight: 26, color: '#000000', marginTop: 2 },
  cellCalloutHint: { fontFamily: type.family, fontSize: 10, lineHeight: 13, color: '#B0B0B5', marginTop: 2 },
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
    color: color.textBody,
    fontFamily: type.familyBold,
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
    fontFamily: type.familyBold,
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
    color: color.text,
    fontFamily: type.familyExtraBold,
  },
  distChip: {
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
  distText: {
    fontSize: type.size.label,
    color: color.surface,
    fontFamily: type.familyExtraBold,
  },

  legendFloat: { position: 'absolute', right: space.lg },

  timeAxis: {
    position: 'absolute',
    left: space.lg,
    right: space.lg,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  timeChip: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: radius.pill,
    backgroundColor: hexToRgba(color.surface, 0.92),
    borderWidth: 1,
    borderColor: color.border,
  },
  timeChipText: {
    fontSize: type.size.caption,
    color: color.textBody,
    fontFamily: type.familyBold,
  },
  timeChipTextOn: { color: '#FFFFFF' },

  freshnessChip: {
    position: 'absolute',
    left: space.lg,
    backgroundColor: hexToRgba(color.text, 0.72),
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: 4,
  },
  freshnessText: {
    fontSize: type.size.caption,
    color: '#FFFFFF',
    fontFamily: type.familyBold,
  },

  degradedBanner: {
    position: 'absolute',
    left: space.lg,
    right: space.lg,
    backgroundColor: color.critical,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  degradedText: {
    fontSize: type.size.caption,
    color: '#FFFFFF',
    fontFamily: type.familyBold,
    textAlign: 'center',
  },

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
    color: color.textBody,
    fontFamily: type.familyBold,
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
  // 수색 안내 카드 — '수색 진행' 요소라 앰버 계열 워시(§4.1). 심각도색 아님.
  guidanceCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.sm,
    borderRadius: radius.lg,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  guidanceIcon: { fontSize: 15, lineHeight: 21 },
  guidanceText: {
    flex: 1,
    fontSize: type.size.label,
    fontFamily: type.familySemiBold,
    lineHeight: 21,
  },

  sheetKicker: {
    fontSize: type.size.label,
    color: color.text,
    fontFamily: type.familyExtraBold,
  },

  lastSeenRow: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  lastSeenIcon: { fontSize: 15 },
  lastSeenText: {
    flex: 1,
    fontSize: type.size.label,
    fontFamily: type.familyBold,
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
    fontFamily: type.familySemiBold,
    lineHeight: 22,
  },
  info112Strong: { fontFamily: type.familyExtraBold },

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
    color: color.surface,
    fontFamily: type.familyCssExtraBold,
  },

  pressed: { opacity: 0.9 },
});
