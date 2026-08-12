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
  const { data: personas, isLoading, isError, refetch } = usePersonas();
  const cached = useGuardianStore((s) => s.persona);
  const list = personas?.length ? personas : cached ? [cached] : [];

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
            <View style={styles.emergencyIcon}><EmergencyIcon width={27} height={25} /></View>
            <Text style={styles.emergencyText}>실종 신고</Text>
          </Pressable>
          <Pressable
            onPress={() => navigation.navigate('GuardianTabs', { screen: 'GuardianReg' })}
            accessibilityRole="button"
            accessibilityLabel="안심 사전 등록"
            style={({ pressed }) => [styles.register, pressed && styles.pressed]}
          >
            <View style={styles.registerIcon}><RegisterIcon width={26} height={26} /></View>
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
          {isError ? <Pressable style={styles.empty} onPress={() => refetch()}><Text style={styles.emptyTitle}>등록 정보를 불러오지 못했습니다</Text><Text style={styles.emptyBody}>눌러서 다시 시도해 주세요</Text></Pressable> : null}
          {!isLoading && !isError && list.length === 0 ? <Pressable style={styles.empty} onPress={() => navigation.navigate('GuardianTabs', { screen: 'GuardianReg' })}><Text style={styles.emptyTitle}>아직 등록된 가족이 없어요</Text><Text style={styles.emptyBody}>안심 사전 등록을 먼저 진행해 주세요</Text></Pressable> : null}
          {list.map((p) => (
            <Pressable
              key={p.id}
              onPress={() => navigation.navigate('PersonaDetail', { personaId: p.id })}
              style={({ pressed }) => [styles.personRow, pressed && styles.pressed]}
            >
              <View style={styles.personInfo}>
                <View style={styles.nameRow}><Text style={styles.personName}>{p.name} ({p.age}세)</Text><View style={styles.dementiaBadge}><Text style={styles.dementiaText}>치매 정도</Text></View></View>
                <Text style={styles.personMeta}>최근 업데이트 날짜: {p.created_at ? p.created_at.slice(0, 10) : ''}</Text>
              </View>
              <Text style={styles.chevron}>›</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.guideBody}>
          <View style={styles.guideRow}><Text style={styles.guideBullet}>•</Text><Text style={styles.guideText}>치매 어르신을 사전에 등록할 수 있습니다.</Text></View>
          <View style={styles.guideRow}><Text style={styles.guideBullet}>•</Text><Text style={styles.guideText}>정기적인 업데이트 알림에 답변해 주시면 실종시 동선 예측 정확도가 올라갑니다.</Text></View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  content: { paddingBottom: 36 },
  logoRow: { height: 87, paddingLeft: 30, paddingTop: 19, flexDirection: 'row', alignItems: 'flex-start' },
  modeLabel: { fontFamily: type.familyYeolumBold, fontSize: 16, lineHeight: 20, letterSpacing: 0.41, color: '#8E8E93', marginLeft: 12, marginTop: 0 },
  hero: { height: 135, flexDirection: 'row', alignItems: 'center', paddingLeft: 28, paddingRight: 26, gap: 19 },
  emergency: { position: 'relative', top: 3, width: 102, height: 106, borderRadius: 55, backgroundColor: '#F14444', alignItems: 'center', justifyContent: 'center', shadowColor: '#F14444', shadowOpacity: 0.63, shadowRadius: 2, elevation: 3 },
  emergencyIcon: { width: 47, height: 43, alignItems: 'center', justifyContent: 'center' },
  emergencyText: { fontFamily: type.familyBold, color: '#FFFFFF', fontSize: 15, marginTop: 1 },
  register: { position: 'relative', top: 3, width: 200, height: 106, borderRadius: 10, backgroundColor: '#90C67C', padding: 13, flexDirection: 'row', alignItems: 'flex-start', shadowColor: '#90C67C', shadowOpacity: 0.71, shadowRadius: 2, elevation: 3 },
  registerIcon: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center', marginRight: 7, marginTop: -8 },
  registerCopy: { flex: 1, paddingTop: 22 },
  registerTitle: { fontFamily: type.familyBold, color: '#FFFFFF', fontSize: 15, lineHeight: 18 },
  registerBody: { fontFamily: type.familyMedium, color: '#FFFFFF', fontSize: 10, lineHeight: 13, letterSpacing: 0.07, marginTop: 5 },
  sectionHead: { height: 64, justifyContent: 'flex-end', paddingHorizontal: 23, paddingBottom: 13 },
  sectionTitle: { fontFamily: type.familySemiBold, fontSize: 18, color: '#000000' },
  familyList: { minHeight: 158, marginHorizontal: 23, gap: 12 },
  empty: { height: 73, borderRadius: 10, backgroundColor: color.figmaField, alignItems: 'center', justifyContent: 'center' },
  emptyTitle: { fontFamily: type.familySemiBold, fontSize: 14, color: '#525253' },
  emptyBody: { fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: color.figmaGray, marginTop: 6 },
  personRow: { height: 73, borderRadius: 10, backgroundColor: color.figmaField, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center' },
  personInfo: { flex: 1 },
  nameRow: { flexDirection: 'row', alignItems: 'center' },
  personName: { fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#525253' },
  dementiaBadge: { height: 16, minWidth: 63, borderRadius: 20, backgroundColor: '#D9D9D9', alignItems: 'center', justifyContent: 'center', marginLeft: 10 },
  dementiaText: { fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253' },
  personMeta: { fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253', marginTop: 6 },
  chevron: { fontFamily: type.family, fontSize: 23, color: color.guardian },
  guideBody: { paddingHorizontal: 23, paddingTop: 35, gap: 1 },
  guideRow: { flexDirection: 'row', alignItems: 'flex-start' },
  guideBullet: { width: 14, fontFamily: type.family, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#525253' },
  guideText: { flex: 1, fontFamily: type.family, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#525253' },
  pressed: { opacity: 0.78 },
});
