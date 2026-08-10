import React from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import { useGuardianStore } from '../store/guardianStore';
import { usePersonas } from '../hooks/queries';
import FigmaLogo from '../components/FigmaLogo';
import EmergencyIcon from '../../assets/figma/guardian-emergency.svg';
import RegisterIcon from '../../assets/figma/guardian-register.svg';
import FigmaStatusBar from '../components/FigmaStatusBar';

export default function GuardianHomeScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data: personas, isLoading } = usePersonas();
  const cached = useGuardianStore((s) => s.persona);
  const figmaFallback = [
    { id: 'figma-1', name: '성함', age: 0, created_at: '' },
    { id: 'figma-2', name: '성함', age: 0, created_at: '' },
  ];
  const loaded = personas?.length ? personas : cached ? [cached] : [];
  const list = loaded.length >= 2 ? loaded : [...loaded, ...figmaFallback.slice(0, 2 - loaded.length)];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.logoRow}>
          <FigmaLogo mode="guardian" />
          <Text style={styles.modeLabel}>보호자{`\n`}안심 모드</Text>
        </View>

        <View style={styles.hero}>
          <Pressable
            onPress={() => navigation.navigate('Report')}
            accessibilityRole="button"
            accessibilityLabel="긴급 실종 신고"
            style={({ pressed }) => [styles.emergency, pressed && styles.pressed]}
          >
            <EmergencyIcon width={47} height={43} />
            <Text style={styles.emergencyText}>실종 신고</Text>
          </Pressable>
          <Pressable
            onPress={() => navigation.navigate('GuardianTabs', { screen: 'GuardianReg' })}
            accessibilityRole="button"
            accessibilityLabel="안심 사전 등록"
            style={({ pressed }) => [styles.register, pressed && styles.pressed]}
          >
            <View style={styles.registerIcon}><RegisterIcon width={36} height={36} /></View>
            <View style={styles.registerCopy}>
              <Text style={styles.registerTitle}>안심 사전 등록</Text>
              <Text style={styles.registerBody}>미리 정보를 등록해두면 위급 시 골든타임을{`\n`}지킬 수 있습니다.</Text>
            </View>
          </Pressable>
        </View>

        <View style={styles.sectionHead}>
          <Text style={styles.sectionTitle}>사전 등록된 가족</Text>
        </View>
        <View style={styles.familyList}>
          {isLoading && list.length === 0 ? <ActivityIndicator color={color.guardian} /> : null}
          {list.map((p) => (
            <Pressable
              key={p.id}
              onPress={() => p.id.startsWith('figma-') ? navigation.navigate('GuardianTabs', { screen: 'GuardianReg' }) : navigation.navigate('PersonaDetail', { personaId: p.id })}
              style={({ pressed }) => [styles.personRow, pressed && styles.pressed]}
            >
              <View style={styles.personInfo}>
                <View style={styles.nameRow}><Text style={styles.personName}>{p.name} ({p.age || '나이'})</Text><View style={styles.dementiaBadge}><Text style={styles.dementiaText}>치매 정도</Text></View></View>
                <Text style={styles.personMeta}>최근 업데이트 날짜: {p.created_at ? p.created_at.slice(0, 10) : ''}</Text>
              </View>
              <Text style={styles.chevron}>›</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.guideBody}>
          <Text style={styles.guideText}>•  치매 어르신을 사전에 등록할 수 있습니다.</Text>
          <Text style={styles.guideText}>•  정기적인 업데이트 알림에 답변해 주시면 실종시 동선 예측 정확도가 올라갑니다.</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  content: { paddingBottom: 36 },
  logoRow: { height: 87, paddingLeft: 30, paddingTop: 19, flexDirection: 'row', alignItems: 'flex-start' },
  modeLabel: { fontFamily: type.familyBold, fontSize: 16, lineHeight: 20, color: color.figmaGray, marginLeft: 12, marginTop: 0 },
  hero: { height: 135, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 26, gap: 19 },
  emergency: { width: 104, height: 106, borderRadius: 55, backgroundColor: color.figmaRed, alignItems: 'center', justifyContent: 'center' },
  emergencyText: { fontFamily: type.familyBold, color: '#FFFFFF', fontSize: 15, marginTop: 1 },
  register: { width: 200, height: 106, borderRadius: 10, backgroundColor: color.guardian, padding: 13, flexDirection: 'row', alignItems: 'flex-start' },
  registerIcon: { width: 36, height: 36, tintColor: '#FFFFFF', marginRight: 7 },
  registerCopy: { flex: 1, paddingTop: 22 },
  registerTitle: { fontFamily: type.familyBold, color: '#FFFFFF', fontSize: 15, lineHeight: 18 },
  registerBody: { fontFamily: type.familyMedium, color: '#FFFFFF', fontSize: 10, lineHeight: 13, marginTop: 5 },
  sectionHead: { height: 64, justifyContent: 'flex-end', paddingHorizontal: 23, paddingBottom: 16 },
  sectionTitle: { fontFamily: type.familySemiBold, fontSize: 18, color: '#000000' },
  familyList: { minHeight: 158, marginHorizontal: 23, gap: 12 },
  empty: { height: 73, borderRadius: 10, backgroundColor: color.figmaField, alignItems: 'center', justifyContent: 'center' },
  emptyTitle: { fontFamily: type.familySemiBold, fontSize: 14, color: '#525253' },
  emptyBody: { fontFamily: type.family, fontSize: 11, color: color.figmaGray, marginTop: 6 },
  personRow: { height: 73, borderRadius: 10, backgroundColor: color.figmaField, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center' },
  personInfo: { flex: 1 },
  nameRow: { flexDirection: 'row', alignItems: 'center' },
  personName: { fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, color: '#525253' },
  dementiaBadge: { height: 16, minWidth: 63, borderRadius: 20, backgroundColor: '#D9D9D9', alignItems: 'center', justifyContent: 'center', marginLeft: 10 },
  dementiaText: { fontFamily: type.family, fontSize: 11, color: '#525253' },
  personMeta: { fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#525253', marginTop: 6 },
  chevron: { fontFamily: type.family, fontSize: 23, color: color.guardian },
  guideBody: { paddingHorizontal: 23, paddingTop: 32, gap: 1 },
  guideText: { fontFamily: type.family, fontSize: 13, lineHeight: 18, color: '#525253' },
  pressed: { opacity: 0.78 },
});
