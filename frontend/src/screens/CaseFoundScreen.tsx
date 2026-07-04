/**
 * 발견·종료 (spec §3.4, CONTRACT #10). 운영자 다크 fullScreenModal.
 * DesignSync `found-content` 목업(라이트 축하 히어로)을 다크 운영자 톤으로 이식:
 *   축하 히어로(그린 그라디언트 체크 + 펄스 링) → 발견 경위 카드 → 요약 통계(StatCard dark)
 *   → 경보 회수 안내 → 감사 카피 → 하단 액션.
 * 액션(정정): [검증 수치 리포트]→navigate('ValidationReport') / [닫기]→closeCase()+popToTop().
 * 색: 성공=산책 그린(무사/평온). 심각도 색(빨강/앰버)은 여기 미사용(spec §4.1).
 * 실종자(이름·관계)는 useMissingPersonStore 단일 소스로만 읽음 — 하드코딩 금지.
 */
import React, { useEffect, useRef } from 'react';
import { ActivityIndicator, Animated, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Circle, Path } from 'react-native-svg';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { color, HIT, radius, space, type } from '../theme/tokens';
import { operatorTheme } from '../theme/theme';
import { hexToRgba } from '../utils/color';
import { useFoundSummary } from '../hooks/queries';
import { useAppModeStore } from '../store/appModeStore';
import { useMissingPersonStore } from '../store/missingPersonStore';
import { DEMO_CASE_ID } from '../data/missing';
import type { OperatorStackParamList } from '../navigation/types';
import StatCard from '../components/StatCard';

type Nav = NativeStackNavigationProp<OperatorStackParamList>;

// 목업 발견 시각(데모 표기 — 프로필 데이터 아님).
const FOUND_TIME = '오후 4시 02분';

// 그라디언트 색은 토큰에서만. (spec §7) — LinearGradient는 최소 2색 readonly 튜플.
const HERO_GRADIENT = [hexToRgba(color.walk, 0.24), hexToRgba(color.walk, 0.06), color.operatorBg] as const;
const CIRCLE_GRADIENT = [color.walk, color.walkInk] as const;
const PRIMARY_GRADIENT = [color.walk, color.walkInk] as const;

// ── 소형 SVG 아이콘(목업 라인 아이콘 이식, 다크에선 그린 스트로크) ──
function CheckIcon() {
  return (
    <Svg width={50} height={50} viewBox="0 0 24 24" fill="none">
      <Path d="M5 12.5l4.5 4.5L19 7.5" stroke="#FFFFFF" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}
function ChatIcon() {
  return (
    <Svg width={14} height={14} viewBox="0 0 24 24" fill="none">
      <Path
        d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"
        stroke={color.walk}
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}
function PinIcon() {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 21s6.5-5.6 6.5-10.5a6.5 6.5 0 0 0-13 0C5.5 15.4 12 21 12 21Z"
        stroke={color.walk}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Circle cx={12} cy={10.5} r={2.3} stroke={color.walk} strokeWidth={2} />
    </Svg>
  );
}
function ClockIcon() {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Circle cx={12} cy={12} r={8.5} stroke={color.walk} strokeWidth={2} />
      <Path d="M12 7.5V12l3 2" stroke={color.walk} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}
function RecallIcon() {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Path d="M20 12a8 8 0 1 1-3-6.2" stroke={color.walk} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M20 5v4h-4" stroke={color.walk} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}
function CloseIcon() {
  return (
    <Svg width={21} height={21} viewBox="0 0 24 24" fill="none">
      <Path d="M6 6l12 12M18 6L6 18" stroke={operatorTheme.text} strokeWidth={2.2} strokeLinecap="round" />
    </Svg>
  );
}
function ReportIcon() {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Path
        d="M8 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3"
        stroke="#FFFFFF"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Path d="M8 12h8M8 16h5M8 8h4" stroke="#FFFFFF" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export default function CaseFoundScreen() {
  const navigation = useNavigation<Nav>();
  const closeCase = useAppModeStore((s) => s.closeCase);
  const profile = useMissingPersonStore((s) => s.profile);
  const { data: summary, isLoading } = useFoundSummary(DEMO_CASE_ID);

  // 축하 펄스 링 — 경량 Animated(네이티브 드라이버 transform/opacity).
  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.timing(pulse, { toValue: 1, duration: 2600, useNativeDriver: true }),
    );
    loop.start();
    return () => loop.stop();
  }, [pulse]);
  const ringScale = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.75, 1.9] });
  const ringOpacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.5, 0] });

  const handleReport = () => navigation.navigate('ValidationReport');
  const handleClose = () => {
    closeCase();
    navigation.popToTop();
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="light" />

      {/* 닫기(X) — 목업 우상단 어포던스도 종료 액션에 매핑 */}
      <Pressable
        onPress={handleClose}
        accessibilityRole="button"
        accessibilityLabel="닫기"
        accessibilityHint="사건을 종료하고 처음 화면으로 돌아갑니다"
        hitSlop={12}
        style={({ pressed }) => [styles.closeX, pressed && styles.pressed]}
      >
        <CloseIcon />
      </Pressable>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* 축하 히어로 */}
        <LinearGradient colors={HERO_GRADIENT} start={{ x: 0.5, y: 0 }} end={{ x: 0.5, y: 1 }} style={styles.hero}>
          <View style={styles.checkWrap} accessible accessibilityLabel="무사히 발견됨">
            <Animated.View
              style={[styles.ring, { transform: [{ scale: ringScale }], opacity: ringOpacity }]}
              pointerEvents="none"
            />
            <LinearGradient
              colors={CIRCLE_GRADIENT}
              start={{ x: 0.1, y: 0 }}
              end={{ x: 0.9, y: 1 }}
              style={styles.checkCircle}
            >
              <CheckIcon />
            </LinearGradient>
          </View>

          <Text
            style={styles.heroTitle}
            accessibilityRole="header"
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
          >
            무사히 발견됐어요
          </Text>
          <Text style={styles.heroSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {profile.name} {profile.rel}가 가족 곁으로{'\n'}안전하게 돌아왔어요 🌿
          </Text>
        </LinearGradient>

        <View style={styles.body}>
          {/* 발견 경위 */}
          <View style={styles.card}>
            <View style={styles.badge}>
              <ChatIcon />
              <Text style={styles.badgeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                시민 제보로 발견
              </Text>
            </View>

            <View style={styles.detailRow}>
              <View style={styles.iconTile}>
                <PinIcon />
              </View>
              <View style={styles.detailText}>
                <Text style={styles.detailLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  발견 장소
                </Text>
                <Text style={styles.detailValue} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
                  {summary ? summary.foundArea : '확인 중'}
                </Text>
              </View>
            </View>

            <View style={styles.divider} />

            <View style={styles.detailRow}>
              <View style={styles.iconTile}>
                <ClockIcon />
              </View>
              <View style={styles.detailText}>
                <Text style={styles.detailLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  발견 시각
                </Text>
                <Text style={styles.detailValue} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
                  {FOUND_TIME}
                </Text>
              </View>
            </View>
          </View>

          {/* 요약 통계 — StatCard dark */}
          <View style={styles.statsSection}>
            <Text style={styles.eyebrow} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              함께한 기록
            </Text>
            {isLoading || !summary ? (
              <View style={styles.loading}>
                <ActivityIndicator color={color.walk} />
              </View>
            ) : (
              <View style={styles.statsRow}>
                <View style={styles.statCell}>
                  <StatCard value={summary.elapsed} label="소요 시간" accent={color.walk} dark />
                </View>
                <View style={styles.statCell}>
                  <StatCard value={summary.citizens} label="동원 시민" accent={color.walk} dark />
                </View>
                <View style={styles.statCell}>
                  <StatCard value={summary.validTips} label="유효 제보" accent={color.walk} dark />
                </View>
              </View>
            )}
          </View>

          {/* 경보 회수 안내 */}
          <View style={styles.recall} accessible accessibilityLabel="주변에 발송된 경보는 자동으로 회수됐어요">
            <RecallIcon />
            <Text style={styles.recallText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              주변에 발송된 경보는 자동으로 회수됐어요
            </Text>
          </View>

          {/* 감사 카피 */}
          <View style={styles.thanks}>
            <Text style={styles.thanksText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              함께 움직여 준 이웃들과 현장 대원들 덕분입니다.{'\n'}관제 예측과 시민 제보가 만나 무사 귀가로 이어졌어요.
            </Text>
          </View>
        </View>
      </ScrollView>

      {/* 하단 액션 */}
      <View style={styles.actions}>
        <Pressable
          onPress={handleReport}
          accessibilityRole="button"
          accessibilityLabel="검증 수치 리포트"
          accessibilityHint="예측 정확도와 검증 지표를 확인합니다"
          style={({ pressed }) => [styles.primaryBtn, pressed && styles.pressed]}
        >
          <LinearGradient
            colors={PRIMARY_GRADIENT}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.primaryFill}
          >
            <ReportIcon />
            <Text style={styles.primaryLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
              검증 수치 리포트
            </Text>
          </LinearGradient>
        </Pressable>

        <Pressable
          onPress={handleClose}
          accessibilityRole="button"
          accessibilityLabel="닫기"
          accessibilityHint="사건을 종료하고 처음 화면으로 돌아갑니다"
          style={({ pressed }) => [styles.closeBtn, pressed && styles.pressed]}
        >
          <Text style={styles.closeLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
            닫기
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: operatorTheme.bg },

  closeX: {
    position: 'absolute',
    top: space.md,
    right: space.lg,
    zIndex: 20,
    width: HIT,
    height: HIT,
    borderRadius: radius.md,
    backgroundColor: operatorTheme.surfaceAlt,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    alignItems: 'center',
    justifyContent: 'center',
  },

  scroll: { flex: 1 },
  scrollContent: { paddingBottom: space.xl },

  // 히어로
  hero: {
    alignItems: 'center',
    paddingTop: space.xxl + space.xl,
    paddingBottom: space.xl,
    paddingHorizontal: space.xl,
  },
  checkWrap: { width: 96, height: 96, alignItems: 'center', justifyContent: 'center' },
  ring: {
    position: 'absolute',
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: hexToRgba(color.walk, 0.18),
  },
  checkCircle: {
    width: 96,
    height: 96,
    borderRadius: 48,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: color.walk,
    shadowOpacity: 0.45,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 12 },
    elevation: 10,
  },
  heroTitle: {
    marginTop: space.xl,
    fontSize: 26,
    fontWeight: type.weight.black,
    color: operatorTheme.text,
    fontFamily: type.family,
    textAlign: 'center',
    letterSpacing: -0.5,
  },
  heroSub: {
    marginTop: space.md,
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: operatorTheme.textSec,
    fontFamily: type.family,
    textAlign: 'center',
    lineHeight: 24,
  },

  // 본문
  body: { paddingHorizontal: space.xl, gap: space.md, marginTop: space.xs },

  card: {
    backgroundColor: operatorTheme.surface,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    padding: space.lg,
    gap: space.lg,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    alignSelf: 'flex-start',
    backgroundColor: hexToRgba(color.walk, 0.16),
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs + 1,
  },
  badgeText: { fontSize: type.size.label, fontWeight: type.weight.black, color: color.walk, fontFamily: type.family },

  detailRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  iconTile: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    backgroundColor: hexToRgba(color.walk, 0.14),
    alignItems: 'center',
    justifyContent: 'center',
  },
  detailText: { flex: 1, minWidth: 0 },
  detailLabel: { fontSize: type.size.label, fontWeight: type.weight.medium, color: operatorTheme.textSec, fontFamily: type.family },
  detailValue: {
    marginTop: 2,
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: operatorTheme.text,
    fontFamily: type.family,
  },
  divider: { height: 1, backgroundColor: operatorTheme.border },

  // 통계
  statsSection: { gap: space.md, marginTop: space.xs },
  eyebrow: { fontSize: type.size.label, fontWeight: type.weight.bold, color: operatorTheme.textSec, fontFamily: type.family },
  loading: { paddingVertical: space.xl, alignItems: 'center' },
  statsRow: { flexDirection: 'row', gap: space.sm },
  statCell: { flex: 1 },

  // 경보 회수
  recall: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: hexToRgba(color.walk, 0.12),
    borderRadius: radius.lg,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  recallText: {
    flex: 1,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: operatorTheme.text,
    fontFamily: type.family,
    lineHeight: 21,
  },

  // 감사
  thanks: {
    backgroundColor: operatorTheme.surface,
    borderColor: operatorTheme.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  thanksText: {
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: operatorTheme.textSec,
    fontFamily: type.family,
    lineHeight: 24,
    textAlign: 'center',
  },

  // 하단 액션
  actions: {
    gap: space.sm,
    paddingHorizontal: space.xl,
    paddingTop: space.md,
    paddingBottom: space.lg,
    borderTopWidth: 1,
    borderTopColor: operatorTheme.border,
    backgroundColor: operatorTheme.bg,
  },
  primaryBtn: {
    borderRadius: radius.lg,
    overflow: 'hidden',
    shadowColor: color.walk,
    shadowOpacity: 0.32,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 8 },
    elevation: 6,
  },
  primaryFill: {
    minHeight: 60,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    paddingHorizontal: space.xl,
  },
  primaryLabel: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: '#FFFFFF', fontFamily: type.family },
  closeBtn: {
    minHeight: 56,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: operatorTheme.border,
    backgroundColor: operatorTheme.surface,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xl,
  },
  closeLabel: { fontSize: type.size.body, fontWeight: type.weight.bold, color: operatorTheme.text, fontFamily: type.family },

  pressed: { opacity: 0.85 },
});
