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
import AppearanceFigure from '../components/AppearanceFigure';
import FigmaStatusBar from '../components/FigmaStatusBar';
import { useActiveAlerts } from '../hooks/queries';
import { alertToView } from '../data/missingView';

type ClothingKey = 'top' | 'bottom' | 'shoes';

type AppearancePresentation = {
  clothing: Array<{ key: ClothingKey; value: string }>;
  extra: string[];
};

const APPEARANCE_FIELDS: Array<{
  key: ClothingKey;
  keywords: string[];
}> = [
  { key: 'top', keywords: ['상의', '셔츠', '점퍼', '재킷', '자켓', '코트', '티셔츠', '블라우스', '니트', '조끼'] },
  { key: 'bottom', keywords: ['하의', '바지', '청바지', '치마', '스커트', '슬랙스', '반바지'] },
  { key: 'shoes', keywords: ['신발', '운동화', '구두', '슬리퍼', '샌들', '부츠'] },
];

function getAppearancePresentation(
  appearance: string[],
  colors?: { top: string; bottom: string; shoes: string },
): AppearancePresentation {
  // 예전 응답은 인상착의 전체를 쉼표로 묶은 한 문장으로 보내기도 했다.
  const values = appearance
    .flatMap((value) => value.split(/[,，\n]+/))
    .map((value) => value.trim())
    .filter(Boolean);
  const used = new Set<number>();
  const resolved = new Map<ClothingKey, string>();

  APPEARANCE_FIELDS.forEach(({ key, keywords }) => {
    const index = values.findIndex((value, i) => !used.has(i) && keywords.some((keyword) => value.includes(keyword)));
    if (index >= 0) {
      used.add(index);
      resolved.set(key, values[index]);
    }
  });

  // 색상이 추출된 필드는 실제 입력된 옷 항목이다. 옷 종류가 명시되지 않은
  // "검정색" 같은 값은 서버의 원래 필드 순서(상의→하의→신발)에 맞춰 보완한다.
  APPEARANCE_FIELDS.forEach(({ key }) => {
    if (resolved.has(key) || !colors?.[key] || colors[key] === 'unknown') return;
    const index = values.findIndex((_, i) => !used.has(i));
    if (index >= 0) {
      used.add(index);
      resolved.set(key, values[index]);
    }
  });

  const clothing = APPEARANCE_FIELDS.flatMap(({ key }) => {
    const value = resolved.get(key);
    return value ? [{ key, value }] : [];
  });

  const remaining = values.filter((_, index) => !used.has(index));
  const height = remaining.filter((value) => /키|cm|센티/.test(value));
  const body = remaining.filter((value) => /체형/.test(value));
  const belongings = remaining.filter((value) => !/키|cm|센티|체형/.test(value));

  return { clothing, extra: [...height, ...body, ...belongings] };
}

export default function AppearanceScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { caseId } = useRoute<RouteProp<RootStackParamList, 'Appearance'>>().params;
  const { data: alerts } = useActiveAlerts();
  const alert = alerts?.find((item) => item.caseId === caseId);
  const view = alertToView(alert ?? {});
  const appearance = getAppearancePresentation(view.appearance, alert?.appearanceColors);
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <View style={styles.body}>
        <Text style={styles.title}>실종자 인상착의 사진</Text>
        <Text style={styles.subtitle}>신고 시 등록된 인상착의를 바탕으로 재구성한 이미지입니다</Text>
        <View style={styles.card}>
          {/* 사진은 받지 않는다(08-07 결정) — 자리표시 사진을 두면 남의 얼굴이
              실종자로 읽힌다. 보호자가 입력한 옷 색으로 실루엣을 그린다. */}
          <AppearanceFigure colors={alert?.appearanceColors} appearance={alert?.appearance} size={198} style={styles.photo} />
          <View style={styles.details}>
            <View style={styles.clothingChips}>
              {appearance.clothing.map(({ key, value }) => (
                <View key={key} style={styles.chip}><Text style={styles.chipText} numberOfLines={1}>{value}</Text></View>
              ))}
            </View>
            {appearance.extra.length ? <Text style={styles.extraText} numberOfLines={2}>{appearance.extra.join(' · ')}</Text> : null}
          </View>
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
  title: { position: 'absolute', left: 20, top: 27, fontFamily: type.familyCssExtraBold, fontSize: 18, lineHeight: 22, color: '#000000' },
  subtitle: { position: 'absolute', left: 20, top: 64, fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: color.figmaGray },
  card: { position: 'absolute', left: 23, right: 23, top: 107, height: 348, borderRadius: 10, backgroundColor: '#FFFFFF', alignItems: 'center', shadowColor: '#000000', shadowOpacity: 0.1, shadowRadius: 7, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  photo: { position: 'absolute', top: 31, width: 247, height: 198, borderRadius: 10, backgroundColor: '#F2F2F2' },
  details: { position: 'absolute', top: 247, left: 16, right: 16, alignItems: 'center' },
  clothingChips: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 8 },
  chip: { height: 22, borderRadius: 11, backgroundColor: '#FFC9CB', paddingHorizontal: 10, alignItems: 'center', justifyContent: 'center' },
  chipText: { fontFamily: type.familyCssBold, fontSize: 10, lineHeight: 13, letterSpacing: 0.07, color: color.figmaRed },
  extraText: { marginTop: 14, textAlign: 'center', fontFamily: type.familyCssSemiBold, fontSize: 14, lineHeight: 18, color: '#525253' },
  primary: { position: 'absolute', left: 10, right: 10, top: 491, height: 58, borderRadius: 30, backgroundColor: color.figmaRed, alignItems: 'center', justifyContent: 'center', shadowColor: '#000000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  primaryText: { fontFamily: type.familyCssBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#FFFFFF' },
  secondary: { position: 'absolute', left: 10, right: 10, top: 560, height: 58, borderRadius: 30, backgroundColor: '#D8D8D8', alignItems: 'center', justifyContent: 'center', shadowColor: '#000000', shadowOpacity: 0.14, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  secondaryText: { fontFamily: type.familyCssBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#9A9A9F' },
});
