import React, { useEffect, useRef, useState } from 'react';
import { Alert, Image, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { Polyline } from 'react-native-maps';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import FigmaStatusBar from '../components/FigmaStatusBar';
import { useActiveWalk, useEndWalk, useStartWalk } from '../hooks/queries';
import { useMyLocation } from '../hooks/useMyLocation';
import { useWalkTracking } from '../hooks/useWalkTracking';
import { formatClock, formatKm, serverTimeMs } from '../utils/walkFormat';
import BaseMap from '../components/BaseMap';
import MapPin from '../components/MapPin';
import WebMap from '../components/WebMap';

const leftMascot = require('../../assets/figma/mascot-walk-right.png');
const rightMascot = require('../../assets/figma/mascot-walk-left.png');

// serverTimeMs 는 utils/walkFormat 로 옮겼다 — 기록 목록도 같은 변환이 필요했는데
// 여기 갇혀 있어서 그쪽만 9시간 어긋난 채로 남아 있었다(실측 08-12).

function useElapsed(startedAt?: string) {
  const [now, setNow] = useState(Date.now());
  const base = useRef<number | null>(null);
  useEffect(() => {
    if (!startedAt) return;
    base.current = serverTimeMs(startedAt);
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [startedAt]);
  return !startedAt || base.current == null ? 0 : Math.max(0, Math.floor((now - base.current) / 1000));
}

export default function WalkActiveScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data: session, isLoading } = useActiveWalk();
  const endWalk = useEndWalk();
  const startWalk = useStartWalk();
  // 부모가 탭 내비게이터면 탭바는 그쪽이 그린다. 라우트 이름으로 가른다 —
  // 탭에서는 'Walk', 스택에서는 'WalkActive' 로 등록돼 있다.
  const inTab = useRoute().name === 'Walk';
  const elapsedSec = useElapsed(session?.started_at);
  const track = useWalkTracking(!!session);
  // 추적 워처의 첫 값이 오기까지 수 초 걸린다(도심에서는 더). 그동안 지도에
  // 중심도 마커도 없으면 "현재 위치가 안 뜬다"로 보인다 — 앱 공용 위치를 폴백으로 쓴다.
  const { point: myPoint } = useMyLocation(true);
  const here = track.current ?? myPoint;

  const onEnd = () => {
    if (!session) return;
    const durationMin = elapsedSec / 60;
    endWalk.mutate(
      { sessionId: session.id, distanceKm: Number(track.distanceKm.toFixed(2)), durationMin },
      {
        onSuccess: (s) => navigation.replace('WalkSummary', { sessionId: s.id, distanceKm: s.distance_km, durationMin: s.duration_min, path: track.path }),
        onError: (e) => Alert.alert('산책을 종료하지 못했습니다', String(e)),
      },
    );
  };

  if (isLoading || !session) {
    // 산책하기 탭이 이 화면을 띄우므로, 진행 중인 산책이 없을 때 여기서 바로
    // 시작할 수 있어야 한다 — 안 그러면 탭을 눌러도 막다른 화면이 된다.
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <StatusBar style="dark" />
        <FigmaStatusBar />
        <View style={styles.center}>
          <Text style={styles.loading}>{isLoading ? '불러오는 중…' : '진행 중인 산책이 없어요'}</Text>
          {!isLoading ? (
            <Pressable
              onPress={() => startWalk.mutate(undefined)}
              disabled={startWalk.isPending}
              accessibilityRole="button"
              style={({ pressed }) => [styles.startBtn, pressed && styles.pressed]}
            >
              <Text style={styles.startBtnText}>
                {startWalk.isPending ? '시작하는 중…' : '산책 시작하기'}
              </Text>
            </Pressable>
          ) : null}
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <View style={styles.body}>
        <View style={styles.greenTop} />
        {/* 실제 위치·실제 경로. 시안 지도 그림을 깔면 걷지 않은 길이 그려진다. */}
        {Platform.OS === 'web' ? (
          <WebMap
            style={styles.map}
            center={here ?? undefined}
            path={track.path}
            zoom={16}
            accessibilityLabel="산책 경로 지도"
          />
        ) : (
          <BaseMap
            style={styles.map}
            region={here ? {
              latitude: here.lat,
              longitude: here.lng,
              latitudeDelta: 0.006,
              longitudeDelta: 0.006,
            } : undefined}
            showsUserLocation
            accessibilityLabel="산책 경로 지도"
          >
            {track.path.length > 1 ? (
              <Polyline
                coordinates={track.path.map((p) => ({ latitude: p.lat, longitude: p.lng }))}
                strokeColor={color.brand}
                strokeWidth={5}
              />
            ) : null}
            {here ? <MapPin kind="me" coordinate={here} title="현재 위치" /> : null}
          </BaseMap>
        )}
        {/* 왼쪽 악어는 카드 **뒤**에 있다(몸 아래쪽이 카드에 가려진다). */}
        <Image source={leftMascot} resizeMode="contain" style={styles.leftMascot} accessibilityLabel="가방을 멘 돌아오길 악어 캐릭터" />

        <View style={styles.metrics}>
          <Metric label="산책한 시간" value={formatClock(elapsedSec)} />
          <Metric label="총 산책 거리" value={`${formatKm(track.distanceKm)}km`} />
        </View>

        {/* 오른쪽 악어는 카드 **앞**에 온다 — 시안에서 오른쪽 카드 모서리를 덮고 있다.
            카드보다 먼저 그리면 카드가 악어를 덮어 뒤로 숨은 것처럼 보인다
            (현장 제보 08-11). 그리는 순서가 곧 앞뒤다. */}
        <Image source={rightMascot} resizeMode="contain" style={styles.rightMascot} accessibilityLabel="산책 중인 돌아오길 악어 캐릭터" />

        <View style={styles.locationHalo}><View style={styles.locationDot} /></View>

        {/* 훅은 권한 거부·측위 실패를 상태로 들고 있었는데 화면이 한 번도 읽지
            않았다 — 거리가 안 재지는 이유가 어디에도 안 보이고 '0.0km' 만 남았다.
            거리 카드 바로 아래에 둔다: 사용자가 이상하다고 느끼는 그 자리다. */}
        {/* 조건을 **상태가 아니라 문구 유무**로 본다. 좌표는 오는데 오차가 커서
            거리를 못 재는 경우는 'error' 가 아니라 'tracking' 이라, 상태로만
            보면 안내가 통째로 묻혔다(실측 08-12: 0.00km 인데 이유가 안 보임). */}
        {track.message ? (
          <View style={styles.trackWarn} accessibilityRole="alert">
            <Text style={styles.trackWarnText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {track.message}
            </Text>
          </View>
        ) : null}

        <Pressable onPress={onEnd} disabled={endWalk.isPending} style={({ pressed }) => [styles.end, pressed && styles.pressed]}>
          <Text style={styles.endText}>{endWalk.isPending ? '저장 중…' : '산책 종료하기'}</Text>
        </Pressable>
      </View>
      {/* 이 화면은 두 곳에서 열린다 — 산책하기 탭(내비게이터가 탭바를 그린다)과
          스택 진입(안 그린다). 탭 안에서 또 그리면 탭바가 두 개로 보인다. */}
      {inTab ? null : <FigmaFlowTabBar mode="citizen" active="register" />}
    </SafeAreaView>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <View style={styles.metric}><Text style={styles.metricLabel}>{label}</Text><Text style={styles.metricValue}>{value}</Text></View>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  body: { flex: 1, overflow: 'hidden' },
  startBtn: { marginTop: 16, height: 50, paddingHorizontal: 34, borderRadius: 25, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center' },
  startBtnText: { fontFamily: type.familyBold, fontSize: 17, color: '#FFFFFF' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  loading: { fontFamily: type.family, fontSize: 13, color: '#525253', textAlign: 'center' },
  greenTop: { position: 'absolute', top: 0, left: 0, right: 0, height: 123, backgroundColor: color.guardianWash },
  map: { position: 'absolute', top: 123, left: 0, right: 0, bottom: 0, width: '100%', height: undefined },
  // Figma 2607:834의 원본 에셋 프레임. body는 44px 상태바 아래에서 시작하므로
  // 원본 좌표 y=46/106을 각각 2/62로 옮긴다.
  leftMascot: { position: 'absolute', top: 2, left: 4, width: 56, height: 79 },
  // 시안: 오른쪽 악어는 왼쪽보다 작고, **발끝이 초록 영역 아래 경계에 닿는다**.
  // 기존값(top 62 + 높이 79 = 141)은 초록 경계 123 을 18px 넘겨 지도 위로 삐져나왔다.
  rightMascot: { position: 'absolute', top: 59, right: 11, width: 41, height: 64 },
  metrics: { position: 'absolute', top: 52, left: 16, right: 16, flexDirection: 'row', gap: 15 },
  // 거리 카드(top 52 + 높이 51) 바로 아래.
  trackWarn: { position: 'absolute', top: 111, left: 16, right: 16, borderRadius: 10, backgroundColor: color.criticalWash, borderWidth: 1, borderColor: color.critical, paddingVertical: 8, paddingHorizontal: 12 },
  trackWarnText: { fontFamily: type.family, fontSize: 12, lineHeight: 17, color: color.criticalInk },
  metric: { flex: 1, height: 51, borderRadius: 10, backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center' },
  metricLabel: { fontFamily: type.family, fontSize: 10, color: color.figmaGray },
  metricValue: { fontFamily: type.familyBold, fontSize: 18, color: '#000000', marginTop: 2 },
  locationHalo: { position: 'absolute', left: '50%', top: '54%', width: 95, height: 95, marginLeft: -48, marginTop: -48, borderRadius: 48, backgroundColor: 'rgba(0,122,255,0.12)', alignItems: 'center', justifyContent: 'center' },
  locationDot: { width: 22, height: 22, borderRadius: 11, backgroundColor: '#007AFF', borderWidth: 3, borderColor: '#FFFFFF' },
  end: { position: 'absolute', left: 10, right: 10, bottom: 38, height: 58, borderRadius: 30, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 } },
  endText: { fontFamily: type.familyBold, fontSize: 20, color: '#FFFFFF' },
  pressed: { opacity: 0.82 },
});
