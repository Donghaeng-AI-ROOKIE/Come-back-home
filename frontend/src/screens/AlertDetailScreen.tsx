import { useEffect } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import PersonSilhouette from '../components/PersonSilhouette';
import { useAppModeStore } from '../store/appModeStore';
import { useEngagementStore } from '../store/engagementStore';
import { useActiveAlerts, useGoldenTime, usePresenceCount } from '../hooks/queries';
import { alertToView } from '../data/missingView';


export default function AlertDetailScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'AlertDetail'>>();
  const caseId = route.params.caseId;
  const enterSearch = useAppModeStore((s) => s.enterSearch);
  const dismissCase = useAppModeStore((s) => s.dismissCase);
  const recordDismissed = useEngagementStore((s) => s.recordDismissed);
  const { data: alerts } = useActiveAlerts();
  const alert = alerts?.find((item) => item.caseId === caseId);
  const view = alertToView(alert ?? {});
  const appearance = view.appearance.slice(0, 3);
  const watching = usePresenceCount(caseId);
  const golden = useGoldenTime();

  useEffect(() => { enterSearch(caseId, 'critical'); }, [caseId, enterSearch]);

  const place = alert?.area
    || (alert?.lkp ? `${alert.lkp.lat.toFixed(4)}, ${alert.lkp.lng.toFixed(4)}` : '최종 목격 위치 확인 중');

  const stopShowing = () => {
    dismissCase(caseId);
    recordDismissed();
    navigation.navigate('CitizenTabs', { screen: 'Alerts' });
  };

  return (
    <View style={styles.root}>
      <FigmaStatusBar />
      <View style={styles.canvas}>
        <Text style={styles.title}>긴급 수색 알림</Text>
        <Text style={styles.subtitle}>현재 내 주변 반경과 AI 예상 동선이 겹치는 실종 사건 목록입니다</Text>

        <Pressable style={styles.photoCard} onPress={() => navigation.navigate('Appearance', { caseId })}>
          <Text style={styles.photoLabel}>{alert?.summary || '실종자 인상착의 정보'}</Text>
        </Pressable>

        <View style={styles.chipRow}>
          <View style={[styles.chip, styles.timeChip]}><Text style={styles.timeText}>골든타임 {golden?.label ?? '--:--'}</Text></View>
          {watching != null ? <View style={[styles.chip, styles.peopleChip]}><Text style={styles.peopleText}>•지금 {watching}명이 함께 찾고 있어요</Text></View> : null}
        </View>

        <Pressable style={styles.personCard} onPress={() => navigation.navigate('AlertSync', { caseId })}>
          <View style={styles.searchChip}><Text style={styles.searchChipText}>수색 중({alert ? `${alert.targetCells.length}개 대상 구역` : '범위 확인 중'})</Text></View>
          <PersonSilhouette colors={alert?.appearanceColors} size={62} style={styles.personImage} />
          <Text style={styles.name}>{view.title}</Text>
          <Text style={styles.meta}>{view.meta}</Text>
          <View style={styles.tags}>
            {appearance.map((tag) => <View key={tag} style={styles.tag}><Text style={styles.tagText} numberOfLines={1}>{tag}</Text></View>)}
          </View>
          <Text style={styles.chevron}>›</Text>
        </Pressable>

        <View style={styles.placeCard}>
          <Text style={styles.pin}>●</Text>
          <Text style={styles.placeLabel}>최종 목격 장소</Text>
          <Text style={styles.placeText}>{place}{alert?.lkpTime ? ` · ${new Date(alert.lkpTime).toLocaleString('ko-KR')}` : ''}</Text>
        </View>

        <View style={styles.actions}>
          {/* 시안: 경보를 확인하면 수색화면(지도)으로 간다. 그 화면에 예상 구역·
              참여자 수·제보 진입이 다 있다. 화면은 만들어져 있었는데 라우트가
              등록돼 있지 않아 도달할 수 없었다(08-11). */}
          <Pressable style={[styles.button, styles.seen]} onPress={() => navigation.navigate('Search', { caseId })}>
            <Text style={styles.seenText}>수색 참여하기</Text>
          </Pressable>
          <Pressable style={[styles.button, styles.notSeen]} onPress={() => navigation.goBack()}>
            <Text style={styles.notSeenText}>못 봤어요</Text>
          </Pressable>
        </View>
        <Text style={styles.hint}>최근 한 시간 안에 보신 기억이 있나요?</Text>
        <Pressable style={styles.stop} onPress={stopShowing}><Text style={styles.stopText}>이 사건은 그만 볼래요</Text></Pressable>
      </View>
      <FigmaFlowTabBar mode="citizen" active="alert" />
    </View>
  );
}

const ink = '#525253';
const red = '#E05454';
const wash = '#FFC9CB';

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  canvas: { flex: 1, position: 'relative' },
  title: { position: 'absolute', left: 20, top: 27, fontFamily: type.familyBold, fontSize: 18, lineHeight: 23, color: '#000000' },
  subtitle: { position: 'absolute', left: 20, top: 63, fontFamily: type.familySemiBold, fontSize: 11, lineHeight: 13, color: '#8E8E93' },
  photoCard: { position: 'absolute', left: 23, right: 22, top: 110, height: 100, borderRadius: 10, backgroundColor: '#F7F7F7', alignItems: 'center', justifyContent: 'center' },
  photoLabel: { fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, color: ink },
  chipRow: { position: 'absolute', left: 23, top: 229, height: 21, flexDirection: 'row', gap: 4 },
  chip: { height: 21, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  timeChip: { width: 88, backgroundColor: red },
  peopleChip: { width: 134, backgroundColor: '#D9D9D9' },
  timeText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, color: '#FFFFFF' },
  peopleText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, color: '#414141' },
  personCard: { position: 'absolute', left: 23, right: 22, top: 262, height: 141, borderRadius: 10, backgroundColor: '#FFF4F4', shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 8, shadowOffset: { width: 0, height: 3 } },
  searchChip: { position: 'absolute', left: 16, top: 8, height: 16, width: 107, borderRadius: 20, backgroundColor: wash, alignItems: 'center', justifyContent: 'center' },
  searchChipText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, color: red },
  personImage: { position: 'absolute', left: 16, top: 39, width: 62, height: 62, borderRadius: 31 },
  name: { position: 'absolute', left: 92, top: 38, fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, color: ink },
  meta: { position: 'absolute', left: 92, top: 65, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: ink },
  tags: { position: 'absolute', left: 92, top: 89, flexDirection: 'row', gap: 5 },
  tag: { height: 16, paddingHorizontal: 6, borderRadius: 20, backgroundColor: wash, justifyContent: 'center' },
  tagText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, color: red },
  chevron: { position: 'absolute', right: 17, top: 19, fontSize: 25, lineHeight: 28, color: red },
  placeCard: { position: 'absolute', left: 23, right: 22, top: 416, height: 62, borderRadius: 10, backgroundColor: '#F7F7F7' },
  pin: { position: 'absolute', left: 10, top: 10, fontSize: 7, color: '#8E8E93' },
  placeLabel: { position: 'absolute', left: 28, top: 10, fontFamily: type.familySemiBold, fontSize: 11, lineHeight: 13, color: '#8E8E93' },
  placeText: { position: 'absolute', left: 12, top: 30, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: ink },
  actions: { position: 'absolute', left: 16, right: 16, top: 509, height: 50, flexDirection: 'row', gap: 15 },
  button: { flex: 1, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  seen: { backgroundColor: red },
  notSeen: { backgroundColor: 'rgba(239,239,244,0.94)' },
  seenText: { fontFamily: type.familySemiBold, fontSize: 17, lineHeight: 22, color: '#FFFFFF' },
  notSeenText: { fontFamily: type.familySemiBold, fontSize: 17, lineHeight: 22, color: '#8E8E93' },
  hint: { position: 'absolute', top: 571, left: 0, right: 0, textAlign: 'center', fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#8E8E93' },
  stop: { position: 'absolute', left: 110, right: 110, top: 620, height: 37, alignItems: 'center', justifyContent: 'center' },
  stopText: { fontFamily: type.familySemiBold, fontSize: 11, lineHeight: 13, color: '#8E8E93', textDecorationLine: 'underline' },
});
