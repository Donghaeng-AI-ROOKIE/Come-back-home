/**
 * 상세 인상착의 (와이어프레임 B-3).
 *
 * 와이어프레임에는 "AI 3D 생성 아바타"가 있으나 **생성하지 않는다.** 실종자의
 * 얼굴을 AI가 지어내면 시민이 그 이미지를 기준으로 사람을 찾게 되고, 닮은 타인을
 * 오인 신고할 위험이 생긴다. 보호자가 올린 실제 사진과 텍스트 인상착의만 쓴다.
 */
import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import CTAButton from '../components/CTAButton';
import { MISSING } from '../data/missing';

export default function AppearanceScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { caseId } = useRoute<RouteProp<RootStackParamList, 'Appearance'>>().params;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          상세 인상착의
        </Text>

        <View style={styles.card}>
          <View style={styles.photo}>
            <Text style={styles.photoText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              보호자 제공 사진
            </Text>
          </View>

          <View style={styles.chips}>
            {MISSING.appearance.map((a) => (
              <View key={a} style={styles.chip}>
                <Text style={styles.chipText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  {a}
                </Text>
              </View>
            ))}
          </View>

          <Text style={styles.summary} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {MISSING.age}세 · {MISSING.cognition}
          </Text>
        </View>

        <View style={styles.notice}>
          <Text style={styles.noticeText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            인상착의는 보호자가 제공한 정보입니다. 비슷한 분을 보셨더라도 직접 확인하거나
            따라가지 마시고, 제보만 남겨 주세요.
          </Text>
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <CTAButton
          label="비슷한 사람을 봤어요"
          onPress={() => navigation.navigate('TipWarn', { caseId })}
          accent={color.search}
        />
        <View style={styles.gap} />
        <CTAButton label="뒤로" onPress={() => navigation.goBack()} variant="ghost" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  scroll: { padding: space.xl, gap: space.lg },
  title: { fontSize: type.size.title, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },

  card: { backgroundColor: color.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: color.border, padding: space.xl, gap: space.lg, alignItems: 'center' },
  photo: {
    width: 150,
    height: 190,
    borderRadius: radius.md,
    backgroundColor: color.surfaceAlt,
    borderWidth: 1,
    borderColor: color.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  photoText: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family },

  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, justifyContent: 'center' },
  chip: { backgroundColor: color.searchWash, borderRadius: radius.pill, paddingHorizontal: space.md, paddingVertical: space.xs },
  chipText: { fontSize: type.size.caption, fontWeight: type.weight.bold, color: color.searchInk, fontFamily: type.family },
  summary: { fontSize: type.size.label, fontWeight: type.weight.bold, color: color.text, fontFamily: type.family },

  notice: { backgroundColor: color.criticalWash, borderRadius: radius.lg, padding: space.lg },
  noticeText: { fontSize: type.size.caption, color: color.criticalInk, fontFamily: type.family, lineHeight: 20 },

  footer: { padding: space.xl, borderTopWidth: 1, borderTopColor: color.border, backgroundColor: color.surface },
  gap: { height: space.sm },
});
