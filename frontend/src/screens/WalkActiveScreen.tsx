import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Image, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { Polyline } from 'react-native-maps';
import Svg, { Circle, Path } from 'react-native-svg';
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
import { clearWalkProgress } from '../utils/walkProgress';
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
  // 세션 id 를 넘긴다 — 훅이 이 산책의 진행분(거리·경로)을 이어받는다.
  // 불리언만 넘기던 시절에는 화면이 다시 마운트될 때마다 0.00km 로 돌아갔다
  // (실측 08-12: 걷는 중에 실종 신고가 접수되자 경보 관문이 화면 트리를 새로
  // 마운트했고, 시간만 남고 거리·경로가 사라졌다).
  const track = useWalkTracking(session?.id ?? null);
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
        onSuccess: (s) => {
          // 서버에 기록이 남았으니 기기에 맡겨 둔 경로는 지운다 — 진행 중인
          // 산책을 이어 주려던 것이지 이동 이력을 모으려던 게 아니다.
          void clearWalkProgress();
          navigation.replace('WalkSummary', { sessionId: s.id, distanceKm: s.distance_km, durationMin: s.duration_min, path: track.path });
        },
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

        {/* 내 위치 버튼 — 네이버 지도처럼 지도 오른쪽 아래.
            지도는 이미 현재 위치를 따라가므로 "중심 맞추기"는 할 일이 없다.
            이 버튼이 하는 일은 **새 측위를 즉시 한 번 받는 것**이다 — 실내에서
            막 나왔거나 한참 서 있다가 다시 걷기 시작한 순간, 워처가 낡은 좌표에
            머물러 있을 수 있다. 그때 사용자가 직접 당길 수 있어야 한다. */}
        <Pressable
          onPress={track.refresh}
          disabled={track.refreshing}
          accessibilityRole="button"
          accessibilityLabel="현재 위치 다시 잡기"
          style={({ pressed }) => [styles.locateBtn, pressed && styles.pressed]}
        >
          {track.refreshing
            ? <ActivityIndicator size="small" color={color.brand} />
            : (
              <Svg width={22} height={22} viewBox="0 0 24 24">
                {/* 조준선 + 가운데 점 — '지금 내 위치를 다시 잡는다'는 뜻이 가장
                    분명한 모양이다. 이모지는 폰트에 없으면 □ 로 깨진다(08-11). */}
                <Circle cx="12" cy="12" r="6" stroke={color.brand} strokeWidth="1.8" fill="none" />
                <Circle cx="12" cy="12" r="2.4" fill={color.brand} />
                <Path d="M12 1.5v3.2M12 19.3v3.2M1.5 12h3.2M19.3 12h3.2"
                      stroke={color.brand} strokeWidth="1.8" strokeLinecap="round" />
              </Svg>
            )}
        </Pressable>

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
  startBtn: { marginTop: 16, height: 50, paddingHorizontal: 34, borderRadius: 25, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center', shadowColor: '#000000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  startBtnText: { fontFamily: type.familyCssBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#FFFFFF' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  loading: { fontFamily: type.familyCss, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#525253', textAlign: 'center' },
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
  trackWarnText: { fontFamily: type.familyCss, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: color.criticalInk },
  metric: { flex: 1, height: 51, borderRadius: 10, backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center' },
  metricLabel: { fontFamily: type.familyCssSemiBold, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: color.figmaGray },
  metricValue: { fontFamily: type.familyCssExtraBold, fontSize: 18, lineHeight: 23, color: '#000000', marginTop: 2 },
  /**
   * 내 위치 표식 — **지도의 중심에 정확히 얹혀야 한다.**
   *
   * 지도는 현재 위치를 중심으로 그려지므로(`center={here}`), 이 점은 지도 영역의
   * 한가운데에 있어야 실제 위치를 가리킨다. 그런데 `top: '54%'` 는 지도가 아니라
   * **화면 전체(body) 기준**이었다. 지도는 `top: 123` 부터 시작하므로 둘의 중심이
   * 어긋난다 — 실측 08-12: 점이 지도 중심보다 **37px 위**, 축척상 약 70m 북쪽을
   * 가리키고 있었다. 산책 중 "내가 여기 있다"는 표시가 70m 틀린 셈이다.
   *
   * 지도 중심 = 123 + (H-123)/2 = 0.5H + 61.5 (H = body 높이).
   * 그래서 화면 중앙(50%)에서 61.5 만큼 내린다 — marginTop 은 반지름(47.5)을
   * 빼야 하므로 61.5 - 47.5 = 14.
   */
  locationHalo: { position: 'absolute', left: '50%', top: '50%', width: 95, height: 95, marginLeft: -48, marginTop: 14, borderRadius: 48, backgroundColor: 'rgba(0,122,255,0.12)', alignItems: 'center', justifyContent: 'center' },
  // 지도 오른쪽 아래. '산책 종료하기' 버튼 위로 띄워 서로 가리지 않게 한다.
  locateBtn: { position: 'absolute', right: 16, bottom: 118, width: 44, height: 44, borderRadius: 22, backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center', shadowColor: '#000000', shadowOpacity: 0.18, shadowRadius: 4, shadowOffset: { width: 0, height: 2 }, elevation: 4 },
  locationDot: { width: 22, height: 22, borderRadius: 11, backgroundColor: '#007AFF', borderWidth: 3, borderColor: '#FFFFFF' },
  end: { position: 'absolute', left: 10, right: 10, bottom: 38, height: 58, borderRadius: 30, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center', shadowColor: '#000000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  endText: { fontFamily: type.familyCssBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#FFFFFF' },
  pressed: { opacity: 0.82 },
});
