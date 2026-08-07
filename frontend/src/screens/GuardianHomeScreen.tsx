/**
 * 보호자 홈 — 피그마 [보호자] 메인 (2625:15791) 구현.
 *
 * 긴급 신고 버튼이 화면 위쪽에 있는 이유: 이 화면을 급하게 여는 사람은
 * 이미 실종 상황이다. 사전등록 안내를 위에 두면 그 순간에 읽히지 않는다.
 */
import React from 'react';
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
import { color, radius, space, type } from '../theme/tokens';
import { gColor } from '../theme/guardianTokens';
import {
  icBroadcastXml,
  icChevronXml,
  icProfileCardXml,
  logoXml,
} from '../assets/guardianSvg';
import { useGuardianStore } from '../store/guardianStore';
import { usePersonas } from '../hooks/queries';

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
  const list = personas?.length ? personas : cached ? [cached] : [];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <SvgXml xml={logoXml} width={77} height={42} />
          <Text style={styles.headerSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            보호자{'\n'}안심 모드
          </Text>
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
            onPress={() => navigation.navigate('RegChat')}
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
              onPress={() => navigation.navigate('PersonaDetail', { personaId: p.id })}
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
  scroll: { padding: space.xl, gap: space.md, paddingBottom: space.xxl },

  header: { flexDirection: 'row', alignItems: 'center', gap: space.md, marginBottom: space.sm },
  headerSub: {
    fontSize: type.size.body,
    lineHeight: 20,
    letterSpacing: 0.41,
    color: gColor.gray,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
  },

  hero: { flexDirection: 'row', alignItems: 'center', gap: space.lg, marginVertical: space.sm },
  sosCircle: {
    width: 104,
    height: 104,
    borderRadius: radius.pill,
    backgroundColor: gColor.alertRed,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
    shadowColor: gColor.alertRed,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.63,
    shadowRadius: 2,
    elevation: 4,
  },
  sosLabel: { fontSize: type.size.label, fontWeight: type.weight.bold, color: '#FFFFFF', fontFamily: type.family },
  regCard: {
    flex: 1,
    minHeight: 104,
    borderRadius: 10,
    backgroundColor: gColor.cardGreen,
    padding: space.lg,
    gap: space.xs,
    shadowColor: gColor.cardGreen,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.71,
    shadowRadius: 2,
    elevation: 4,
  },
  regTitle: { fontSize: type.size.label, fontWeight: type.weight.bold, color: 'rgba(255,255,255,0.92)', fontFamily: type.family },
  regBody: { fontSize: type.size.caption, fontWeight: type.weight.medium, color: 'rgba(255,255,255,0.92)', fontFamily: type.family, lineHeight: 17 },

  section: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.bold,
    color: color.text,
    fontFamily: type.family,
    marginTop: space.md,
  },
  rowBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: gColor.barBg,
    borderRadius: radius.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    gap: space.md,
  },
  rowInfo: { flex: 1, gap: space.xs },
  rowTop: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  rowName: { fontSize: 17, fontWeight: type.weight.bold, color: gColor.textMuted, letterSpacing: -0.41, fontFamily: type.family },
  chip: { backgroundColor: gColor.chip, borderRadius: radius.pill, paddingHorizontal: space.md, paddingVertical: 2 },
  chipText: { fontSize: type.size.caption, color: gColor.textMuted, fontFamily: type.family },
  rowDate: { fontSize: type.size.caption, color: gColor.textMuted, letterSpacing: 0.07, fontFamily: type.family },
  empty: { fontSize: type.size.label, color: color.textBody, fontFamily: type.family, lineHeight: 22 },

  guide: { marginTop: space.md, gap: space.xs },
  guideText: { fontSize: type.size.caption, color: gColor.textMuted, letterSpacing: -0.08, fontFamily: type.family, lineHeight: 18 },
  pressed: { opacity: 0.85 },
});
