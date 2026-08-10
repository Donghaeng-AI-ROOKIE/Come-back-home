import React from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import FigmaStatusBar from '../components/FigmaStatusBar';

const summaryMascot = require('../../assets/figma/mascot-summary.png');
const summaryImage = require('../../assets/figma/walk-summary-image.png');

export default function WalkSummaryScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { distanceKm, durationMin } = useRoute<RouteProp<RootStackParamList, 'WalkSummary'>>().params;
  const time = `${String(Math.floor(durationMin)).padStart(2, '0')}:${String(Math.round((durationMin % 1) * 60)).padStart(2, '0')}`;
  return <SafeAreaView style={styles.safe} edges={['top']}><StatusBar style="dark" /><FigmaStatusBar /><View style={styles.body}>
    <Text style={styles.pageTitle}>오늘의 산책 기록</Text>
    <Text style={styles.kicker}>오늘 나의 산책 기록</Text>
    <View style={styles.headlineRow}>
      <Text style={styles.headline}>오늘은 총 {distanceKm.toFixed(1)}km를 걸었어요!</Text>
      <Image source={summaryMascot} resizeMode="contain" style={styles.mascot} accessibilityLabel="돌아오길 악어 캐릭터" />
    </View>
    <Image source={summaryImage} resizeMode="cover" style={styles.image} accessibilityLabel="오늘의 산책 기록 사진" />
    <View style={styles.metrics}><Metric label="산책한 시간" value={time} /><Metric label="총 산책 거리" value={`${distanceKm.toFixed(1)}km`} /></View>
    <Pressable style={styles.primary}><Text style={styles.primaryText}>오늘의 안심 산책 기록 공유하기</Text></Pressable>
    <Pressable style={styles.secondary} onPress={() => navigation.navigate('CitizenTabs', { screen: 'Home' })}><Text style={styles.secondaryText}>다른 산책길 둘러보기</Text></Pressable>
  </View><FigmaFlowTabBar mode="citizen" active="register" /></SafeAreaView>;
}
function Metric({ label, value }: { label: string; value: string }) { return <View style={styles.metric}><Text style={styles.metricLabel}>{label}</Text><Text style={styles.metricValue}>{value}</Text></View>; }
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' }, body: { flex: 1, paddingTop: 31 }, pageTitle: { fontFamily: type.familyBold, fontSize: 20, color: '#000000', marginHorizontal: 20 },
  kicker: { fontFamily: type.family, fontSize: 11, color: '#007AFF', marginHorizontal: 20, marginTop: 45 },
  headlineRow: { flexDirection: 'row', alignItems: 'center', marginHorizontal: 20, marginTop: 3 },
  headline: { fontFamily: type.familyBold, fontSize: 20, color: '#000000' },
  mascot: { width: 34, height: 40, marginLeft: 7 },
  image: { width: '100%', height: 220, backgroundColor: '#E4E4E4', marginTop: 12 }, metrics: { flexDirection: 'row', gap: 15, marginHorizontal: 16, marginTop: 47 }, metric: { flex: 1, height: 50, borderRadius: 10, backgroundColor: color.figmaField, alignItems: 'center', justifyContent: 'center' }, metricLabel: { fontFamily: type.family, fontSize: 10, color: color.figmaGray }, metricValue: { fontFamily: type.familyBold, fontSize: 18, color: '#000000' },
  primary: { height: 58, marginHorizontal: 10, borderRadius: 30, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center', marginTop: 47 }, primaryText: { fontFamily: type.familyBold, fontSize: 18, color: '#FFFFFF' }, secondary: { height: 58, marginHorizontal: 10, borderRadius: 30, backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center', marginTop: 9, shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 } }, secondaryText: { fontFamily: type.familyBold, fontSize: 18, color: '#525253' },
});
