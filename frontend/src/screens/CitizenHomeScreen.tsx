import React from 'react';
import { Alert, Image, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import { useActiveWalk, useStartWalk, useWalkStats } from '../hooks/queries';
import FigmaLogo from '../components/FigmaLogo';
import FigmaStatusBar from '../components/FigmaStatusBar';

const homeImage = require('../../assets/figma/citizen-home-image.png');

const ROUTES = [
  { id: 'gyeongui', name: '경의선 숲길', meta: '1.2km · 산책하기 좋은 길' },
  { id: 'mangwon', name: '망원 한강공원', meta: '2.5km · 강변 산책길' },
  { id: 'hongje', name: '홍제천 산책길', meta: '1.7km · 평탄한 길' },
];

export default function CitizenHomeScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data: stats, refetch, isRefetching } = useWalkStats();
  const { data: active } = useActiveWalk();
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
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
      >
        <View style={styles.logoRow}><FigmaLogo mode="citizen" /></View>

        <View style={styles.monthHead}>
          <Text style={styles.kicker}>이번 달 나의 산책 기록</Text>
          <Text style={styles.monthTitle}>8월에는 총 {(stats?.month_km ?? 0).toFixed(1)}km를 걸었네요!</Text>
        </View>
        <Image source={homeImage} resizeMode="cover" style={styles.monthImage} accessibilityLabel="이번 달 산책 기록 이미지" />

        <View style={styles.routeHead}><Text style={styles.routeHeadline}>내 주변 산책 루트 추천</Text></View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.routeRow}>
          {ROUTES.map((route) => (
            <Pressable key={route.id} onPress={() => onStart(route.name)} style={({ pressed }) => [styles.routeCard, pressed && styles.pressed]}>
              <Image source={homeImage} resizeMode="cover" style={styles.routeImage} accessibilityLabel={`${route.name} 산책길 이미지`} />
              <Text style={styles.routeName}>{route.name}</Text>
              <Text style={styles.routeMeta}>{route.meta}</Text>
            </Pressable>
          ))}
        </ScrollView>

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
  monthHead: { height: 87, paddingHorizontal: 16, paddingTop: 18 },
  kicker: { fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#007AFF' },
  monthTitle: { fontFamily: type.familySemiBold, fontSize: 17, lineHeight: 22, color: '#000000', marginTop: 5 },
  monthImage: { width: undefined, height: 117, marginHorizontal: 16, borderRadius: 10, backgroundColor: '#E6E6E6' },
  routeHead: { height: 56, justifyContent: 'center', paddingHorizontal: 16 },
  routeHeadline: { fontFamily: type.familySemiBold, fontSize: 18, lineHeight: 22, color: '#000000' },
  routeRow: { paddingLeft: 16, paddingRight: 16, gap: 8 },
  routeCard: { width: 164, height: 212 },
  routeImage: { width: 164, height: 162, borderRadius: 10, backgroundColor: '#DEDEDE' },
  routeName: { fontFamily: type.familySemiBold, fontSize: 14, lineHeight: 18, color: '#000000', marginTop: 10 },
  routeMeta: { fontFamily: type.family, fontSize: 11, lineHeight: 18, color: color.figmaGray },
  start: { height: 57, marginHorizontal: 10, marginTop: 37, borderRadius: 10, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center' },
  startText: { fontFamily: type.familyBold, fontSize: 17, color: '#FFFFFF' },
  pressed: { opacity: 0.8 },
  disabled: { opacity: 0.5 },
});
