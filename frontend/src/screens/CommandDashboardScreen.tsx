/**
 * 운영자 지휘 대시보드 (CONTRACT #9 / spec §3.4·§4.2). OPERATOR DARK(operatorTheme).
 * 헤더: 사건 타이틀 + 실종자 단일 소스 라벨(절대 "남성" 아님) + 골든타임 칩(dark).
 * 세그먼트 3뷰 — 예측(POA 히트맵+시간축) / 근거(추론 타임라인+POI) / 교차검증(마음·몸 격자).
 * 지도는 §4.5대로 라이트/그레이스케일 고정, 다크 대시보드여도 히트맵 대비 확보.
 * 하단(운영자 전용): 발견 처리 → CaseFound, 검증 수치 → ValidationReport.
 */
import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import { color, radius, space, type } from '../theme/tokens';
import { operatorTheme } from '../theme/theme';
import type { TimeAxis } from '../types/domain';
import type { OperatorStackParamList } from '../navigation/types';
import { DEMO_CASE_ID, LAST_SEEN } from '../data/missing';
import { POIS, REASON_TIMELINE } from '../data/mock';
import { useCrossValidation, usePoaPrediction } from '../hooks/queries';
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
import CTAButton from '../components/CTAButton';

type ViewKey = 'predict' | 'reason' | 'crossval';

const SEGMENTS: { key: ViewKey; label: string }[] = [
  { key: 'predict', label: '예측' },
  { key: 'reason', label: '근거' },
  { key: 'crossval', label: '교차검증' },
];

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
  const [t, setT] = useState<TimeAxis>(0);

  const poa = usePoaPrediction(DEMO_CASE_ID, t);
  const cv = useCrossValidation(DEMO_CASE_ID);

  const grid = poa.data;
  const mapLabel = grid
    ? `발견확률 히트맵. 최고 구역 ${grid.topLabel}. 누적 발견확률 ${Math.round(
        grid.cumulative * 100,
      )}퍼센트. 경과 ${t}시간 기준.`
    : '발견확률 히트맵 불러오는 중';

  const cvData = cv.data;
  const agreementPct = cvData ? Math.round(cvData.agreement * 100) : 0;
  const jsdText = cvData ? cvData.jsd.toFixed(3) : '—';

  const goFound = () => navigation.navigate('CaseFound');
  const goValidation = () => navigation.navigate('ValidationReport');

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />

      {/* 헤더 — 사건 타이틀 + 실종자 단일 소스 라벨 + 골든타임 */}
      <View style={styles.header}>
        <View style={styles.headerTop}>
          <Text
            style={styles.caseTitle}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
            numberOfLines={1}
          >
            {`${profile.area} 실종 사건`}
          </Text>
          <GoldenTimeChip dark emphasis="critical" />
        </View>
        <Text
          style={styles.caseSub}
          allowFontScaling
          maxFontSizeMultiplier={type.maxScale}
          numberOfLines={2}
        >
          {profile.label}
        </Text>
      </View>

      <SegmentedControl
        segments={SEGMENTS}
        value={view}
        onChange={(key) => setView(key as ViewKey)}
        accent={operatorTheme.accent}
        dark
      />

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        {/* ── 예측: 실지도 + POA 히트맵 + 최종목격 핀 + 시간축 + 범례 ── */}
        {view === 'predict' && (
          <View>
            <View style={styles.mapBox}>
              {grid ? (
                <BaseMap scrollEnabled={false} accessibilityLabel={mapLabel}>
                  <PoaHeatmap grid={grid} />
                  <MapPin
                    kind="lastSeen"
                    coordinate={LAST_SEEN}
                    title="최종 목격"
                    description={profile.lastSeen}
                  />
                </BaseMap>
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

            {grid ? (
              <View
                style={styles.mapInfo}
                accessible
                accessibilityLabel={`최고 구역 ${grid.topLabel}. 누적 발견확률 ${Math.round(
                  grid.cumulative * 100,
                )}퍼센트.`}
              >
                <Text
                  style={styles.mapInfoTop}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                  numberOfLines={1}
                >
                  {`최고 구역 · ${grid.topLabel}`}
                </Text>
                <Text
                  style={styles.mapInfoCum}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  {`누적 발견확률 ${Math.round(grid.cumulative * 100)}%`}
                </Text>
              </View>
            ) : null}

            <Text
              style={styles.blockLabel}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
            >
              예측 시간축
            </Text>
            <TimeAxisSlider value={t} onChange={setT} accent={operatorTheme.accent} dark />

            <View style={styles.legendWrap}>
              <HeatLegend dark />
            </View>
          </View>
        )}

        {/* ── 근거: 마음 상태 추론 타임라인 + 유력 지점(POI) ── */}
        {view === 'reason' && (
          <View>
            <Text
              style={styles.blockLabel}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
            >
              이동 추론 타임라인
            </Text>
            <View style={styles.card}>
              <ReasonTimeline steps={REASON_TIMELINE} dark />
            </View>

            <Text
              style={[styles.blockLabel, styles.blockLabelSpaced]}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
            >
              유력 지점 (POA)
            </Text>
            {POIS.map((poi, i) => (
              <View key={poi.id} style={styles.poiRow}>
                <PoiProbCard poi={poi} rank={i + 1} dark />
              </View>
            ))}
          </View>
        )}

        {/* ── 교차검증: 마음/몸 격자 + 일치도 링 + JSD ── */}
        {view === 'crossval' && (
          <View>
            {cvData ? (
              <>
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
                      마음·몸 예측이 거의 일치해요
                    </Text>
                    <Text
                      style={styles.cvSub}
                      allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}
                    >
                      {`이동분포 유사도 JSD ${jsdText} · 완전일치에 가까움`}
                    </Text>
                  </View>
                </View>

                <Text
                  style={[styles.blockLabel, styles.blockLabelSpaced]}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  마음 ↔ 몸 예측 격자
                </Text>
                <View style={styles.gridRow}>
                  <CrossValMiniGrid title="마음" cells={cvData.mind} dark />
                  <CrossValMiniGrid title="몸" cells={cvData.body} dark />
                </View>
                <Text
                  style={styles.gridNote}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  점선 테두리 = 마음·몸 예측 불일치 셀 (재확인 필요)
                </Text>
              </>
            ) : (
              <View
                style={styles.cvLoading}
                accessible
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

      {/* 하단 액션바 — 운영자 전용 */}
      <View style={styles.actionBar}>
        <CTAButton
          label="발견 처리"
          onPress={goFound}
          accent={color.walk}
          fullWidth={false}
          style={styles.actionBtn}
          accessibilityHint="사건을 발견 완료로 종료합니다"
        />
        <CTAButton
          label="검증 수치"
          onPress={goValidation}
          accent={color.operatorSurfaceAlt}
          fullWidth={false}
          style={[styles.actionBtn, styles.actionBtnSecondary]}
          accessibilityHint="검증 수치 리포트를 봅니다"
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: operatorTheme.bg },

  header: {
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.md,
  },
  headerTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  caseTitle: {
    flex: 1,
    marginRight: space.md,
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    color: operatorTheme.text,
  },
  caseSub: {
    marginTop: space.xs,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    color: operatorTheme.textSec,
    lineHeight: 21,
  },

  scroll: { flex: 1 },
  scrollContent: {
    paddingHorizontal: space.lg,
    paddingTop: space.lg,
    paddingBottom: space.xxl,
  },

  mapBox: {
    height: 300,
    borderRadius: radius.lg,
    overflow: 'hidden',
  },
  mapLoading: {
    flex: 1,
    minHeight: 300,
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

  mapInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: space.md,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
  },
  mapInfoTop: {
    flex: 1,
    marginRight: space.sm,
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
    color: operatorTheme.text,
  },
  mapInfoCum: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
    color: operatorTheme.accent,
  },

  blockLabel: {
    marginTop: space.xl,
    marginBottom: space.md,
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    color: operatorTheme.text,
  },
  blockLabelSpaced: { marginTop: space.xxl },

  legendWrap: { marginTop: space.lg },

  card: {
    padding: space.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
  },

  poiRow: { marginBottom: space.md },

  cvSummary: {
    flexDirection: 'row',
    alignItems: 'center',
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
    lineHeight: 21,
  },

  gridRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    flexWrap: 'wrap',
  },
  gridNote: {
    marginTop: space.md,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    color: operatorTheme.textSec,
    lineHeight: 21,
  },

  cvLoading: {
    minHeight: 200,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
  },

  actionBar: {
    flexDirection: 'row',
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.md,
    borderTopWidth: 1,
    borderTopColor: operatorTheme.border,
    backgroundColor: operatorTheme.bg,
  },
  actionBtn: { flex: 1 },
  actionBtnSecondary: {
    marginLeft: space.md,
    borderWidth: 1,
    borderColor: operatorTheme.border,
  },
});
