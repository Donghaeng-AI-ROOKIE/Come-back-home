import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import PersonSilhouette from '../components/PersonSilhouette';
import FigmaStatusBar from '../components/FigmaStatusBar';
import { useActiveAlerts } from '../hooks/queries';
import { alertToView } from '../data/missingView';

export default function AppearanceScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { caseId } = useRoute<RouteProp<RootStackParamList, 'Appearance'>>().params;
  const { data: alerts } = useActiveAlerts();
  const alert = alerts?.find((item) => item.caseId === caseId);
  const view = alertToView(alert ?? {});
  const appearance = view.appearance.slice(0, 3);
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <View style={styles.body}>
        <Text style={styles.title}>실종자 인상착의 정보</Text>
        <Text style={styles.subtitle}>신고 시 등록된 인상착의 정보입니다 (사진은 수집하지 않습니다)</Text>
        <View style={styles.card}>
          {/* 사진은 받지 않는다(08-07 결정) — 자리표시 사진을 두면 남의 얼굴이
              실종자로 읽힌다. 보호자가 입력한 옷 색으로 실루엣을 그린다. */}
          <PersonSilhouette colors={alert?.appearanceColors} appearance={alert?.appearance} size={198} rounded={false} style={styles.photo} />
          <View style={styles.chips}>
            {(appearance.length ? appearance : ['정보 확인 중']).map((label) => <View key={label} style={styles.chip}><Text style={styles.chipText} numberOfLines={1}>{label}</Text></View>)}
          </View>
          <Text style={styles.summary}>{view.title} / {view.meta}</Text>
        </View>
        <Pressable style={styles.primary} onPress={() => navigation.navigate('TipWarn', { caseId })}><Text style={styles.primaryText}>비슷한 사람을 봤어요</Text></Pressable>
        <Pressable style={styles.secondary} onPress={() => navigation.goBack()}><Text style={styles.secondaryText}>비슷한 사람을 보지 못했어요</Text></Pressable>
      </View>
      <FigmaFlowTabBar mode="citizen" active="alert" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  body: { flex: 1, position: 'relative' },
  title: { position: 'absolute', left: 20, top: 27, fontFamily: type.familyExtraBold, fontSize: 18, lineHeight: 22, color: '#000000' },
  subtitle: { position: 'absolute', left: 20, top: 64, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: color.figmaGray },
  card: { position: 'absolute', left: 23, right: 23, top: 107, height: 348, borderRadius: 10, backgroundColor: '#FFFFFF', alignItems: 'center', shadowColor: '#000000', shadowOpacity: 0.1, shadowRadius: 7, shadowOffset: { width: 0, height: 2 } },
  photo: { position: 'absolute', top: 31, width: 247, height: 198, borderRadius: 10, backgroundColor: '#F2F2F2' },
  chips: { position: 'absolute', top: 247, flexDirection: 'row', gap: 6 },
  chip: { height: 18, borderRadius: 9, backgroundColor: '#FFC9CB', paddingHorizontal: 8, alignItems: 'center', justifyContent: 'center' },
  chipText: { fontFamily: type.familyMedium, fontSize: 10, lineHeight: 13, color: color.figmaRed },
  summary: { position: 'absolute', top: 282, fontFamily: type.familySemiBold, fontSize: 17, lineHeight: 22, color: '#525253' },
  primary: { position: 'absolute', left: 10, right: 10, top: 491, height: 58, borderRadius: 30, backgroundColor: color.figmaRed, alignItems: 'center', justifyContent: 'center', shadowColor: '#000000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 } },
  primaryText: { fontFamily: type.familyBold, fontSize: 20, color: '#FFFFFF' },
  secondary: { position: 'absolute', left: 10, right: 10, top: 560, height: 58, borderRadius: 30, backgroundColor: '#D8D8D8', alignItems: 'center', justifyContent: 'center', shadowColor: '#000000', shadowOpacity: 0.14, shadowRadius: 2, shadowOffset: { width: 0, height: 2 } },
  secondaryText: { fontFamily: type.familyBold, fontSize: 20, color: '#9A9A9F' },
});
