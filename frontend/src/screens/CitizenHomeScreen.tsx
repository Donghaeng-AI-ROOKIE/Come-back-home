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
import { useDebugStore } from '../store/debugStore';
import { useAlertsForMe } from '../hooks/useAlertGate';
import { useMyLocation } from '../hooks/useMyLocation';
import { useAreaStatus } from '../hooks/useAreaStatus';

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
  const forceInAlertArea = useDebugStore((s) => s.forceInAlertArea);
  const setForceInAlertArea = useDebugStore((s) => s.setForceInAlertArea);

  // 동네 상태 — 지오펜스를 통과한(= 나에게 해당되는) 경보만 본다. 구역 밖이면
  // alert 가 null 이고 "평온해요"가 맞는 말이다. 경보 중에 평온하다고 쓰는 건
  // 이 화면에서 가장 눈에 띄는 거짓말이었다.
  const { alerts: myAlerts } = useAlertsForMe();
  const activeAlert = myAlerts[0] ?? null;
  const { status: locStatus } = useMyLocation();
  // 거리(m·분)가 아니라 "예측 구역 안/밖 + 확률 등급" — 근거는 utils/areaStatus.ts.
  const area = useAreaStatus(activeAlert?.caseId ?? '');

  // 위치를 모르면 **경보를 아예 못 받는다**(fail-closed). 어느 사건이 이 사람에게
  // 해당되는지 고를 수 없기 때문인데, 사용자 입장에선 조용한 실패라 반드시 알려야 한다.
  const locationBlocked = locStatus === 'denied' || locStatus === 'unavailable';

  const statusTitle = locationBlocked
    ? '위치를 켜야 주변 경보를 받을 수 있어요'
    : activeAlert
      ? `${activeAlert.area} 인근에서 실종자를 찾고 있어요`
      : '우리 동네는 지금 평온해요';
  const statusSub = locationBlocked
    ? '실종 경보는 내 주변일 때만 도착해요. 위치를 모르면 어느 사건이 가까운지 알 수 없어 알려드리지 못해요.'
    : !activeAlert
      ? '이번 달 이웃들이 무사히 집으로 돌아왔어요'
      : area.label;

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

        {/* 동네 상태 — 경보가 나에게 해당될 때만 수색 문구로 바뀐다.
            색은 심각도 워시(채도 높은 필 아님) — 관문을 통과한 뒤의 홈이라
            여기서 다시 전면 경보처럼 굴면 사용자의 의사를 뒤집는 셈이다. */}
        <View
          style={[
            styles.statusCard,
            activeAlert && styles.statusCardAlert,
            locationBlocked && styles.statusCardBlocked,
          ]}
          accessible
          accessibilityRole="text"
          accessibilityLabel={`${statusTitle}. ${statusSub}`}
        >
          <View
            style={[
              styles.statusDot,
              activeAlert && styles.statusDotAlert,
              locationBlocked && styles.statusDotBlocked,
            ]}
          />
          <View style={styles.statusText}>
            <Text
              style={[
                styles.statusTitle,
                activeAlert && styles.statusTitleAlert,
                locationBlocked && styles.statusTitleBlocked,
              ]}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
            >
              {statusTitle}
            </Text>
            <Text style={styles.statusSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {statusSub}
            </Text>
          </View>
        </View>

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
  statusCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.sm,
    backgroundColor: color.walkWash,
    borderRadius: radius.lg,
    padding: space.md,
  },
  statusCardAlert: { backgroundColor: color.criticalWash },
  // 위치 차단 — 긴급(빨강)도 평시(그린)도 아니다. 주의 환기용 앰버 계열.
  statusCardBlocked: { backgroundColor: color.searchWash },
  statusDotBlocked: { backgroundColor: color.search },
  statusTitleBlocked: { color: color.searchInk },
  statusDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: color.walk, marginTop: 5 },
  statusDotAlert: { backgroundColor: color.critical },
  statusText: { flex: 1, minWidth: 0 },
  statusTitle: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.walkInk,
    fontFamily: type.family,
  },
  statusTitleAlert: { color: color.criticalInk },
  statusSub: {
    marginTop: 2,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
    lineHeight: 18,
  },

  // 데모 전용 칩 — 눈에 띄지 않게 중립 톤. 시연 스위치지 기능이 아니다.
  debugChip: {
    alignSelf: 'center',
    marginTop: space.md,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
  },
  debugText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
  },
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
