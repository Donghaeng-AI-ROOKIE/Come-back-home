/**
 * 안심 산책 홈 (와이어프레임 A-1) — 시민의 평상시 첫 화면.
 *
 * 이 앱은 실종 사건이 없는 날이 대부분이다. 그날 열 이유가 없으면 정작 알림이
 * 필요한 날 앱이 지워져 있으므로, 홈은 "수색"이 아니라 "산책"을 앞에 둔다.
 */
import React from 'react';
import { Alert, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import { useActiveWalk, useStartWalk, useWalkStats } from '../hooks/queries';

/** 추천 루트는 아직 서버 계산이 없다 — 표시용 고정값임을 코드에 남긴다. */
const ROUTES = [
  { id: 'gyeongui', icon: '🌳', name: '경의선 숲길', meta: '1.2km · 보통' },
  { id: 'mangwon', icon: '🌊', name: '망원 한강공원', meta: '2.5km · 원활' },
];

export default function CitizenHomeScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data: stats, refetch, isRefetching } = useWalkStats();
  const { data: active } = useActiveWalk();
  const startWalk = useStartWalk();

  const onStart = (areaLabel?: string) => {
    if (active) {
      navigation.navigate('WalkActive');
      return;
    }
    startWalk.mutate(areaLabel, {
      onSuccess: () => navigation.navigate('WalkActive'),
      onError: (e) => Alert.alert('산책을 시작하지 못했습니다', String(e)),
    });
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
      >
        <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          안심 산책
        </Text>

        {/* 이번 달 누적 */}
        <View
          style={styles.monthCard}
          accessible
          accessibilityLabel={`이번 달 누적 안심 동행 거리 ${stats?.month_km.toFixed(1) ?? 0}킬로미터`}
        >
          <Text style={styles.monthValue} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {(stats?.month_km ?? 0).toFixed(1)} <Text style={styles.monthUnit}>km</Text>
          </Text>
          <Text style={styles.monthLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            이번 달 누적 안심 동행 거리
          </Text>
        </View>

        {/* 추천 루트 */}
        <Text style={styles.section} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          내 주변 안심 루트
        </Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.routeRow}>
          {ROUTES.map((r) => (
            <Pressable
              key={r.id}
              onPress={() => onStart(r.name)}
              accessibilityRole="button"
              accessibilityLabel={`${r.name}에서 산책 시작`}
              style={({ pressed }) => [styles.routeCard, pressed && styles.pressed]}
            >
              <Text style={styles.routeIcon}>{r.icon}</Text>
              <Text style={styles.routeName} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                {r.name}
              </Text>
              <Text style={styles.routeMeta} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                {r.meta}
              </Text>
            </Pressable>
          ))}
        </ScrollView>

        {/* 시작 */}
        <Pressable
          onPress={() => onStart()}
          disabled={startWalk.isPending}
          accessibilityRole="button"
          accessibilityLabel={active ? '진행 중인 산책으로 이동' : '산책 시작하기'}
          style={({ pressed }) => [styles.startBtn, pressed && styles.pressed, startWalk.isPending && styles.disabled]}
        >
          <Text style={styles.startLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {active ? '진행 중인 산책 이어가기' : startWalk.isPending ? '시작하는 중…' : '산책 시작하기'}
          </Text>
        </Pressable>

        <Text style={styles.note} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          산책 경로는 저장하지 않습니다. 시작·종료 시각과 거리 합계만 기록됩니다.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  scroll: { padding: space.xl, gap: space.md, paddingBottom: space.xxl },
  title: { fontSize: type.size.title, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  section: { fontSize: type.size.label, fontWeight: type.weight.black, color: color.textCaption, fontFamily: type.family, marginTop: space.sm },

  monthCard: {
    backgroundColor: color.walkWash,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.walk,
    padding: space.xl,
    alignItems: 'center',
    gap: space.xs,
  },
  monthValue: {
    fontSize: type.size.bigNum,
    fontWeight: type.weight.black,
    color: color.walkInk,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
  },
  monthUnit: { fontSize: type.size.cardTitle, fontWeight: type.weight.bold },
  monthLabel: { fontSize: type.size.caption, color: color.walkInk, fontFamily: type.family, fontWeight: type.weight.medium },

  routeRow: { gap: space.md, paddingVertical: space.xs, paddingRight: space.xl },
  routeCard: {
    minWidth: 148,
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    gap: space.xs,
  },
  routeIcon: { fontSize: 22 },
  routeName: { fontSize: type.size.label, fontWeight: type.weight.bold, color: color.text, fontFamily: type.family },
  routeMeta: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family },

  startBtn: {
    minHeight: 60,
    borderRadius: radius.pill,
    backgroundColor: color.walk,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: space.sm,
  },
  startLabel: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: '#FFFFFF', fontFamily: type.family },
  note: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family, textAlign: 'center', lineHeight: 19 },
  pressed: { opacity: 0.85 },
  disabled: { opacity: 0.5 },
});
