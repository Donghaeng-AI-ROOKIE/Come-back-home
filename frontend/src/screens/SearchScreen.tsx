/**
 * 수색 탭 (spec §3.4, search-content). 라이트 소비자 화면.
 * 실 타일맵 위 POA 히트맵(usePoaPrediction) + 최종 목격 핀 + 수치·패턴 범례.
 * 실종자 정보는 익명 compact 카드(단일 소스)로만 노출. 주 액션 = 제보하기.
 * 모드 전환 트리거 없음 — 색만 useModeTheme().accent로 셸 강조.
 */
import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import { color, radius, space, type } from '../theme/tokens';
import { useModeTheme } from '../theme/theme';
import { usePoaPrediction } from '../hooks/queries';
import { DEMO_CASE_ID, LAST_SEEN } from '../data/missing';
import { useAuthStore } from '../store/authStore';
import type { RootStackParamList } from '../navigation/types';

import BaseMap from '../components/BaseMap';
import PoaHeatmap from '../components/PoaHeatmap';
import MapPin from '../components/MapPin';
import HeatLegend from '../components/HeatLegend';
import MissingPersonCard from '../components/MissingPersonCard';
import ModeStatusBar from '../components/ModeStatusBar';
import CTAButton from '../components/CTAButton';

export default function SearchScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const theme = useModeTheme();
  const role = useAuthStore((s) => s.role);
  const poa = usePoaPrediction(DEMO_CASE_ID, 1);

  const grid = poa.data;
  const mapA11y = grid
    ? `발견 확률 히트맵. 최고 구역 ${grid.topLabel}. 누적 발견확률 ${Math.round(
        grid.cumulative * 100,
      )}%. 최종 목격 위치가 표시돼 있어요.`
    : '발견 확률 지도를 불러오는 중입니다.';

  const onReport = () => navigation.navigate('ReportChat', { caseId: DEMO_CASE_ID });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + space.xxl }]}
        showsVerticalScrollIndicator={false}
      >
        <ModeStatusBar />

        <View style={styles.headerBlock}>
          <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            실시간 예측 지도
          </Text>
          <Text style={styles.subtitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            AI가 예측한 발견 확률이 높은 구역이에요. 이 근처를 지나신다면 한 번 살펴봐 주세요.
          </Text>
        </View>

        <View style={styles.mapWrap}>
          <BaseMap scrollEnabled={false} accessibilityLabel={mapA11y}>
            {grid ? <PoaHeatmap grid={grid} /> : null}
            <MapPin
              kind="lastSeen"
              coordinate={LAST_SEEN}
              title="최종 목격 위치"
              description="정릉동 주민센터, 오후 3시 10분경"
            />
          </BaseMap>

          {poa.isLoading ? (
            <View style={styles.mapOverlay} accessible accessibilityLabel="지도를 불러오는 중입니다">
              <ActivityIndicator color={theme.accent} size="large" />
              <Text style={styles.overlayText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                예측 지도를 불러오는 중…
              </Text>
            </View>
          ) : null}
        </View>

        {poa.isError ? (
          <Pressable
            onPress={() => poa.refetch()}
            accessibilityRole="button"
            accessibilityLabel="지도 다시 불러오기"
            style={({ pressed }) => [styles.errorCard, pressed && styles.pressed]}
          >
            <Text style={styles.errorText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              지도를 불러오지 못했어요. 눌러서 다시 시도해 주세요.
            </Text>
          </Pressable>
        ) : null}

        <HeatLegend compact />

        {grid ? (
          <View
            style={styles.cumRow}
            accessible
            accessibilityLabel={`최고 확률 구역 ${grid.topLabel}, 누적 발견확률 ${Math.round(
              grid.cumulative * 100,
            )}퍼센트`}
          >
            <Text style={styles.cumLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              최고 확률 구역 · {grid.topLabel}
            </Text>
            <Text style={styles.cumValue} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              누적 {Math.round(grid.cumulative * 100)}%
            </Text>
          </View>
        ) : null}

        <View style={styles.section}>
          <Text style={styles.sectionTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            지금 찾고 있어요
          </Text>
          <MissingPersonCard variant="compact" anon />
        </View>

        <CTAButton
          label="제보하기"
          onPress={onReport}
          accent={theme.accent}
          accessibilityHint="본 것을 알려주면 수색 구역을 좁힐 수 있어요"
          style={styles.cta}
        />

        <View
          style={styles.infoLine}
          accessible
          accessibilityLabel="급한 상황이면 112에 먼저 신고해 주세요. 이 앱은 신고 채널이 아니라 함께 찾는 도구예요."
        >
          <Text style={styles.infoEmoji} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            📞
          </Text>
          <Text style={styles.infoText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            급한 상황이면{' '}
            <Text
              style={styles.infoStrong}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
            >
              112
            </Text>
            에 먼저 신고해 주세요. 이 앱은 신고 채널이 아니라, 예측과 제보로 함께 찾는 도구예요.
          </Text>
        </View>

        {role === 'operator' ? (
          <View
            style={styles.operatorNote}
            accessible
            accessibilityLabel="운영자 전용 안내. AI 예측 지도 전체보기는 관제 콘솔에서 제공돼요."
          >
            <Text style={styles.operatorText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              운영자 전용 · AI 예측 지도 전체보기는 관제 콘솔에서 제공돼요.
            </Text>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surface },
  scroll: { flex: 1 },
  content: {
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    gap: space.lg,
  },
  headerBlock: { gap: space.xs },
  title: {
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },
  subtitle: {
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
    lineHeight: 24,
  },
  mapWrap: { height: 300 },
  mapOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    borderRadius: radius.lg,
    backgroundColor: 'rgba(255,255,255,0.72)',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
  },
  overlayText: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
  },
  errorCard: {
    backgroundColor: color.surfaceAlt,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
  },
  errorText: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
    textAlign: 'center',
  },
  cumRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: color.surfaceAlt,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: color.border,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    gap: space.sm,
  },
  cumLabel: {
    flex: 1,
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.text,
    fontFamily: type.family,
  },
  cumValue: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.critical,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
  },
  section: { gap: space.sm },
  sectionTitle: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },
  cta: { marginTop: space.xs },
  infoLine: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: color.surfaceAlt,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    gap: space.sm,
  },
  infoEmoji: { fontSize: 18 },
  infoText: {
    flex: 1,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
    lineHeight: 22,
  },
  infoStrong: { fontWeight: type.weight.black, color: color.critical },
  operatorNote: {
    backgroundColor: color.walkWash,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.md,
  },
  operatorText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: color.walkInk,
    fontFamily: type.family,
  },
  pressed: { opacity: 0.85 },
});
