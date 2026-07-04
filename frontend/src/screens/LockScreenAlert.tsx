/**
 * 잠금화면 경보 takeover (spec §3.4, §4.1). Root fullScreenModal.
 * iOS 잠금화면 룩: 다크 반투명 배경 + 큰 시계 + 긴급(빨강) 실종경보 카드.
 * 긴급 = 빨강(color.critical) — 앰버 금지(§4.1). 진입 즉시 낭독(accessibilityLiveRegion="assertive").
 * 뒤로가기(시스템/닫기 버튼) → 이전 화면 dismiss.
 */
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { TextStyle } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { color, radius, space, type, HIT } from '../theme/tokens';
import CTAButton from '../components/CTAButton';
import { DEMO_CASE_ID, MISSING_ANON } from '../data/missing';
import type { RootStackParamList } from '../navigation/types';

// 시계 자릿수 흔들림 방지 — 고정폭 숫자.
const TABULAR: TextStyle = { fontVariant: ['tabular-nums'] };
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'] as const;
// '내 주변' 타겟 근거 — 경보 메타데이터(거리), 실종자 프로필 아님. 데모 상수.
const DISTANCE_LABEL = '약 320m';

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

  const clock = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  const dateLine = `${now.getMonth() + 1}월 ${now.getDate()}일 ${WEEKDAYS[now.getDay()]}요일`;

  const headline = `내 주변 · ${MISSING_ANON}`;
  const openDetail = () => navigation.navigate('AlertDetail', { caseId });
  const dismiss = () => navigation.goBack();

  return (
    <View
      style={[
        styles.root,
        { paddingTop: insets.top + space.md, paddingBottom: insets.bottom + space.lg },
      ]}
    >
      <StatusBar style="light" />

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

      {/* 시계 */}
      <View style={styles.clockBlock}>
        <Text style={styles.date} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          {dateLine}
        </Text>
        <Text style={[styles.clock, TABULAR]} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          {clock}
        </Text>
      </View>

      <View style={styles.spacer} />

      {/* 긴급 실종경보 카드 (빨강) */}
      <View
        style={styles.alertCard}
        accessible
        accessibilityLiveRegion="assertive"
        accessibilityLabel={`긴급 실종경보. 내 주변 ${MISSING_ANON}. 거리 ${DISTANCE_LABEL}. 지금 확인하려면 아래 지금 확인 버튼을 누르세요.`}
      >
        <View style={styles.alertHead}>
          <View style={styles.sevBadge}>
            <Text style={styles.sevBadgeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              실종경보
            </Text>
          </View>
          <Text style={styles.alertMeta} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            방금 · 112 실종경보
          </Text>
        </View>

        <View style={styles.alertBody}>
          <View style={styles.silhouette}>
            <Text style={styles.silhouetteGlyph} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              👤
            </Text>
          </View>
          <View style={styles.alertText}>
            <Text
              style={styles.alertTitle}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
              numberOfLines={2}
            >
              {headline}
            </Text>
            <Text style={styles.alertDistance} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {`${DISTANCE_LABEL} 거리에서 실종경보`}
            </Text>
          </View>
        </View>
      </View>

      {/* 주 행동 — 긴급(danger) */}
      <View style={styles.ctaWrap}>
        <CTAButton
          label="지금 확인"
          onPress={openDetail}
          variant="danger"
          accessibilityHint="실종 경보 상세 화면을 엽니다"
        />
        <Text style={styles.footHint} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          경찰 112 실종경보를 기반으로 내 주변에만 전송됐어요
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: color.operatorBg, // 다크 잠금화면 배경(토큰 소스)
    paddingHorizontal: space.xl,
  },
  topBar: { alignItems: 'flex-end' },
  dismiss: { width: HIT, height: HIT, alignItems: 'center', justifyContent: 'center' },
  dismissGlyph: {
    fontSize: 22,
    color: color.operatorTextSec,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
  },
  clockBlock: { alignItems: 'center', marginTop: space.xxl },
  date: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.operatorTextSec,
    fontFamily: type.family,
    marginBottom: space.xs,
  },
  clock: {
    fontSize: 64,
    fontWeight: type.weight.black,
    color: color.operatorText,
    fontFamily: type.family,
  },
  spacer: { flex: 1 },
  alertCard: {
    backgroundColor: color.critical, // 긴급 = 빨강(§4.1)
    borderRadius: radius.lg,
    padding: space.lg,
  },
  alertHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.md,
  },
  sevBadge: {
    backgroundColor: color.criticalWash,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    borderRadius: radius.pill,
  },
  sevBadgeText: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.criticalInk,
    fontFamily: type.family,
  },
  alertMeta: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.operatorText,
    fontFamily: type.family,
  },
  alertBody: { flexDirection: 'row', alignItems: 'center' },
  silhouette: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: color.criticalWash,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: space.lg,
  },
  silhouetteGlyph: { fontSize: 30, textAlign: 'center' },
  alertText: { flex: 1 },
  alertTitle: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.operatorText,
    fontFamily: type.family,
  },
  alertDistance: {
    marginTop: space.xs,
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.operatorText,
    fontFamily: type.family,
  },
  ctaWrap: { marginTop: space.lg },
  footHint: {
    marginTop: space.md,
    fontSize: type.size.caption,
    color: color.operatorTextSec,
    textAlign: 'center',
    fontFamily: type.family,
    lineHeight: 18,
  },
});
