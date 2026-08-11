import React from 'react';
import { ActivityIndicator, Alert, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import { useActiveWalk, useNearbyWalks, useStartWalk, useWalkStats } from '../hooks/queries';
import { isLocationSettled, useMyLocation } from '../hooks/useMyLocation';
import FigmaLogo from '../components/FigmaLogo';
import FigmaStatusBar from '../components/FigmaStatusBar';
import BaseMap from '../components/BaseMap';
import WebMap from '../components/WebMap';

/** 카드 썸네일 — 실제 그 장소의 지도. 시안의 자리표시 사각형이 있던 자리다. */
function RouteThumb({ lat, lng, style }: { lat: number; lng: number; style: any }) {
  if (Platform.OS === 'web') {
    return <WebMap style={style} center={{ lat, lng }} zoom={15} accessibilityLabel="산책 장소 위치" />;
  }
  return (
    <BaseMap
      style={style}
      liteMode
      scrollEnabled={false}
      region={{ latitude: lat, longitude: lng, latitudeDelta: 0.006, longitudeDelta: 0.006 }}
      accessibilityLabel="산책 장소 위치"
    />
  );
}

export default function CitizenHomeScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data: stats, refetch, isRefetching } = useWalkStats();
  const { data: active } = useActiveWalk();
  const walks = useNearbyWalks();
  // 위치를 못 받은 경우와 주변에 없는 경우는 다른 상황이다 — 같은 문구로 뭉개면
  // 사용자는 앱이 고장 난 줄 알고 권한을 켜 볼 생각을 못 한다.
  const { status: locStatus } = useMyLocation(true);
  const locBlocked = isLocationSettled(locStatus) && locStatus !== 'granted';
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
        {/* Figma의 월간 이미지 영역. 집계값은 바로 위 제목에 실제 서버 값으로 반영하고,
            이 영역에 별도 통계 UI를 더하지 않아 원본의 시각 위계를 보존한다. */}
        <View style={styles.monthCard} />

        <View style={styles.routeHead}><Text style={styles.routeHeadline}>내 주변 산책 루트 추천</Text></View>
        {locBlocked ? (
          <Text style={styles.routeEmpty}>
            위치를 알 수 없어 주변 산책길을 찾지 못했습니다.{'\n'}설정에서 위치 권한을 켜 주세요.
          </Text>
        ) : walks.isLoading || !isLocationSettled(locStatus) ? (
          <ActivityIndicator style={styles.routeLoading} color={color.brand} />
        ) : (walks.data?.length ?? 0) === 0 ? (
          // 지어낸 목록으로 채우지 않는다 — 못 찾았으면 못 찾았다고 말한다.
          <Text style={styles.routeEmpty}>주변에서 산책 장소를 찾지 못했습니다.</Text>
        ) : (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.routeRow}>
            {walks.data!.map((route) => (
              <Pressable key={`${route.name}-${route.lat}`} onPress={() => onStart(route.name)} style={({ pressed }) => [styles.routeCard, pressed && styles.pressed]}>
                <RouteThumb lat={route.lat} lng={route.lng} style={styles.routeImage} />
                <Text style={styles.routeName} numberOfLines={1}>{route.name}</Text>
                <Text style={styles.routeMeta}>{route.distance_km}km · 여기서 걸어서</Text>
              </Pressable>
            ))}
          </ScrollView>
        )}

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
  monthCard: { height: 117, marginHorizontal: 16, borderRadius: 10, backgroundColor: '#DEDEDE' },
  routeLoading: { height: 212, justifyContent: 'center' },
  routeEmpty: { height: 212, paddingHorizontal: 16, fontFamily: type.family, fontSize: 12, lineHeight: 18, color: color.figmaGray },
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
