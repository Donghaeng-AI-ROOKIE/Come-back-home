import { useEffect } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import { useAppModeStore } from '../store/appModeStore';

const MAP = require('../../assets/figma/search-map.png');
const PERSON = require('../../assets/figma/search-person.png');

export default function AlertSyncScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'AlertSync'>>();
  const caseId = route.params.caseId;
  const enterSearch = useAppModeStore((s) => s.enterSearch);

  useEffect(() => { enterSearch(caseId, 'critical'); }, [caseId, enterSearch]);

  return (
    <View style={styles.root}>
      <Image source={MAP} style={styles.map} resizeMode="cover" />
      <View style={styles.status}><FigmaStatusBar /></View>

      <View style={styles.sheet}>
        <View style={styles.handle} />
        <Text style={styles.kicker}>지금 함께 찾고 있어요</Text>
        <View style={styles.count}><Text style={styles.countText}>•5명</Text></View>

        <Image source={PERSON} style={styles.person} />
        <Text style={styles.name}>김순자</Text>
        <Text style={styles.meta}>78세 • 여성 • 창천동 인근</Text>
        <View style={styles.tags}>
          {['회색 점퍼', '검정 바지', '지팡이'].map((tag) => <View key={tag} style={styles.tag}><Text style={styles.tagText}>{tag}</Text></View>)}
          <Pressable style={styles.photoButton} onPress={() => navigation.navigate('Appearance', { caseId })}><Text style={styles.photoText}>인상착의 사진 보기</Text></Pressable>
        </View>

        <View style={[styles.infoCard, styles.firstInfo]}>
          <Text style={styles.infoIcon}>●</Text>
          <Text style={styles.infoText}>멀리 가지 못하고 한자리에 머물러 계실 수 있어요.{`\n`}골목, 벤치, 건물 그늘을 먼저 살펴봐 주세요.</Text>
        </View>
        <View style={[styles.infoCard, styles.secondInfo]}>
          <Text style={styles.infoIcon}>i</Text>
          <Text style={styles.infoText}>발견하면 가까이 가지 말고 112에 신고해 주세요.{`\n`}이 앱은 신고 채널이 아니라, 함께 실종자를 찾는 앱이에요.</Text>
        </View>

        <Pressable style={styles.reportButton} onPress={() => navigation.navigate('ReportChat', { caseId })}>
          <Text style={styles.reportText}>목격 내용 제보하기</Text>
        </Pressable>
      </View>
      <View style={styles.tabs}><FigmaFlowTabBar mode="citizen" active="alert" /></View>
    </View>
  );
}

const red = '#E05454';
const wash = '#FFC9CB';
const ink = '#525253';

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF', overflow: 'hidden' },
  map: { position: 'absolute', left: 0, right: 0, top: 0, width: '100%', height: 383 },
  status: { position: 'absolute', top: 0, left: 0, right: 0 },
  sheet: { position: 'absolute', left: 0, right: 0, top: 367, bottom: 0, borderTopLeftRadius: 12, borderTopRightRadius: 12, backgroundColor: 'rgba(255,255,255,0.96)', shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 25, shadowOffset: { width: 0, height: -2 } },
  handle: { position: 'absolute', top: 8, left: '45%', right: '45%', height: 5, borderRadius: 3, backgroundColor: 'rgba(0,0,0,0.1)' },
  kicker: { position: 'absolute', left: 17, top: 26, fontFamily: type.family, fontSize: 13, lineHeight: 18, fontWeight: '600', color: 'rgba(0,0,0,0.4)' },
  count: { position: 'absolute', right: 27, top: 28, width: 51, height: 21, borderRadius: 20, backgroundColor: '#D9D9D9', alignItems: 'center', justifyContent: 'center' },
  countText: { fontFamily: type.family, fontSize: 10, lineHeight: 13, fontWeight: '700', color: '#414141' },
  person: { position: 'absolute', left: 17, top: 76, width: 42, height: 42, borderRadius: 21 },
  name: { position: 'absolute', left: 77, top: 62, fontFamily: type.family, fontSize: 17, lineHeight: 22, fontWeight: '700', color: ink },
  meta: { position: 'absolute', left: 77, top: 93, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: ink },
  tags: { position: 'absolute', left: 77, top: 116, flexDirection: 'row', gap: 5, alignItems: 'center' },
  tag: { height: 18, paddingHorizontal: 6, borderRadius: 20, backgroundColor: wash, justifyContent: 'center' },
  tagText: { fontFamily: type.family, fontSize: 10, lineHeight: 13, fontWeight: '700', color: red },
  photoButton: { height: 18, paddingHorizontal: 9, borderRadius: 20, backgroundColor: red, justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 2 },
  photoText: { fontFamily: type.family, fontSize: 10, lineHeight: 13, fontWeight: '700', color: '#FFFFFF' },
  infoCard: { position: 'absolute', left: 23, right: 21, height: 41, borderRadius: 9, backgroundColor: '#FFF4F4' },
  firstInfo: { top: 155 },
  secondInfo: { top: 205 },
  infoIcon: { position: 'absolute', left: 9, top: 11, width: 12, textAlign: 'center', fontSize: 9, fontWeight: '700', color: red },
  infoText: { position: 'absolute', left: 27, top: 7, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: ink },
  reportButton: { position: 'absolute', left: 10, right: 10, top: 265, height: 57, borderRadius: 26, backgroundColor: red, alignItems: 'center', justifyContent: 'center' },
  reportText: { fontFamily: type.family, fontSize: 20, lineHeight: 25, fontWeight: '700', color: '#FFFFFF' },
  tabs: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 85 },
});
