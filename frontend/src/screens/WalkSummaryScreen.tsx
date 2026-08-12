import React from 'react';
import { Image, Platform, Pressable, Share, StyleSheet, Text, View } from 'react-native';
import { Polyline } from 'react-native-maps';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import FigmaStatusBar from '../components/FigmaStatusBar';
import BaseMap from '../components/BaseMap';
import WebMap from '../components/WebMap';
import MapPin from '../components/MapPin';
import { formatClock, formatKm } from '../utils/walkFormat';

const summaryMascot = require('../../assets/figma/mascot-summary.png');

export default function WalkSummaryScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { distanceKm, durationMin } = useRoute<RouteProp<RootStackParamList, 'WalkSummary'>>().params;
  // 분을 정수부·소수부로 쪼개 붙이면 반올림이 60 초를 만들어 '03:60' 이 나온다.
  // 초로 환산해 한 번에 자른다 — 산책 중 화면과 같은 포맷터를 쓴다.
  const time = formatClock(durationMin * 60);
  const km = formatKm(distanceKm);
  const path = useRoute<RouteProp<RootStackParamList, 'WalkSummary'>>().params.path ?? [];
  const shareWalk = () => Share.share({
    message: `오늘 돌아오길과 ${km}km를 ${time} 동안 걸었어요. 우리 동네 안심 산책 기록을 함께 나눠요!`,
  });
  // 시안의 회색 사각형 자리 — 오늘 **실제로 걸은 길**을 그린다. 경로는 이 기기
  // 안에서만 넘어온 값이다(서버는 산책 좌표를 저장하지 않는다).
  const mid = path.length ? path[Math.floor(path.length / 2)] : null;
  return <SafeAreaView style={styles.safe} edges={['top']}><StatusBar style="dark" /><FigmaStatusBar /><View style={styles.body}>
    <Text style={styles.kicker}>오늘 나의 산책 기록</Text>
    <View style={styles.headlineRow}>
      <Text style={styles.headline}>오늘은 총 {km}km를 걸었어요!</Text>
      <Image source={summaryMascot} resizeMode="contain" style={styles.mascot} accessibilityLabel="돌아오길 악어 캐릭터" />
    </View>
    {mid == null ? (
      <View style={[styles.image, styles.imageEmpty]}><Text style={styles.imageEmptyText}>경로를 기록하지 못했습니다</Text></View>
    ) : Platform.OS === 'web' ? (
      <WebMap style={styles.image} center={mid} path={path} zoom={15} accessibilityLabel="오늘 걸은 경로 지도" />
    ) : (
      <BaseMap
        style={styles.image}
        liteMode
        scrollEnabled={false}
        region={{ latitude: mid.lat, longitude: mid.lng, latitudeDelta: 0.008, longitudeDelta: 0.008 }}
        accessibilityLabel="오늘 걸은 경로 지도"
      >
        {path.length > 1 ? (
          <Polyline coordinates={path.map((p) => ({ latitude: p.lat, longitude: p.lng }))} strokeColor={color.brand} strokeWidth={5} />
        ) : null}
        <MapPin kind="me" coordinate={path[path.length - 1]} title="도착" />
      </BaseMap>
    )}
    <View style={styles.metrics}><Metric label="산책한 시간" value={time} /><Metric label="총 산책 거리" value={`${km}km`} /></View>
    <Pressable style={styles.primary} onPress={shareWalk}><Text style={styles.primaryText}>오늘의 안심 산책 기록 공유하기</Text></Pressable>
    <Pressable style={styles.secondary} onPress={() => navigation.navigate('CitizenTabs', { screen: 'Home' })}><Text style={styles.secondaryText}>다른 산책길 둘러보기</Text></Pressable>
  </View><FigmaFlowTabBar mode="citizen" active="register" /></SafeAreaView>;
}
function Metric({ label, value }: { label: string; value: string }) { return <View style={styles.metric}><Text style={styles.metricLabel}>{label}</Text><Text style={styles.metricValue}>{value}</Text></View>; }
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' }, body: { flex: 1, position: 'relative' },
  kicker: { position: 'absolute', left: 20, top: 94, fontFamily: type.familyCssSemiBold, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#007AFF' },
  headlineRow: { position: 'absolute', left: 20, right: 20, top: 111, height: 45, flexDirection: 'row', alignItems: 'center' },
  headline: { fontFamily: type.familyCssExtraBold, fontSize: 18, lineHeight: 23, color: '#000000' },
  mascot: { width: 34, height: 40, marginLeft: 7 },
  image: { position: 'absolute', left: 0, right: 0, top: 156, width: '100%', height: 220, backgroundColor: '#E4E4E4' }, imageEmpty: { alignItems: 'center', justifyContent: 'center' }, imageEmptyText: { fontFamily: type.familyCss, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: color.figmaGray }, metrics: { position: 'absolute', left: 16, right: 16, top: 424, height: 50, flexDirection: 'row', gap: 15 }, metric: { flex: 1, height: 50, borderRadius: 10, backgroundColor: color.figmaField, alignItems: 'center', justifyContent: 'center' }, metricLabel: { fontFamily: type.familyCssSemiBold, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: color.figmaGray }, metricValue: { fontFamily: type.familyCssExtraBold, fontSize: 18, lineHeight: 23, color: '#000000' },
  primary: { position: 'absolute', left: 10, right: 10, top: 520, height: 58, borderRadius: 30, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 3 }, primaryText: { fontFamily: type.familyCssBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#FFFFFF' }, secondary: { position: 'absolute', left: 10, right: 10, top: 587, height: 58, borderRadius: 30, backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 3 }, secondaryText: { fontFamily: type.familyCssBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#525253' },
});
