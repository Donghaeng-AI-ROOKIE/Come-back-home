import { useEffect, useRef } from 'react';
import { ActivityIndicator, Animated, PanResponder, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import { useAppModeStore } from '../store/appModeStore';
import { useActiveAlerts, useGuidance, usePoaPrediction, usePresenceCount } from '../hooks/queries';
import { alertToView } from '../data/missingView';
import BaseMap from '../components/BaseMap';
import PoaHeatmap from '../components/PoaHeatmap';
import MapPin from '../components/MapPin';
import WebMap from '../components/WebMap';
import PersonSilhouette from '../components/PersonSilhouette';
import { useTabBarMetrics } from '../theme/tabBar';


export default function AlertSyncScreen() {
  const tabBar = useTabBarMetrics();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'AlertSync'>>();
  const caseId = route.params.caseId;
  const enterSearch = useAppModeStore((s) => s.enterSearch);
  const { data: alerts } = useActiveAlerts();
  const alert = alerts?.find((item) => item.caseId === caseId);
  const view = alertToView(alert ?? {});
  const appearance = view.appearance.slice(0, 3);
  const watching = usePresenceCount(caseId);
  const guidance = useGuidance(caseId).data?.text;
  const poa = usePoaPrediction(caseId, 0);
  const lkp = alert?.lkp;
  const region = lkp ? {
    latitude: lkp.lat,
    longitude: lkp.lng,
    latitudeDelta: 0.012,
    longitudeDelta: 0.012,
  } : undefined;

  useEffect(() => { enterSearch(caseId, 'critical'); }, [caseId, enterSearch]);

  /**
   * 손잡이를 끌어 시트를 키우고 줄인다.
   *
   * 시트가 고정 높이라 지도를 더 보고 싶어도, 내용을 한눈에 보고 싶어도 방법이
   * 없었다(현장 제보 08-12). 두 자리 사이를 오가게 한다.
   *
   * 제스처를 **손잡이 영역에만** 건다 — 시트 전체에 걸면 안쪽 목록을 넘기려는
   * 손짓과 다툰다.
   *
   * `top` 은 레이아웃 값이라 네이티브 드라이버를 쓸 수 없다. 두 자리 사이
   * 180ms 짜리 짧은 이동이라 부담되지 않는다.
   */
  const sheetTop = useRef(new Animated.Value(SHEET_COLLAPSED_TOP)).current;
  const liveTop = useRef(SHEET_COLLAPSED_TOP);
  const grabbedAt = useRef(SHEET_COLLAPSED_TOP);
  useEffect(() => {
    const id = sheetTop.addListener(({ value }) => { liveTop.current = value; });
    return () => sheetTop.removeListener(id);
  }, [sheetTop]);

  const pan = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_e, g) => Math.abs(g.dy) > 2,
      onPanResponderGrant: () => { grabbedAt.current = liveTop.current; },
      onPanResponderMove: (_e, g) => {
        const next = Math.min(SHEET_COLLAPSED_TOP, Math.max(SHEET_EXPANDED_TOP, grabbedAt.current + g.dy));
        sheetTop.setValue(next);
      },
      onPanResponderRelease: (_e, g) => {
        const mid = (SHEET_COLLAPSED_TOP + SHEET_EXPANDED_TOP) / 2;
        const snap = (to: number) =>
          Animated.timing(sheetTop, { toValue: to, duration: 180, useNativeDriver: false }).start();
        // 거의 안 움직였으면 탭으로 보고 반대쪽으로 넘긴다.
        if (Math.abs(g.dy) < 4) {
          snap(grabbedAt.current > mid ? SHEET_EXPANDED_TOP : SHEET_COLLAPSED_TOP);
          return;
        }
        // 빠르게 튕기면 손이 간 방향을, 천천히 놓으면 가까운 쪽을 따른다.
        if (g.vy > 0.5) snap(SHEET_COLLAPSED_TOP);
        else if (g.vy < -0.5) snap(SHEET_EXPANDED_TOP);
        else snap(grabbedAt.current + g.dy < mid ? SHEET_EXPANDED_TOP : SHEET_COLLAPSED_TOP);
      },
    }),
  ).current;


  return (
    <View style={styles.root}>
      {/* 웹은 react-native-maps 가 없다. 시안 지도 그림을 깔면 예측 결과로 오인되므로
          실제 OSM 타일 + 서버가 준 실제 POA 셀을 그린다(components/WebMap). */}
      {Platform.OS === 'web' ? (
        <WebMap
          style={styles.map}
          center={lkp}
          marker={lkp}
          grid={poa.data}
          accessibilityLabel="실제 발견확률 지도"
        />
      ) : (
        <BaseMap style={styles.map} region={region} accessibilityLabel={poa.data ? `실제 발견확률 지도. ${poa.data.topLabel}` : '발견확률 지도를 불러오는 중'}>
          {poa.data ? <PoaHeatmap grid={poa.data} /> : null}
          {lkp ? <MapPin kind="lastSeen" coordinate={lkp} title="최종 목격 위치" /> : null}
        </BaseMap>
      )}
      {poa.isLoading && Platform.OS !== 'web' ? <ActivityIndicator style={styles.mapLoading} color={red} /> : null}
      <View style={styles.status}><FigmaStatusBar /></View>

      {/* 시트 안 내용은 **스크롤된다.** 예전에는 전부 절대좌표라 시트 높이보다
          길면 그대로 잘렸고, 화면이 좁은 기기에서는 '목격 내용 제보하기' 버튼이
          하단 탭바에 가려 아예 누를 수 없었다(현장 제보 08-12).
          손잡이는 시트에 고정하고 그 아래만 흐름 배치로 바꿔 스크롤에 맡긴다 —
          절대좌표로는 내용 높이를 알 수 없어 스크롤 자체가 성립하지 않는다. */}
      <Animated.View style={[styles.sheet, { top: sheetTop, bottom: tabBar.height }]}>
        <View
          style={styles.grip}
          {...pan.panHandlers}
          accessibilityRole="adjustable"
          accessibilityLabel="실종자 정보 카드 크기 조절"
        >
          <View style={styles.handle} />
        </View>
        <ScrollView contentContainerStyle={styles.sheetBody} showsVerticalScrollIndicator={false}>
          <View style={styles.kickerRow}>
            <Text style={styles.kicker}>지금 함께 찾고 있어요</Text>
            {watching != null ? <View style={styles.count}><Text style={styles.countText}>•{watching}명</Text></View> : null}
          </View>

          <View style={styles.personRow}>
            <PersonSilhouette colors={alert?.appearanceColors} appearance={alert?.appearance} size={42} style={styles.person} />
            <View style={styles.personInfo}>
              <Text style={styles.name}>{view.title}</Text>
              <Text style={styles.meta}>{view.meta}</Text>
              <View style={styles.tags}>
                {appearance.map((tag) => <View key={tag} style={styles.tag}><Text style={styles.tagText} numberOfLines={1}>{tag}</Text></View>)}
                <Pressable style={styles.photoButton} onPress={() => navigation.navigate('Appearance', { caseId })}><Text style={styles.photoText}>인상착의 사진 보기</Text></Pressable>
              </View>
            </View>
          </View>

          <View style={[styles.infoCard, styles.firstInfo]}>
            <Text style={styles.infoIcon}>●</Text>
            <Text style={styles.infoText} numberOfLines={2}>{guidance || '사건에 맞는 수색 안내를 불러오고 있습니다.'}</Text>
          </View>
          <View style={styles.infoCard}>
            <Text style={styles.infoIcon}>i</Text>
            <Text style={styles.infoText}>발견하면 가까이 가지 말고 112에 신고해 주세요.{`\n`}이 앱은 신고 채널이 아니라, 함께 실종자를 찾는 앱이에요.</Text>
          </View>

          <Pressable style={styles.reportButton} onPress={() => navigation.navigate('ReportChat', { caseId })}>
            <Text style={styles.reportText}>목격 내용 제보하기</Text>
          </Pressable>
        </ScrollView>
      </Animated.View>
      <View style={[styles.tabs, { height: tabBar.height }]}><FigmaFlowTabBar mode="citizen" active="alert" /></View>
    </View>
  );
}

/**
 * 시트가 멈추는 두 자리.
 *
 * 접힘(367)은 시안 기본값 — 지도가 주인공이고 시트는 요약만 보여 준다.
 * 펼침(140)은 상태바와 지도 일부만 남기고 시트 내용을 최대한 보여 준다.
 * 중간에서 손을 떼면 가까운 쪽으로 붙는다.
 */
const SHEET_COLLAPSED_TOP = 367;
const SHEET_EXPANDED_TOP = 140;

const red = color.figmaRed;
const wash = '#FFC9CB';
const ink = '#525253';

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF', overflow: 'hidden' },
  map: { position: 'absolute', left: 0, right: 0, top: 0, width: '100%', height: 383 },
  mapLoading: { position: 'absolute', top: 170, left: 0, right: 0 },
  status: { position: 'absolute', top: 0, left: 0, right: 0 },
  sheet: { position: 'absolute', left: 0, right: 0, borderTopLeftRadius: 12, borderTopRightRadius: 12, backgroundColor: 'rgba(255,255,255,0.96)', shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 25, shadowOffset: { width: 0, height: -2 }, elevation: 8 },
  // 손잡이는 얇지만 잡는 영역은 넉넉해야 한다 — 5px 막대만 노리게 하면 안 잡힌다.
  grip: { paddingTop: 8, paddingBottom: 8, alignItems: 'center' },
  handle: { width: 40, height: 5, borderRadius: 3, backgroundColor: 'rgba(0,0,0,0.1)' },
  // 시안의 top 값을 간격으로 옮긴 것 — 812 캔버스에서는 픽셀이 그대로다.
  sheetBody: { paddingTop: 5, paddingBottom: 12 },
  kickerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingLeft: 17, paddingRight: 27 },
  kicker: { fontFamily: type.familySemiBold, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: 'rgba(0,0,0,0.4)' },
  count: { width: 51, height: 21, borderRadius: 20, backgroundColor: '#D9D9D9', alignItems: 'center', justifyContent: 'center' },
  countText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, letterSpacing: 0.07, color: '#414141' },
  personRow: { flexDirection: 'row', marginTop: 18, paddingLeft: 17, paddingRight: 21 },
  person: { width: 42, height: 42, borderRadius: 21, marginTop: 14 },
  personInfo: { flex: 1, marginLeft: 18 },
  name: { fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: ink },
  meta: { marginTop: 9, fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: ink },
  tags: { marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 5, alignItems: 'center' },
  tag: { height: 18, paddingHorizontal: 6, borderRadius: 20, backgroundColor: wash, justifyContent: 'center' },
  tagText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, letterSpacing: 0.07, color: red },
  photoButton: { height: 18, paddingHorizontal: 9, borderRadius: 20, backgroundColor: red, justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 2, elevation: 2 },
  photoText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, letterSpacing: 0.07, color: '#FFFFFF' },
  // 고정 높이 41 을 떼고 패딩으로 — 안내문이 길어지면 잘렸다.
  infoCard: { marginLeft: 23, marginRight: 21, marginTop: 9, minHeight: 41, borderRadius: 9, backgroundColor: '#FFF4F4', flexDirection: 'row', alignItems: 'center', paddingVertical: 7, paddingLeft: 9, paddingRight: 12 },
  firstInfo: { marginTop: 21 },
  infoIcon: { width: 12, textAlign: 'center', fontSize: 9, fontWeight: '700', color: red },
  infoText: { flex: 1, marginLeft: 6, fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: ink },
  reportButton: { marginHorizontal: 10, marginTop: 19, height: 57, borderRadius: 26, backgroundColor: red, alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  reportText: { fontFamily: type.familyCssBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#FFFFFF' },
  tabs: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
