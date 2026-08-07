/**
 * 사전 등록 완료 — 피그마 [보호자] 사전등록 완료 (2609:15629) 구현.
 * 무엇이 저장됐는지 보호자가 확인하는 화면.
 */
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { SvgXml } from 'react-native-svg';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import { gColor } from '../theme/guardianTokens';
import {
  icBookmarkXml,
  icCheckCircleXml,
  icHomeSmallXml,
  logoXml,
} from '../assets/guardianSvg';
import { useGuardianStore } from '../store/guardianStore';

function Row({ k, v }: { k: string; v: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowKey} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        {k}
      </Text>
      <Text style={styles.rowVal} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        {v}
      </Text>
    </View>
  );
}

export default function RegDoneScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { name, age } = useRoute<RouteProp<RootStackParamList, 'RegDone'>>().params;
  // 방금 등록한 페르소나 캐시 — 관련 장소 요약에 쓴다.
  const persona = useGuardianStore((s) => s.persona);
  const places = (persona?.attraction_points ?? []).map((p) => p.label).slice(0, 3);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.hero}>
          <SvgXml xml={logoXml} width={77} height={42} />
          <SvgXml xml={icCheckCircleXml} width={25} height={25} />
          <Text style={styles.heroTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            사전 등록 완료
          </Text>
          <Text style={styles.heroSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            답변해주신 내용이 안전하게 저장되었습니다.
          </Text>
        </View>

        <View style={styles.sectionRow}>
          <SvgXml xml={icBookmarkXml} width={11} height={13} />
          <Text style={styles.sectionTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            요약 정보
          </Text>
        </View>
        <View style={styles.card}>
          <Row k="이름" v={name} />
          <Row k="연령" v={`${age}세`} />
          <Row k="건강 상태" v="치매" />
          <Row k="관련 장소" v={places.length ? places.join(', ') : '등록된 장소 없음'} />
        </View>

        <View style={styles.notice}>
          <Text style={styles.noticeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            등록 정보는 실종 상황의 예측에만 쓰이며, 사건이 종결되면 보관 기간에 따라 파기됩니다.
          </Text>
        </View>

        <Pressable
          onPress={() => navigation.navigate('GuardianTabs', { screen: 'GuardianHome' })}
          accessibilityRole="button"
          accessibilityLabel="홈으로 돌아가기"
          style={({ pressed }) => [styles.homeBtn, pressed && styles.pressed]}
        >
          <SvgXml xml={icHomeSmallXml} width={14} height={13} />
          <Text style={styles.homeLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            홈으로 돌아가기
          </Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: gColor.mint },
  scroll: { padding: space.xl, gap: space.md, paddingBottom: space.xxl },
  hero: { alignItems: 'center', gap: space.md, paddingVertical: space.xl },
  heroTitle: { fontSize: type.size.title, fontWeight: type.weight.medium, color: color.text, fontFamily: type.family, marginTop: space.xs },
  heroSub: { fontSize: type.size.label, fontWeight: type.weight.medium, color: gColor.textMuted, fontFamily: type.family, textAlign: 'center' },

  sectionRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingHorizontal: space.xs },
  sectionTitle: { fontSize: type.size.label, fontWeight: type.weight.medium, color: color.text, fontFamily: type.family },

  card: { backgroundColor: gColor.surface, borderRadius: radius.lg, padding: space.lg },
  row: { flexDirection: 'row', paddingVertical: space.sm, gap: space.lg },
  rowKey: { width: 90, fontSize: type.size.label, fontWeight: type.weight.medium, color: gColor.inkGreen, fontFamily: type.family },
  rowVal: { flex: 1, fontSize: type.size.label, fontWeight: type.weight.regular, color: gColor.textValue, fontFamily: type.family },

  notice: { backgroundColor: 'rgba(255,255,255,0.6)', borderRadius: radius.lg, padding: space.lg },
  noticeText: { fontSize: type.size.caption, color: gColor.inkGreen, fontFamily: type.family, lineHeight: 20 },

  homeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    alignSelf: 'center',
    minWidth: 255,
    minHeight: 44,
    marginTop: space.xl,
    borderRadius: radius.pill,
    backgroundColor: gColor.surface,
    shadowColor: '#000000',
    shadowOffset: { width: 1, height: 1 },
    shadowOpacity: 0.25,
    shadowRadius: 2,
    elevation: 2,
  },
  homeLabel: { fontSize: type.size.label, fontWeight: type.weight.medium, color: gColor.textMuted, fontFamily: type.family },
  pressed: { opacity: 0.85 },
});
