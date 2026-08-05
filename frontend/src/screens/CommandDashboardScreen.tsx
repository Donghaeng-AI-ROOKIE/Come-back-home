/**
 * 운영자 지휘 대시보드 (CONTRACT #9 / spec §3.4·§4.2). OPERATOR DARK(operatorTheme).
 * command-content.dc.html 목업 재현 — 다크 맵 포워드 셸 + 플로팅 크롬 + 하단 세그먼트 3뷰.
 *
 * 목업 대비 정정(NOT 1:1):
 *  · 헤더 실종자 = 단일 소스(useMissingPersonStore) 78세 여성 김순자 — 목업 "남성" 버그 제거.
 *  · 지도 = 라벨없는 SVG blob → 실 타일맵 BaseMap + POA 폴리곤 히트맵(§4.5). 범례·게이지는 오버레이.
 *  · POA 범례 = 4단계 색+명도+패턴 이중부호화 HeatLegend(§4.2). 목업 3단계(색만) 대체.
 *  · 골든타임 = 대시보드 진행 타이머라 앰버(searching, §4.1). 세그먼트 활성도 앰버.
 *  · 클릭 div → Pressable + role/label. 정보 그래픽에 accessibilityLabel.
 *  · onBack/onFound/onMetrics 셸 핸들러 → OperatorStack 네비게이션으로 매핑.
 *
 * 세그먼트 3뷰 — 예측(POA 히트맵+시간축) / 근거(추론 타임라인+POI) / 교차검증(마음·몸 격자).
 * 하단(운영자 전용): 발견 완료 처리 → CaseFound, 검증 리포트 → ValidationReport.
 */
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import { color, radius, space, type } from '../theme/tokens';
import { operatorTheme } from '../theme/theme';
import { poaMeta } from '../theme/poa';
import { hexToRgba } from '../utils/color';
import type { TimeAxis } from '../types/domain';
import type { OperatorStackParamList } from '../navigation/types';
import { DEMO_CASE_ID, LAST_SEEN } from '../data/missing';
import { POIS, REASON_TIMELINE } from '../data/mock';
import { useCrossValidation, usePoaPrediction, useGoldenTime } from '../hooks/queries';
import { useMissingPersonStore } from '../store/missingPersonStore';
import { useAppModeStore } from '../store/appModeStore';

import BaseMap from '../components/BaseMap';
import PoaHeatmap from '../components/PoaHeatmap';
import MapPin from '../components/MapPin';
import HeatLegend from '../components/HeatLegend';
import TimeAxisSlider from '../components/TimeAxisSlider';
import SegmentedControl from '../components/SegmentedControl';
import GoldenTimeChip from '../components/GoldenTimeChip';
import ReasonTimeline from '../components/ReasonTimeline';
import PoiProbCard from '../components/PoiProbCard';
import CrossValMiniGrid from '../components/CrossValMiniGrid';

type ViewKey = 'predict' | 'reason' | 'crossval';

const SEGMENTS: { key: ViewKey; label: string }[] = [
  { key: 'predict', label: '예측' },
  { key: 'reason', label: '근거' },
  { key: 'crossval', label: '교차검증' },
];

// 목업의 반투명 다크 플로팅 카드 = operatorSurface에서 토큰 파생(색은 tokens.ts만).
const FLOAT_BG = hexToRgba(color.operatorSurface, 0.9);
const CHIP_BG = hexToRgba(color.search, 0.2);
const TRACK_BG = hexToRgba(color.operatorText, 0.16);
const MISMATCH_BG = hexToRgba(color.critical, 0.14);
const MISMATCH_BORDER = hexToRgba(color.critical, 0.34);

// 그라디언트 스톱은 모두 토큰(발견=산책 그린 램프, 게이지=저 앰버→수색 앰버 램프).
const FOUND_GRADIENT: readonly [string, string] = [color.walk, color.walkInk];
const GAUGE_GRADIENT: readonly [string, string] = [poaMeta.low.fill, color.search];

export default function CommandDashboardScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<OperatorStackParamList>>();
  const profile = useMissingPersonStore((s) => s.profile);

  // 운영자 대시보드는 활성 사건을 지휘 중 — 골든타임이 흐르도록 수색 모드 보장.
  // (이미 진행 중이면 enteredSearchAt을 리셋하지 않음 → 카운트다운 유지)
  const mode = useAppModeStore((s) => s.mode);
  const enterSearch = useAppModeStore((s) => s.enterSearch);
  useEffect(() => {
    if (mode !== 'search') enterSearch(DEMO_CASE_ID, 'critical');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [view, setView] = useState<ViewKey>('predict');
  const [t, setT] = useState<TimeAxis>(1);

  const poa = usePoaPrediction(DEMO_CASE_ID, t);
  const cv = useCrossValidation(DEMO_CASE_ID);
  // 표시 컴포넌트에 넘길 데이터는 화면이 가져온다(디자인 교체 대비).
  const goldenTime = useGoldenTime();

  const grid = poa.data;
  const sexLabel = profile.sex === 'F' ? '여성' : '남성';
  const cumPct = grid ? Math.round(grid.cumulative * 100) : 0;
  const radiusKm = (0.6 + t * 0.55).toFixed(1);

  const mapLabel = grid
    ? `발견확률 히트맵. 최고 구역 ${grid.topLabel}. 누적 발견확률 ${cumPct}퍼센트. 경과 ${t}시간, 예측 반경 약 ${radiusKm}킬로미터.`
    : '발견확률 히트맵 불러오는 중';

  const cvData = cv.data;
  const agreementPct = cvData ? Math.round(cvData.agreement * 100) : 0;
  const jsdText = cvData ? cvData.jsd.toFixed(3) : '—';

  const goFound = () => navigation.navigate('CaseFound');
  const goValidation = () => navigation.navigate('ValidationReport');

  const gait = profile.appearance.includes('지팡이') ? '지팡이·느림' : '보통';

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />

      {/* ── 헤더: 실루엣 + 실종자 단일 소스(78세 여성 김순자) + 골든타임(앰버) ── */}
      <View style={styles.header}>
        <View
          style={styles.avatar}
          accessible
          accessibilityRole="image"
          accessibilityLabel="실종자 실루엣"
        >
          <Text style={styles.avatarGlyph} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {'👤'}
          </Text>
        </View>

        <View
          style={styles.headerText}
          accessible
          accessibilityLabel={`실종 수색 지휘. ${profile.name}, ${profile.age}세 ${sexLabel}, ${profile.cognition}.`}
        >
          <View style={styles.eyebrowRow}>
            <View style={styles.sevDot} />
            <Text
              style={styles.eyebrow}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
              numberOfLines={1}
            >
              실종 수색 지휘 · 진행 중
            </Text>
          </View>
          <Text
            style={styles.caseTitle}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
            numberOfLines={1}
          >
            {`${profile.age}세 ${sexLabel} · ${profile.name}`}
          </Text>
          <Text
            style={styles.caseSub}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
            numberOfLines={1}
          >
            {`${profile.cognition} · ${profile.appearance[0]} · ${profile.area}`}
          </Text>
        </View>

        <GoldenTimeChip goldenTime={goldenTime} dark emphasis="searching" />
      </View>

      <SegmentedControl
        segments={SEGMENTS}
        value={view}
        onChange={(key) => setView(key as ViewKey)}
        accent={operatorTheme.accent}
        dark
      />

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        {/* ══ 예측: 실지도 + POA 히트맵 + 최종목격 핀 + 플로팅 범례/게이지 + 시간축 ══ */}
        {view === 'predict' && (
          <View>
            <View style={styles.mapWrap}>
              {grid ? (
                <>
                  <BaseMap
                    style={StyleSheet.absoluteFill}
                    scrollEnabled={false}
                    accessibilityLabel={mapLabel}
                  >
                    <PoaHeatmap grid={grid} />
                    <MapPin
                      kind="lastSeen"
                      coordinate={LAST_SEEN}
                      title="최종 목격"
                      description={profile.lastSeen}
                    />
                  </BaseMap>

                  {/* 좌상단 플로팅 POA 범례 (색+명도+패턴 4단계) */}
                  <View style={styles.legendFloat} pointerEvents="none">
                    <HeatLegend dark compact />
                  </View>

                  {/* 우상단 플로팅 누적 발견 확률 게이지 */}
                  <View
                    style={styles.gaugeFloat}
                    accessible
                    accessibilityRole="image"
                    accessibilityLabel={`누적 발견 확률 ${cumPct}퍼센트. 수색팀 3, 제보 2건.`}
                    pointerEvents="none"
                  >
                    <Text
                      style={styles.gaugeCap}
                      allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}
                    >
                      누적 발견 확률
                    </Text>
                    <View style={styles.gaugeNumRow}>
                      <Text
                        style={styles.gaugeNum}
                        allowFontScaling
                        maxFontSizeMultiplier={type.maxScale}
                      >
                        {String(cumPct)}
                      </Text>
                      <Text
                        style={styles.gaugePct}
                        allowFontScaling
                        maxFontSizeMultiplier={type.maxScale}
                      >
                        %
                      </Text>
                    </View>
                    <View style={styles.gaugeTrack}>
                      <LinearGradient
                        colors={GAUGE_GRADIENT}
                        start={{ x: 0, y: 0 }}
                        end={{ x: 1, y: 0 }}
                        style={[styles.gaugeFill, { width: `${Math.max(4, cumPct)}%` }]}
                      />
                    </View>
                    <Text
                      style={styles.gaugeSub}
                      allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}
                    >
                      수색팀 3 · 제보 2건
                    </Text>
                  </View>
                </>
              ) : (
                <View
                  style={styles.mapLoading}
                  accessible
                  accessibilityRole="image"
                  accessibilityLabel={poa.isError ? '예측을 불러오지 못했어요' : mapLabel}
                >
                  {poa.isError ? (
                    <Text
                      style={styles.loadingText}
                      allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}
                    >
                      예측을 불러오지 못했어요
                    </Text>
                  ) : (
                    <>
                      <ActivityIndicator color={operatorTheme.accent} />
                      <Text
                        style={styles.loadingText}
                        allowFontScaling
                        maxFontSizeMultiplier={type.maxScale}
                      >
                        AI 예측 지도를 불러오는 중…
                      </Text>
                    </>
                  )}
                </View>
              )}
            </View>

            {/* 예측 시트: 이동 구역 헤더 + 경과/반경 칩 + 시간축 슬라이더 */}
            <View style={styles.predictSheet}>
              <View style={styles.sheetHead}>
                <Text
                  style={styles.sheetTitle}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  AI 예측 이동 구역
                </Text>
                <View
                  style={styles.rangeChip}
                  accessible
                  accessibilityLabel={`경과 ${t}시간, 예측 반경 약 ${radiusKm}킬로미터`}
                >
                  <Text
                    style={styles.rangeChipText}
                    allowFontScaling
                    maxFontSizeMultiplier={type.maxScale}
                    numberOfLines={1}
                  >
                    {`경과 ${t}h · 반경 ${radiusKm}km`}
                  </Text>
                </View>
              </View>

              <View style={styles.sliderWrap}>
                <TimeAxisSlider value={t} onChange={setT} accent={operatorTheme.accent} dark />
              </View>

              <Text
                style={styles.sheetHint}
                allowFontScaling
                maxFontSizeMultiplier={type.maxScale}
              >
                시간이 지날수록 예측 구역이 넓어지고 이동해요
              </Text>
            </View>
          </View>
        )}

        {/* ══ 근거: 페르소나 카드 + 이동 의도 추론 타임라인 + 목표 후보 POI ══ */}
        {view === 'reason' && (
          <View>
            <Text style={styles.panelTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              왜 이 경로인가
            </Text>
            <Text style={styles.panelSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              AI가 이 구역을 높게 본 근거예요
            </Text>

            {/* 페르소나 카드 (단일 소스 파생: 관계·인지단계·보행능력) */}
            <View style={styles.personaCard}>
              <View style={styles.personaCol}>
                <Text
                  style={styles.personaKey}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  관계
                </Text>
                <Text
                  style={styles.personaVal}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  {profile.rel}
                </Text>
              </View>
              <View style={styles.personaDivider} />
              <View style={styles.personaCol}>
                <Text
                  style={styles.personaKey}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  인지 단계
                </Text>
                <Text
                  style={[styles.personaVal, styles.personaValAccent]}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  {profile.cognition}
                </Text>
              </View>
              <View style={styles.personaDivider} />
              <View style={styles.personaCol}>
                <Text
                  style={styles.personaKey}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  보행 능력
                </Text>
                <Text
                  style={styles.personaVal}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  {gait}
                </Text>
              </View>
            </View>

            <Text
              style={[styles.blockLabel, styles.blockLabelSpaced]}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
            >
              이동 의도 추론
            </Text>
            <View style={styles.card}>
              <ReasonTimeline steps={REASON_TIMELINE} dark />
            </View>

            <Text
              style={[styles.blockLabel, styles.blockLabelSpaced]}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
            >
              목표 후보 장소 (POA)
            </Text>
            {POIS.map((poi, i) => (
              <View key={poi.id} style={styles.poiRow}>
                <PoiProbCard poi={poi} rank={i + 1} dark />
              </View>
            ))}
          </View>
        )}

        {/* ══ 교차검증: 마음/몸 격자 + 일치도 링 + JSD + 불일치 안내 ══ */}
        {view === 'crossval' && (
          <View>
            {cvData ? (
              <>
                <View style={styles.cvGrids}>
                  <View style={styles.cvGridCard}>
                    <View style={styles.cvGridBody}>
                      <CrossValMiniGrid title="마음" cells={cvData.mind} dark />
                    </View>
                    <Text
                      style={styles.cvGridSub}
                      allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}
                    >
                      LLM 개인화 예측
                    </Text>
                  </View>
                  <View style={styles.cvGridCard}>
                    <View style={styles.cvGridBody}>
                      <CrossValMiniGrid title="몸" cells={cvData.body} dark />
                    </View>
                    <Text
                      style={styles.cvGridSub}
                      allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}
                    >
                      고전 POA 커버리지
                    </Text>
                  </View>
                </View>

                <View
                  style={styles.cvSummary}
                  accessible
                  accessibilityLabel={`마음·몸 예측 일치도 ${agreementPct}퍼센트. 이동분포 유사도 JSD ${jsdText}, 완전일치에 가까움.`}
                >
                  <View style={styles.ring}>
                    <Text
                      style={styles.ringNum}
                      allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}
                    >
                      {`${agreementPct}%`}
                    </Text>
                    <Text
                      style={styles.ringCap}
                      allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}
                    >
                      일치도
                    </Text>
                  </View>
                  <View style={styles.cvSummaryText}>
                    <Text
                      style={styles.cvHeadline}
                      allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}
                    >
                      마음 · 몸 예측 일치도
                    </Text>
                    <Text
                      style={styles.cvSub}
                      allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}
                    >
                      {`두 모델이 겹치는 구역일수록 신뢰도가 높아요\n이동분포 유사도 JSD ${jsdText} · 완전일치에 가까움`}
                    </Text>
                  </View>
                </View>

                <View
                  style={styles.mismatchNote}
                  accessible
                  accessibilityLabel="불일치 구간: 마음은 옛집 방향, 몸은 전방위 확산. 북동측 우선 확인 권장."
                >
                  <View style={styles.mismatchSwatch} />
                  <Text
                    style={styles.mismatchText}
                    allowFontScaling
                    maxFontSizeMultiplier={type.maxScale}
                  >
                    <Text style={styles.mismatchStrong}>불일치 구간</Text>
                    {' — 마음은 '}
                    <Text style={styles.mismatchAccent}>옛집 방향</Text>
                    {', 몸은 '}
                    <Text style={styles.mismatchStrong}>전방위 확산</Text>
                    {'. 북동측 우선 확인 권장'}
                  </Text>
                </View>
              </>
            ) : (
              <View
                style={styles.cvLoading}
                accessible
                accessibilityRole="image"
                accessibilityLabel={cv.isError ? '교차검증을 불러오지 못했어요' : '교차검증 불러오는 중'}
              >
                {cv.isError ? (
                  <Text
                    style={styles.loadingText}
                    allowFontScaling
                    maxFontSizeMultiplier={type.maxScale}
                  >
                    교차검증을 불러오지 못했어요
                  </Text>
                ) : (
                  <>
                    <ActivityIndicator color={operatorTheme.accent} />
                    <Text
                      style={styles.loadingText}
                      allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}
                    >
                      교차검증 계산 중…
                    </Text>
                  </>
                )}
              </View>
            )}
          </View>
        )}
      </ScrollView>

      {/* ── 하단 액션바 — 운영자 전용 ── */}
      <View style={styles.actionBar}>
        <Pressable
          onPress={goFound}
          accessibilityRole="button"
          accessibilityLabel="발견 완료 처리"
          accessibilityHint="사건을 발견 완료로 종료합니다"
          style={({ pressed }) => [styles.actionBtn, styles.foundBtn, pressed && styles.pressed]}
        >
          <LinearGradient
            colors={FOUND_GRADIENT}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={StyleSheet.absoluteFill}
          />
          <Text
            style={styles.foundGlyph}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
          >
            ✓
          </Text>
          <Text
            style={styles.foundLabel}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
            numberOfLines={1}
          >
            발견 완료 처리
          </Text>
        </Pressable>

        <Pressable
          onPress={goValidation}
          accessibilityRole="button"
          accessibilityLabel="검증 리포트"
          accessibilityHint="검증 수치 리포트를 봅니다"
          style={({ pressed }) => [styles.actionBtn, styles.metricsBtn, pressed && styles.pressed]}
        >
          <Text
            style={styles.metricsGlyph}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
          >
            ▊
          </Text>
          <Text
            style={styles.metricsLabel}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
            numberOfLines={1}
          >
            검증 리포트
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: operatorTheme.bg },

  // ── 헤더 ──
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    paddingBottom: space.md,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: operatorTheme.surfaceAlt,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: space.md,
  },
  avatarGlyph: { fontSize: 22, textAlign: 'center', fontFamily: type.family },
  headerText: { flex: 1, marginRight: space.md },
  eyebrowRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 2 },
  sevDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: color.critical,
    marginRight: space.xs,
  },
  eyebrow: {
    flex: 1,
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
    color: operatorTheme.textSec,
    letterSpacing: 0.2,
  },
  caseTitle: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    color: operatorTheme.text,
  },
  caseSub: {
    marginTop: 2,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    color: operatorTheme.textSec,
  },

  scroll: { flex: 1 },
  scrollContent: {
    paddingHorizontal: space.lg,
    paddingTop: space.lg,
    paddingBottom: space.xl,
  },

  // ── 예측: 지도 + 플로팅 오버레이 ──
  mapWrap: {
    height: 360,
    borderRadius: radius.lg,
    overflow: 'hidden',
    position: 'relative',
  },
  mapLoading: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
  },
  loadingText: {
    marginTop: space.sm,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    color: operatorTheme.textSec,
    textAlign: 'center',
  },
  legendFloat: {
    position: 'absolute',
    top: space.md,
    left: space.md,
  },
  gaugeFloat: {
    position: 'absolute',
    top: space.md,
    right: space.md,
    minWidth: 132,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: FLOAT_BG,
  },
  gaugeCap: {
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
    color: operatorTheme.textSec,
    letterSpacing: 0.2,
  },
  gaugeNumRow: { flexDirection: 'row', alignItems: 'baseline', marginTop: 2 },
  gaugeNum: {
    fontSize: type.size.bigNum,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
    color: operatorTheme.text,
    letterSpacing: -0.5,
  },
  gaugePct: {
    marginLeft: 2,
    fontSize: type.size.body,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
    color: operatorTheme.textSec,
  },
  gaugeTrack: {
    marginTop: space.sm,
    height: 8,
    borderRadius: radius.pill,
    backgroundColor: TRACK_BG,
    overflow: 'hidden',
  },
  gaugeFill: { height: '100%', borderRadius: radius.pill },
  gaugeSub: {
    marginTop: space.xs,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    color: operatorTheme.textSec,
  },

  // ── 예측 시트 ──
  predictSheet: {
    marginTop: space.lg,
    padding: space.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
  },
  sheetHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sheetTitle: {
    flex: 1,
    marginRight: space.md,
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    color: operatorTheme.text,
  },
  rangeChip: {
    flexShrink: 0,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    borderRadius: radius.pill,
    backgroundColor: CHIP_BG,
  },
  rangeChipText: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
    color: operatorTheme.text,
  },
  sliderWrap: { marginTop: space.lg },
  sheetHint: {
    marginTop: space.md,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    color: operatorTheme.textSec,
    textAlign: 'center',
  },

  // ── 근거 ──
  panelTitle: {
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    color: operatorTheme.text,
  },
  panelSub: {
    marginTop: space.xs,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    color: operatorTheme.textSec,
  },
  personaCard: {
    flexDirection: 'row',
    marginTop: space.lg,
    padding: space.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
  },
  personaCol: { flex: 1, alignItems: 'center' },
  personaDivider: { width: 1, backgroundColor: operatorTheme.border, marginHorizontal: space.sm },
  personaKey: {
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
    color: operatorTheme.textSec,
  },
  personaVal: {
    marginTop: space.xs,
    fontSize: type.size.body,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    color: operatorTheme.text,
    textAlign: 'center',
  },
  personaValAccent: { color: color.search },

  blockLabel: {
    marginBottom: space.md,
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    color: operatorTheme.text,
  },
  blockLabelSpaced: { marginTop: space.xl },

  card: {
    padding: space.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
  },
  poiRow: { marginBottom: space.md },

  // ── 교차검증 ──
  cvGrids: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  cvGridCard: {
    flex: 1,
    marginHorizontal: space.xs,
    padding: space.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
  },
  cvGridSub: {
    marginTop: space.sm,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    color: operatorTheme.textSec,
    textAlign: 'center',
  },
  cvGridBody: { alignItems: 'center' },

  cvSummary: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: space.lg,
    padding: space.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
  },
  ring: {
    width: 88,
    height: 88,
    borderRadius: 44,
    borderWidth: 5,
    borderColor: operatorTheme.accent,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: operatorTheme.surfaceAlt,
  },
  ringNum: {
    fontSize: type.size.bigNum,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
    color: operatorTheme.text,
  },
  ringCap: {
    marginTop: 2,
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
    color: operatorTheme.textSec,
  },
  cvSummaryText: { flex: 1, marginLeft: space.lg },
  cvHeadline: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    color: operatorTheme.text,
  },
  cvSub: {
    marginTop: space.xs,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
    color: operatorTheme.textSec,
    lineHeight: 22,
  },

  mismatchNote: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: space.md,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: MISMATCH_BORDER,
    backgroundColor: MISMATCH_BG,
  },
  mismatchSwatch: {
    flexShrink: 0,
    width: 20,
    height: 12,
    borderRadius: radius.sm,
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: operatorTheme.text,
    marginRight: space.md,
  },
  mismatchText: {
    flex: 1,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    color: operatorTheme.text,
    lineHeight: 22,
  },
  mismatchStrong: { fontWeight: type.weight.black },
  mismatchAccent: { fontWeight: type.weight.black, color: color.search },

  cvLoading: {
    minHeight: 200,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
  },

  // ── 하단 액션바 ──
  actionBar: {
    flexDirection: 'row',
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.md,
    borderTopWidth: 1,
    borderTopColor: operatorTheme.border,
    backgroundColor: operatorTheme.bg,
  },
  actionBtn: {
    flex: 1,
    minHeight: 56,
    borderRadius: radius.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  pressed: { opacity: 0.85 },
  foundBtn: {
    shadowColor: color.walk,
    shadowOpacity: 0.4,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 5,
  },
  foundGlyph: {
    fontSize: type.size.body,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    color: '#FFFFFF',
    marginRight: space.sm,
  },
  foundLabel: {
    fontSize: type.size.body,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    color: '#FFFFFF',
  },
  metricsBtn: {
    marginLeft: space.md,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
  },
  metricsGlyph: {
    fontSize: type.size.body,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    color: color.search,
    marginRight: space.sm,
  },
  metricsLabel: {
    fontSize: type.size.body,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    color: operatorTheme.text,
  },
});
