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
import AppearanceFigure from '../components/AppearanceFigure';
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
  const appearance = view.appearance.slice(0, 5);
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

        {/* 이 카드는 **인상착의**를 보여 준다. 그래서 그림도 옷 색이 보이는
            전신(AppearanceFigure)이어야 한다 — 얼굴 배지(PersonSilhouette)를 쓰면
            옷을 설명하는 자리에 얼굴만 떴다(현장 제보 08-12). 아래 인물 카드는
            반대로 "누구인가"라 얼굴 확대가 맞고, 그래서 두 그림이 다르다.

            옆에 있던 요약 문구는 뺐다 — 바로 아래 인물 카드의 칩이 같은 내용
            (상의·하의·신발·체형)을 이미 보여 줘 같은 말을 두 번 하고 있었다.
            그림만 남기고 가운데 놓는다. */}
        <Pressable
          style={styles.photoCard}
          onPress={() => navigation.navigate('Appearance', { caseId })}
          accessibilityRole="button"
          accessibilityLabel="인상착의 자세히 보기"
        >
          <AppearanceFigure colors={alert?.appearanceColors} appearance={alert?.appearance} size={88} style={styles.photoPreview} />
        </Pressable>

        <View style={styles.chipRow}>
          <View style={[styles.chip, styles.timeChip]}><Text style={styles.timeText}>골든타임 {golden?.label ?? '--:--'}</Text></View>
          {watching != null ? <View style={[styles.chip, styles.peopleChip]}><Text style={styles.peopleText}>•지금 {watching}명이 함께 찾고 있어요</Text></View> : null}
        </View>

        <Pressable style={styles.personCard} onPress={() => navigation.navigate('AlertSync', { caseId })}>
          <View style={styles.searchChip}><Text style={styles.searchChipText}>수색 중({alert ? `${alert.targetCells.length}개 대상 구역` : '범위 확인 중'})</Text></View>
          <PersonSilhouette colors={alert?.appearanceColors} appearance={alert?.appearance} size={62} focus="face" style={styles.personImage} />
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
          {/* '봤어요' = **본 것을 제보하겠다**는 뜻이므로 제보 흐름으로 보낸다
              (TipWarn → ReportChat). 버튼 이름이 '수색 참여하기'였을 때 수색
              지도(Search)로 가도록 해 뒀는데, 이름이 바뀐 뒤에도 목적지가 그대로라
              **봤다고 눌렀는데 지도가 떴다**(현장 제보 08-12). 바로 아래 안내문도
              "대화로 제보할 수 있어요"라고 약속하고 있었다.

              수색 지도는 위쪽 인물 카드(→ AlertSync)와 탭으로 여전히 갈 수 있다.
              '비슷한 사람을 봤어요'(AppearanceScreen)와도 목적지가 같아졌다. */}
          <Pressable style={[styles.button, styles.seen]} onPress={() => navigation.navigate('TipWarn', { caseId })}>
            <Text style={styles.seenText}>봤어요</Text>
          </Pressable>
          <Pressable style={[styles.button, styles.notSeen]} onPress={() => navigation.goBack()}>
            <Text style={styles.notSeenText}>못 봤어요</Text>
          </Pressable>
        </View>
        <Text style={styles.hint}>'봤어요'를 누르면 목격 내용을 대화로 편하게 제보할 수 있어요</Text>
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
  subtitle: { position: 'absolute', left: 20, top: 63, fontFamily: type.familySemiBold, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#8E8E93' },
  // 그림 하나만 담으므로 카드도 그림에 맞춰 좁힌다. 가로로 꽉 찬 카드에 그림
  // 하나만 있으면 좌우가 비어 보인다.
  // 높이 108 은 아래 chipRow(top 229)까지의 여유를 남긴 상한이다 — 더 키우려면
  // 그 아래 요소들(전부 절대배치)의 top 을 함께 내려야 한다.
  // 절대배치라 가운데 정렬은 left 50% + 음수 마진으로 잡는다(폭의 절반).
  photoCard: { position: 'absolute', left: '50%', marginLeft: -50, top: 110, width: 100, height: 108, borderRadius: 10, backgroundColor: '#F7F7F7', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 7, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  // 그림은 viewBox 100x160 세로 비율이라 정사각 상자에 넣으면 높이에 맞춰
  // 축소되고 가로가 남는다(88x88 상자에서 실제 그림은 55x88). 상자를 세로로
  // 잡아 그 낭비를 없앤다 — 같은 카드 안에서 그림이 커진다.
  // 배경은 카드에 맡긴다(상자 배경을 두면 카드 안에 상자가 또 보인다).
  photoPreview: { width: 64, height: 96, backgroundColor: 'transparent' },
  chipRow: { position: 'absolute', left: 23, top: 229, height: 21, flexDirection: 'row', gap: 4 },
  chip: { height: 21, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  timeChip: { width: 88, backgroundColor: red },
  peopleChip: { width: 134, backgroundColor: '#D9D9D9' },
  timeText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, letterSpacing: 0.07, color: '#FFFFFF' },
  peopleText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, letterSpacing: 0.07, color: '#414141' },
  personCard: { position: 'absolute', left: 23, right: 22, top: 262, height: 141, borderRadius: 10, backgroundColor: '#FFF4F4', shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 2 },
  searchChip: { position: 'absolute', left: 16, top: 8, height: 16, width: 107, borderRadius: 20, backgroundColor: wash, alignItems: 'center', justifyContent: 'center' },
  searchChipText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, letterSpacing: 0.07, color: red },
  personImage: { position: 'absolute', left: 16, top: 39, width: 62, height: 62, borderRadius: 31 },
  name: { position: 'absolute', left: 92, top: 38, fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: ink },
  meta: { position: 'absolute', left: 92, top: 65, fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: ink },
  tags: { position: 'absolute', left: 92, right: 26, top: 89, flexDirection: 'row', flexWrap: 'wrap', gap: 5 },
  tag: { height: 16, paddingHorizontal: 6, borderRadius: 20, backgroundColor: wash, justifyContent: 'center' },
  tagText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, letterSpacing: 0.07, color: red },
  chevron: { position: 'absolute', right: 17, top: 19, fontSize: 25, lineHeight: 28, color: red },
  placeCard: { position: 'absolute', left: 23, right: 22, top: 416, height: 62, borderRadius: 10, backgroundColor: '#F7F7F7' },
  pin: { position: 'absolute', left: 10, top: 10, fontSize: 7, color: '#8E8E93' },
  placeLabel: { position: 'absolute', left: 28, top: 10, fontFamily: type.familySemiBold, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#8E8E93' },
  placeText: { position: 'absolute', left: 12, top: 30, fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: ink },
  actions: { position: 'absolute', left: 16, right: 16, top: 509, height: 50, flexDirection: 'row', gap: 15 },
  button: { flex: 1, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  seen: { backgroundColor: red, shadowColor: '#000', shadowOpacity: 0.16, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  notSeen: { backgroundColor: 'rgba(239,239,244,0.94)' },
  seenText: { fontFamily: type.familyRobotoSemiBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#FFFFFF' },
  notSeenText: { fontFamily: type.familyRobotoSemiBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#8E8E93' },
  hint: { position: 'absolute', top: 571, left: 0, right: 0, textAlign: 'center', fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#8E8E93' },
  stop: { position: 'absolute', left: 110, right: 110, top: 620, height: 37, alignItems: 'center', justifyContent: 'center' },
  stopText: { fontFamily: type.familySemiBold, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#8E8E93', textDecorationLine: 'underline' },
});
