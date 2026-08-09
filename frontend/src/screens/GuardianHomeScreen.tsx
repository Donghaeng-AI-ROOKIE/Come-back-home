/**
 * 보호자 홈 — 피그마 [보호자] 메인 (2625:15791) 구현.
 *
 * 긴급 신고 버튼이 화면 위쪽에 있는 이유: 이 화면을 급하게 여는 사람은
 * 이미 실종 상황이다. 사전등록 안내를 위에 두면 그 순간에 읽히지 않는다.
 */
import React, { useEffect } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { SvgXml } from 'react-native-svg';
import type { RootStackParamList } from '../navigation/types';
import { radius, type } from '../theme/tokens';
import { gColor, gFont } from '../theme/guardianTokens';
import {
  icBroadcastXml,
  icChevronXml,
  icProfileCardXml,
  guardianModeLabelXml,
} from '../assets/guardianSvg';
import { useGuardianStore } from '../store/guardianStore';
import { usePersonas } from '../hooks/queries';
import GuardianLogo from '../components/GuardianLogo';

/** ISO → "YYYY.MM.DD". 등록일이 없으면 빈 문자열. */
function fmtDate(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}.${mm}.${dd}`;
}

export default function GuardianHomeScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  // 서버가 진실이다. 스토어는 방금 등록한 것을 즉시 띄우기 위한 캐시일 뿐이라,
  // 앱을 다시 켜면 비어 있다 — 그때도 등록한 가족이 보여야 한다.
  const { data: personas, isLoading } = usePersonas();
  const cached = useGuardianStore((s) => s.persona);
  const setPersona = useGuardianStore((s) => s.setPersona);
  const list = personas?.length ? personas : cached ? [cached] : [];

  useEffect(() => {
    if (!cached && personas?.[0]) setPersona(personas[0]);
  }, [cached, personas, setPersona]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <GuardianLogo />
          <SvgXml xml={guardianModeLabelXml} width={54} height={39} />
        </View>

        <View style={styles.hero}>
          <Pressable
            onPress={() => navigation.navigate('Report')}
            accessibilityRole="button"
            accessibilityLabel="긴급 실종 신고"
            accessibilityHint="실종 신고를 접수하고 AI 예측을 시작합니다"
            style={({ pressed }) => [styles.sosCircle, pressed && styles.pressed]}
          >
            <SvgXml xml={icBroadcastXml} width={27} height={25} />
            <Text style={styles.sosLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              실종 신고
            </Text>
          </Pressable>

          <Pressable
            onPress={() => navigation.navigate('GuardianTabs', { screen: 'GuardianReg' })}
            accessibilityRole="button"
            accessibilityLabel="안심 사전 등록"
            style={({ pressed }) => [styles.regCard, pressed && styles.pressed]}
          >
            <SvgXml xml={icProfileCardXml} width={26} height={26} />
            <Text style={styles.regTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              안심 사전 등록
            </Text>
            <Text style={styles.regBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              미리 정보를 등록해두면 위급 시 골든타임을 지킬 수 있습니다.
            </Text>
          </Pressable>
        </View>

        <Text style={styles.section} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          사전 등록된 가족
        </Text>
        {isLoading && list.length === 0 ? (
          <View style={styles.rowBar}>
            <ActivityIndicator color={gColor.primary} />
          </View>
        ) : list.length === 0 ? (
          <View style={styles.rowBar}>
            <Text style={styles.empty} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              아직 등록된 가족이 없습니다. 사전 등록을 먼저 진행해 주세요.
            </Text>
          </View>
        ) : (
          list.map((p) => (
            <Pressable
              key={p.id}
              onPress={() => {
                setPersona(p);
                navigation.navigate('PersonaDetail', { personaId: p.id });
              }}
              accessibilityRole="button"
              accessibilityLabel={`${p.name} ${p.age}세 등록 정보 보기`}
              accessibilityHint="저장된 내용을 확인하고 수정할 수 있어요"
              style={({ pressed }) => [styles.rowBar, pressed && styles.pressed]}
            >
              <View style={styles.rowInfo}>
                <View style={styles.rowTop}>
                  <Text style={styles.rowName} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    {p.name} ({p.age}세)
                  </Text>
                  <View style={styles.chip}>
                    <Text style={styles.chipText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      치매
                    </Text>
                  </View>
                </View>
                <Text style={styles.rowDate} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  최근 업데이트 날짜: {fmtDate(p.created_at)}
                </Text>
              </View>
              <SvgXml xml={icChevronXml} width={7} height={12} />
            </Pressable>
          ))
        )}

        <View style={styles.guide}>
          <Text style={styles.guideText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {'•'}  치매 어르신을 사전에 등록할 수 있습니다.
          </Text>
          <Text style={styles.guideText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {'•'}  정기적인 업데이트 알림에 답변해 주시면 실종시 동선 예측 정확도가
            올라갑니다.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: gColor.surface },
  scroll: { paddingHorizontal: 24, paddingTop: 16, gap: 12, paddingBottom: 30 },

  header: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 8 },

  hero: { flexDirection: 'row', alignItems: 'center', gap: 16, marginVertical: 8 },
  sosCircle: {
    width: 104,
    height: 104,
    borderRadius: radius.pill,
    backgroundColor: gColor.alertRed,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    shadowColor: gColor.alertRed,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.63,
    shadowRadius: 2,
    elevation: 4,
  },
  sosLabel: { fontSize: 14, color: '#FFFFFF', fontFamily: gFont.semiBold },
  regCard: {
    flex: 1,
    minHeight: 104,
    borderRadius: 10,
    backgroundColor: gColor.cardGreen,
    padding: 16,
    gap: 4,
    shadowColor: gColor.cardGreen,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.71,
    shadowRadius: 2,
    elevation: 4,
  },
  regTitle: { fontSize: 14, color: 'rgba(255,255,255,0.92)', fontFamily: gFont.semiBold },
  regBody: { fontSize: 11, color: 'rgba(255,255,255,0.92)', fontFamily: gFont.medium, lineHeight: 15 },

  section: {
    fontSize: 16,
    color: '#000000',
    fontFamily: gFont.semiBold,
    marginTop: 12,
  },
  rowBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: gColor.barBg,
    borderRadius: radius.md,
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 12,
  },
  rowInfo: { flex: 1, gap: 4 },
  rowTop: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  rowName: { fontSize: 17, color: gColor.textMuted, letterSpacing: -0.41, fontFamily: gFont.semiBold },
  chip: { backgroundColor: gColor.chip, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 2 },
  chipText: { fontSize: 11, color: gColor.textMuted, fontFamily: gFont.regular },
  rowDate: { fontSize: 11, color: gColor.textMuted, letterSpacing: 0.07, fontFamily: gFont.regular },
  empty: { fontSize: 13, color: gColor.textMuted, fontFamily: gFont.regular, lineHeight: 19 },

  guide: { marginTop: 12, gap: 4 },
  guideText: { fontSize: 11, color: gColor.textMuted, letterSpacing: -0.08, fontFamily: gFont.regular, lineHeight: 18 },
  pressed: { opacity: 0.85 },
});
