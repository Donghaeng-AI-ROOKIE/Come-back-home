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
import FigmaStatusBar from '../components/FigmaStatusBar';
import BellIcon from '../../assets/figma/tip-warning-bell.svg';

export default function TipWarnScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { caseId } = useRoute<RouteProp<RootStackParamList, 'TipWarn'>>().params;
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <View style={styles.body}>
        <Text style={styles.title}>실종자 제보</Text>
        <View style={styles.warn}>
          <View style={styles.warnHead}><BellIcon width={28} height={28} /><Text style={styles.warnTitle}>제보 전 주의사항 안내</Text></View>
          <Text style={styles.warnText}>허위 또는 장난 제보는 실종자를 찾는 골든타임을 심각하게 훼손합니다.</Text>
          <Text style={styles.warnText}>허위 신고 시 법적 처벌을 받을 수 있으니 신중하게 제보해 주세요.</Text>
        </View>
        <Pressable style={styles.primary} onPress={() => navigation.replace('ReportChat', { caseId })}><Text style={styles.primaryText}>비슷한 사람을 봤어요</Text></Pressable>
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
  warn: { position: 'absolute', left: 23, right: 23, top: 92, height: 128, borderRadius: 10, backgroundColor: '#FFF0F1', paddingHorizontal: 14, paddingTop: 18, shadowColor: '#000000', shadowOpacity: 0.1, shadowRadius: 7, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  warnHead: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  warnTitle: { fontFamily: type.familySemiBold, fontSize: 19, lineHeight: 25, color: '#525253' },
  warnText: { fontFamily: type.family, fontSize: 11, lineHeight: 15, color: color.figmaRed, marginTop: 12 },
  primary: { position: 'absolute', left: 10, right: 10, top: 250, height: 57, borderRadius: 29, backgroundColor: color.figmaRed, alignItems: 'center', justifyContent: 'center', shadowColor: '#000000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  primaryText: { fontFamily: type.familyBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#FFFFFF' },
  secondary: { position: 'absolute', left: 10, right: 10, top: 318, height: 57, borderRadius: 29, backgroundColor: '#D8D8D8', alignItems: 'center', justifyContent: 'center', shadowColor: '#000000', shadowOpacity: 0.14, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  secondaryText: { fontFamily: type.familyBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#9A9A9F' },
});
