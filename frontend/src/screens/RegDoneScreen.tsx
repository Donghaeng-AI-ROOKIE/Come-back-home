import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import FigmaLogo from '../components/FigmaLogo';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import DoneCheck from '../../assets/figma/done-check.svg';
import DoneHome from '../../assets/figma/done-home.svg';
import BookmarkIcon from '../../assets/figma/detail-bookmark.svg';
import { useGuardianStore } from '../store/guardianStore';
import FigmaStatusBar from '../components/FigmaStatusBar';

export default function RegDoneScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { name, age } = useRoute<RouteProp<RootStackParamList, 'RegDone'>>().params;
  const persona = useGuardianStore((s) => s.persona);
  return <SafeAreaView style={styles.safe} edges={['top']}><StatusBar style="dark" /><FigmaStatusBar /><View style={styles.body}>
    <FigmaLogo mode="guardian" /><DoneCheck width={36} height={36} color={color.brand} style={styles.check} /><Text style={styles.title}>사전 등록 완료</Text><Text style={styles.subtitle}>답변해주신 내용이 안전하게 저장되었습니다.</Text>
    <View style={styles.sectionRow}><BookmarkIcon width={9} height={11} color={color.brand} style={styles.bookmark} /><Text style={styles.section}>요약 정보</Text></View><View style={styles.card}><Row k="이름" v={name || persona?.name || '이름'} /><Row k="연령" v={age ? `${age}세` : persona ? `${persona.age}세` : '연령'} /><Row k="건강 상태" v={persona?.type === 'dementia' ? '치매' : '건강 상태'} /><Row k="관련 장소" v={persona?.attraction_points?.[0]?.label ?? '관련 장소'} /></View>
    <Pressable style={styles.home} onPress={() => navigation.navigate('GuardianTabs', { screen: 'GuardianHome' })}><View style={styles.homeLabel}><DoneHome width={14} height={14} color={color.brand} /><Text style={styles.homeText}>홈으로 돌아가기</Text></View></Pressable>
  </View><FigmaFlowTabBar mode="guardian" active="register" /></SafeAreaView>;
}
function Row({ k, v }: { k: string; v: string }) { return <View style={styles.row}><Text style={styles.key}>{k}</Text><Text style={styles.value}>{v}</Text></View>; }
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.guardianWash }, body: { flex: 1, alignItems: 'center', paddingTop: 84 }, check: { marginTop: 30 }, title: { fontFamily: type.familySemiBold, fontSize: 20, color: '#000000', marginTop: 7 }, subtitle: { fontFamily: type.familyMedium, fontSize: 14, color: '#525253', marginTop: 12 },
  sectionRow: { width: 329, flexDirection: 'row', alignItems: 'center', marginTop: 45 }, bookmark: { marginLeft: 2, marginRight: 9 }, section: { fontFamily: type.familySemiBold, fontSize: 14, color: '#000000' }, card: { width: 329, height: 124, borderRadius: 10, backgroundColor: '#FFFFFF', paddingHorizontal: 17, paddingVertical: 13, marginTop: 10 }, row: { flexDirection: 'row', height: 25, alignItems: 'center' }, key: { width: 58, fontFamily: type.familySemiBold, fontSize: 12, color: '#316837' }, value: { fontFamily: type.family, fontSize: 12, color: '#4D4D4D' }, home: { width: 255, height: 38, borderRadius: 22, backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center', marginTop: 44, shadowColor: '#000', shadowOpacity: 0.15, shadowRadius: 2, shadowOffset: { width: 1, height: 1 } }, homeLabel: { flexDirection: 'row', alignItems: 'center', gap: 7 }, homeText: { fontFamily: type.familyMedium, fontSize: 14, color: '#525253' },
});
