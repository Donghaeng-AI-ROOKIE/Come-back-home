/**
 * 내 안심 기록 — 마이페이지 (와이어프레임 A-4).
 *
 * 레벨·배지·누적은 전부 서버가 계산한 값을 그대로 그린다. 앱에서 계산하면
 * 규칙을 바꿀 때마다 앱 배포가 필요하고 구버전 사용자에게 다른 값이 보인다
 * (backend/app/walk/stats.py).
 */
import React from 'react';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import dayjs from 'dayjs';
import { color, radius, space, type } from '../theme/tokens';
import { useWalkStats } from '../hooks/queries';
import type { Badge, WalkSession } from '../api/walk';

function BadgeChip({ badge }: { badge: Badge }) {
  return (
    <View
      style={[styles.badge, !badge.earned && styles.badgeOff]}
      accessible
      accessibilityLabel={`${badge.label} 배지 ${badge.earned ? '획득' : '미획득'}`}
    >
      <View style={[styles.badgeIcon, badge.earned ? styles.badgeIconOn : styles.badgeIconOff]}>
        <Text style={styles.badgeEmoji}>{badge.icon}</Text>
      </View>
      <Text style={styles.badgeLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={2}>
        {badge.label}
      </Text>
    </View>
  );
}

function RecentRow({ s }: { s: WalkSession }) {
  return (
    <View style={styles.recentRow}>
      <View style={styles.recentInfo}>
        <Text style={styles.recentTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
          {s.area_label || '산책'}
        </Text>
        <Text style={styles.recentDate} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          {s.ended_at ? dayjs(s.ended_at).format('YYYY.MM.DD A h:mm') : ''}
        </Text>
      </View>
      <Text style={styles.recentKm} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        {s.distance_km.toFixed(1)} km
      </Text>
    </View>
  );
}

export default function RecordsScreen() {
  const { data, isLoading, isError, error, refetch, isRefetching } = useWalkStats();

  if (isError) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.center}>
          <Text style={styles.errTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            기록을 불러오지 못했습니다
          </Text>
          {/* 오류를 감추면 "서버가 안 붙었다"를 "기록이 없다"로 오해하게 된다. */}
          <Text style={styles.errBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {String(error)}
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
      >
        <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          내 안심 기록
        </Text>

        {isLoading || !data ? (
          <Text style={styles.muted}>불러오는 중…</Text>
        ) : (
          <>
            {/* 레벨 */}
            <View style={styles.levelCard} accessible accessibilityLabel={`${data.level_label} 레벨 ${data.level}`}>
              <Text style={styles.levelEmoji}>🏅</Text>
              <View style={styles.levelInfo}>
                <Text style={styles.levelTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  {data.level_label} (Lv.{data.level})
                </Text>
                <Text style={styles.levelSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  {data.next_level_km > 0
                    ? `다음 단계까지 ${data.next_level_km.toFixed(1)}km 남음`
                    : '최고 단계 달성'}
                </Text>
              </View>
            </View>

            {/* 누적 */}
            <View style={styles.row}>
              <View style={styles.statCard}>
                <Text style={styles.statLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  총 안심 동행
                </Text>
                <Text style={[styles.statValue, styles.walkInk]} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  {data.total_km.toFixed(1)} <Text style={styles.statUnit}>km</Text>
                </Text>
              </View>
              <View style={styles.statCard}>
                <Text style={styles.statLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  실종자 제보
                </Text>
                <Text style={[styles.statValue, styles.criticalInk]} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  {data.tip_count} <Text style={styles.statUnit}>건</Text>
                </Text>
              </View>
            </View>

            {/* 배지 */}
            <Text style={styles.section} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              배지
            </Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.badgeRow}>
              {data.badges.map((b) => (
                <BadgeChip key={b.id} badge={b} />
              ))}
            </ScrollView>

            {/* 최근 산책 */}
            <Text style={styles.section} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              최근 산책 기록
            </Text>
            <View style={styles.recentCard}>
              {data.recent.length === 0 ? (
                <Text style={styles.muted} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  아직 산책 기록이 없어요.
                </Text>
              ) : (
                data.recent.map((s) => <RecentRow key={s.id} s={s} />)
              )}
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  scroll: { padding: space.xl, gap: space.md, paddingBottom: space.xxl },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl, gap: space.sm },
  title: { fontSize: type.size.title, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  section: { fontSize: type.size.label, fontWeight: type.weight.black, color: color.textCaption, fontFamily: type.family, marginTop: space.sm },
  muted: { fontSize: type.size.label, color: color.textBody, fontFamily: type.family },
  errTitle: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: color.critical, fontFamily: type.family },
  errBody: { fontSize: type.size.caption, color: color.textBody, fontFamily: type.family, textAlign: 'center' },

  levelCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.lg,
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
  },
  levelEmoji: { fontSize: 36 },
  levelInfo: { flex: 1, gap: space.xs },
  levelTitle: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  levelSub: { fontSize: type.size.caption, color: color.textBody, fontFamily: type.family },

  row: { flexDirection: 'row', gap: space.md },
  statCard: {
    flex: 1,
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    alignItems: 'center',
    gap: space.xs,
  },
  statLabel: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family, fontWeight: type.weight.bold },
  statValue: { fontSize: 26, fontWeight: type.weight.black, fontFamily: type.family, fontVariant: ['tabular-nums'] },
  statUnit: { fontSize: type.size.caption, fontWeight: type.weight.bold },
  walkInk: { color: color.walkInk },
  criticalInk: { color: color.criticalInk },

  badgeRow: { gap: space.lg, paddingVertical: space.sm, paddingRight: space.xl },
  badge: { alignItems: 'center', width: 72, gap: space.xs },
  badgeOff: { opacity: 0.4 },
  badgeIcon: { width: 52, height: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center' },
  badgeIconOn: { backgroundColor: color.walkWash },
  badgeIconOff: { backgroundColor: color.surfaceAlt, borderWidth: 1, borderColor: color.border },
  badgeEmoji: { fontSize: 26 },
  badgeLabel: { fontSize: type.size.caption, fontWeight: type.weight.bold, color: color.textBody, fontFamily: type.family, textAlign: 'center' },

  recentCard: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    paddingHorizontal: space.lg,
  },
  recentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.border,
    gap: space.md,
  },
  recentInfo: { flex: 1, gap: space.xs },
  recentTitle: { fontSize: type.size.label, fontWeight: type.weight.bold, color: color.text, fontFamily: type.family },
  recentDate: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family },
  recentKm: { fontSize: type.size.label, fontWeight: type.weight.black, color: color.walkInk, fontFamily: type.family, fontVariant: ['tabular-nums'] },
});
