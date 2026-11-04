import React from 'react';
import { Alert, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import { useActiveAlerts, useActiveWalk, useStartWalk, useWalkStats } from '../hooks/queries';
import { isLocationSettled, retryLocation, useMyLocation } from '../hooks/useMyLocation';
import FigmaLogo from '../components/FigmaLogo';
import PushEnableCard from '../components/PushEnableCard';
import FigmaStatusBar from '../components/FigmaStatusBar';
import AlertCard from '../components/AlertCard';
import { useAppModeStore } from '../store/appModeStore';
import { nearbyAlertCard } from '../utils/alertTitle';
import { formatKm, koreanMonth } from '../utils/walkFormat';

export default function CitizenHomeScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data: stats, refetch, isRefetching } = useWalkStats();
  const { data: active } = useActiveWalk();
  const refreshHome = () => { void refetch(); };
  // 위치 권한 복구는 경보 대상 확인과 산책 기록에 계속 필요하다.
  const { status: locStatus, message: locMessage } = useMyLocation(true);
  const locBlocked = isLocationSettled(locStatus) && locStatus !== 'granted';
  /**
   * 주변 진행 중 경보 — 있어도 홈에는 아무 표시가 없었다. 긴급 알림 목록과 같은
   * 규칙으로 고른 맨 위 경보 한 장을 홈 맨 위에 둔다(utils/alertTitle.nearbyAlertCard).
   * 경보 관문(useAlertGate)이 이미 같은 훅·같은 쿼리 키로 묻고 있어 요청이 늘지 않는다.
   */
  const { data: alerts } = useActiveAlerts();
  const dismissedCases = useAppModeStore((s) => s.dismissedCases);
  const alertCard = nearbyAlertCard(alerts, dismissedCases);
  const openAlert = () => {
    if (alertCard?.caseId) navigation.navigate('AlertDetail', { caseId: alertCard.caseId });
    else navigation.navigate('CitizenTabs', { screen: 'Alerts' });
  };
  const startWalk = useStartWalk();
  const onStart = (areaLabel?: string) => {
    if (active) return navigation.navigate('WalkActive');
    startWalk.mutate(areaLabel, {
      onSuccess: () => navigation.navigate('WalkActive'),
      onError: (e) => Alert.alert('산책을 시작하지 못했습니다', String(e)),
    });
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refreshHome} />}
      >
        <View style={styles.logoRow}><FigmaLogo mode="citizen" /></View>

        {alertCard ? (
          <AlertCard
            tone="red"
            badge={alertCard.badge}
            title={alertCard.title}
            body={alertCard.body}
            onPress={openAlert}
            accessibilityLabel={`${alertCard.badge}. ${alertCard.title}. ${alertCard.body}`}
            style={styles.alertCard}
          />
        ) : null}

        {/* 앱을 꺼 둬도 경보를 받게 하는 유일한 경로 — 이미 켜져 있으면 안 그린다. */}
        <PushEnableCard />

        <View style={styles.monthHead}>
          <Text style={styles.kicker}>이번 달 나의 산책 기록</Text>
          <Text style={styles.monthTitle}>{koreanMonth(Date.now())}월에는 총 {formatKm(stats?.month_km ?? 0)}km를 걸었네요!</Text>
        </View>
        {/* Figma 의 월간 이미지 영역 — **카드 규격(높이·여백·라운드)은 시안 그대로** 두고
            내용만 서버 집계로 채운다. 빈 회색 상자로 두면 화면의 한 블록이 통째로
            자리표시자가 되고, "목업은 전부 실데이터로"라는 원칙과 어긋난다. */}
        <View style={styles.monthCard}>
          <View style={styles.monthStat}>
            <Text style={styles.monthStatValue}>{stats?.walk_count ?? 0}</Text>
            <Text style={styles.monthStatLabel}>산책 횟수</Text>
          </View>
          <View style={styles.monthStat}>
            <Text style={styles.monthStatValue}>{formatKm(stats?.total_km ?? 0)}km</Text>
            <Text style={styles.monthStatLabel}>누적 거리</Text>
          </View>
          <View style={styles.monthStat}>
            <Text style={styles.monthStatValue}>{stats?.tip_count ?? 0}</Text>
            <Text style={styles.monthStatLabel}>제보 참여</Text>
          </View>
          <View style={styles.monthStat}>
            <Text style={styles.monthStatValue} numberOfLines={1}>{stats?.level_label ?? '-'}</Text>
            <Text style={styles.monthStatLabel}>등급</Text>
          </View>
        </View>

        {locBlocked ? (
          <Pressable onPress={retryLocation} accessibilityRole="button" accessibilityLabel="위치 권한 다시 요청하기">
            <Text style={styles.locationNotice}>
              위치를 알 수 없어 주변 경보와 산책 기록 이용이 제한됩니다.{'\n'}
              <Text style={styles.locationRetry}>눌러서 위치 권한 다시 요청하기</Text>
              {locMessage ? `\n\n${locMessage}` : ''}
            </Text>
          </Pressable>
        ) : null}

        <Pressable
          onPress={() => onStart()}
          disabled={startWalk.isPending}
          style={({ pressed }) => [styles.start, pressed && styles.pressed, startWalk.isPending && styles.disabled]}
        >
          <Text style={styles.startText}>{active ? '산책 이어가기' : startWalk.isPending ? '시작하는 중…' : '산책 시작하기'}</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  content: { paddingBottom: 38 },
  logoRow: { height: 78, paddingLeft: 30, paddingTop: 26 },
  // 목록 카드(28 간격) 대신 홈 가장자리 여백(16)에 맞춘다 — 아래 알림 연결 카드와 같은 줄.
  alertCard: { marginHorizontal: 16, marginTop: 4, marginBottom: 4 },
  monthHead: { height: 87, paddingHorizontal: 16, paddingTop: 18 },
  kicker: { fontFamily: type.familyCssSemiBold, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#007AFF' },
  monthTitle: { fontFamily: type.familyCssExtraBold, fontSize: 18, lineHeight: 23, color: '#000000', marginTop: 5 },
  // 시안 규격(높이 117·여백 16·라운드 10) 유지. 배경만 회색 자리표시자에서
  // 읽을 수 있는 밝은 톤으로 바꾼다 — 안에 숫자가 들어가기 때문이다.
  monthCard: {
    height: 117, marginHorizontal: 16, borderRadius: 10, backgroundColor: '#F4F4F4',
    flexDirection: 'row', alignItems: 'center',
  },
  monthStat: { flex: 1, alignItems: 'center', gap: 6 },
  monthStatValue: { fontFamily: type.familyCssBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#000000' },
  monthStatLabel: { fontFamily: type.familyCss, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: color.figmaGray },
  locationNotice: { marginTop: 20, paddingHorizontal: 16, fontFamily: type.familyCss, fontSize: 13, lineHeight: 18, color: color.figmaGray },
  locationRetry: { color: color.brand, textDecorationLine: 'underline' },
  start: { height: 57, marginHorizontal: 10, marginTop: 37, borderRadius: 30, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center', shadowColor: '#000000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  startText: { fontFamily: type.familyCssBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#FFFFFF' },
  pressed: { opacity: 0.8 },
  disabled: { opacity: 0.5 },
});
