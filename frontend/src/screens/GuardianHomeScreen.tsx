import React from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import { useGuardianStore } from '../store/guardianStore';
import { useGuardianCases, usePersonaStatus, usePersonas } from '../hooks/queries';
import FigmaLogo from '../components/FigmaLogo';
import EmergencyIcon from '../../assets/figma/guardian-emergency.svg';
import RegisterIcon from '../../assets/figma/guardian-register.svg';
import FigmaStatusBar from '../components/FigmaStatusBar';

export default function GuardianHomeScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data: personas, isLoading, isError, refetch } = usePersonas();
  const cached = useGuardianStore((s) => s.persona);
  const list = personas?.length ? personas : cached ? [cached] : [];

  /**
   * 빠른 등록으로 신고한 보호자에게 "안심 사전 등록" 자리를 **보완챗**으로 내준다.
   *
   * 이 자리에 원래 카드를 그대로 두면 안 되는 이유: 그 버튼은 12문항 온보딩으로
   * 가는데, 이 보호자는 이미 등록을 했다(Tier1 만). 눌러 봐야 **같은 어르신이 두
   * 번 등록될 뿐** 비어 있는 Tier2·3 은 그대로 남는다.
   *
   * 조건이 둘인 이유 — `partial` 은 "Tier1 만 찼다", 진행 중 사건은 "지금 찾고
   * 있다"를 뜻한다. 둘이 겹칠 때가 보완챗의 값이 가장 큰 순간이다. 답을 채우면
   * 서버가 그 사건을 곧바로 다시 예측해(persona_events) 수색 반경·속도가 인구
   * 평균에서 이 어르신의 값으로 바뀐다. 사건이 없으면 급할 게 없으므로 평소의
   * 등록 카드를 그대로 둔다.
   */
  const { data: status } = usePersonaStatus();
  const { data: cases } = useGuardianCases();
  const needsSupplement = status?.persona_status === 'partial' && (cases?.length ?? 0) > 0;

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
            onPress={() => needsSupplement
              ? navigation.navigate('RegChat', { mode: 'supplement' })
              : navigation.navigate('GuardianTabs', { screen: 'GuardianReg' })}
            accessibilityRole="button"
            accessibilityLabel={needsSupplement ? '추가 질문에 답하기' : '안심 사전 등록'}
            style={({ pressed }) => [styles.register, needsSupplement && styles.registerUrgent, pressed && styles.pressed]}
          >
            <View style={styles.registerIcon}><RegisterIcon width={26} height={26} /></View>
            <View style={styles.registerCopy}>
              {needsSupplement ? (
                <>
                  <Text style={styles.registerTitle}>추가 질문에 답해 주세요</Text>
                  <Text style={styles.registerBody}>7가지만 더 알려주시면 수색 범위를{`\n`}더 좁힐 수 있습니다.</Text>
                </>
              ) : (
                <>
                  <Text style={styles.registerTitle}>안심 사전 등록</Text>
                  <Text style={styles.registerBody}>미리 정보를 등록해두면 위급 시 골든타임을{`\n`}지킬 수 있습니다.</Text>
                </>
              )}
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
                <View style={styles.nameRow}><Text style={styles.personName}>{p.name} ({p.age}세)</Text></View>
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

/** 보완챗 카드 테두리 두께 — 안쪽 패딩 보정에 같은 값을 써야 해서 상수로 뺀다. */
const URGENT_BORDER = 2;

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  content: { paddingBottom: 36 },
  logoRow: { height: 87, paddingLeft: 30, paddingTop: 19, flexDirection: 'row', alignItems: 'flex-start' },
  modeLabel: { fontFamily: type.familyYeolumBold, fontSize: 16, lineHeight: 20, letterSpacing: 0.41, color: '#8E8E93', marginLeft: 12, marginTop: 0 },
  hero: { height: 135, flexDirection: 'row', alignItems: 'center', paddingLeft: 28, paddingRight: 26, gap: 19 },
  emergency: { position: 'relative', top: 3, width: 102, height: 106, borderRadius: 55, backgroundColor: '#F14444', alignItems: 'center', justifyContent: 'center', shadowColor: '#F14444', shadowOpacity: 0.63, shadowRadius: 2, elevation: 3 },
  emergencyIcon: { width: 47, height: 43, alignItems: 'center', justifyContent: 'center' },
  emergencyText: { fontFamily: type.familyBold, color: '#FFFFFF', fontSize: 15, marginTop: 1 },
  register: { position: 'relative', top: 3, width: 200, height: 106, borderRadius: 10, backgroundColor: '#90C67C', paddingLeft: 14, paddingTop: 10, alignItems: 'flex-start', shadowColor: '#90C67C', shadowOpacity: 0.71, shadowRadius: 2, elevation: 3 },
  // 보완챗 상태 전용 — **이 스타일이 붙을 때만** 테두리가 생긴다. 평소의
  // `register` 카드는 테두리 없이 그대로 둔다(시안 원본).
  //
  // 바꾸는 것은 테두리뿐이다. 초록 채움은 온보딩 카드와 같은 값을 그대로 쓴다 —
  // 같은 자리의 같은 카드라는 것이 보여야 하고, 배경까지 손대면 옆의 실종 신고
  // 버튼과 위계가 엉킨다.
  //
  // 고정 크기(200×106) 카드라 테두리가 바깥으로 번지지 않고 안쪽으로 들어온다.
  // 글자가 2px 밀리는데, 그만큼 paddingLeft·paddingTop 에서 빼 시안 위치를 지킨다.
  registerUrgent: {
    borderWidth: URGENT_BORDER,
    borderColor: color.critical,
    paddingLeft: 14 - URGENT_BORDER,
    paddingTop: 10 - URGENT_BORDER,
  },
  registerIcon: { width: 26, height: 26, alignItems: 'center', justifyContent: 'center' },
  registerCopy: { paddingTop: 5 },
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
  personMeta: { fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253', marginTop: 6 },
  chevron: { fontFamily: type.family, fontSize: 23, color: color.guardian },
  guideBody: { paddingHorizontal: 23, paddingTop: 35, gap: 1 },
  guideRow: { flexDirection: 'row', alignItems: 'flex-start' },
  guideBullet: { width: 14, fontFamily: type.family, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#525253' },
  guideText: { flex: 1, fontFamily: type.family, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#525253' },
  pressed: { opacity: 0.78 },
});
