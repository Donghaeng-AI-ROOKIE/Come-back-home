/**
 * 제보 전 경고 (와이어프레임 C-1).
 *
 * 제보 챗봇 앞에 한 단계를 두는 이유: 허위·장난 제보가 층2 판정을 받으면 LKP 가
 * 잘못된 곳으로 옮겨가고 예측 전체가 그쪽으로 끌려간다(신뢰도 p ≥ 0.8 + 위치·시각
 * 특정 시 새 LKP 확정). 되돌리는 비용이 크므로 진입 전에 한 번 멈춘다.
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

export default function TipWarnScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { caseId } = useRoute<RouteProp<RootStackParamList, 'TipWarn'>>().params;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          실종자 제보
        </Text>

        <View style={styles.warn} accessible accessibilityLabel="주의. 허위 또는 장난 제보는 실종자를 찾는 시간을 크게 잃게 합니다.">
          <Text style={styles.warnTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            잠깐 확인해 주세요
          </Text>
          <Text style={styles.warnBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            제보는 예상 위치를 실제로 옮깁니다. 확실하지 않은 정보는 수색 방향을 잘못된 곳으로
            돌려 골든타임을 잃게 합니다.
          </Text>
          <Text style={styles.warnBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            기억이 흐릿해도 괜찮습니다 — 확신하는 만큼만 알려 주시면 그 정도로 반영됩니다.
          </Text>
        </View>

        <View style={styles.tips}>
          <Text style={styles.tipsTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            이런 정보가 도움이 됩니다
          </Text>
          <Text style={styles.tipItem} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            · 어디에서 보셨는지 (건물 이름·출구 번호)
          </Text>
          <Text style={styles.tipItem} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            · 언제 보셨는지 (방금 전, 10분 전)
          </Text>
          <Text style={styles.tipItem} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            · 어느 방향으로 가셨는지
          </Text>
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <CTAButton
          label="제보 시작하기"
          onPress={() => navigation.replace('ReportChat', { caseId })}
          accent={color.search}
        />
        <View style={styles.gap} />
        <CTAButton label="취소" onPress={() => navigation.goBack()} variant="ghost" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  scroll: { padding: space.xl, gap: space.lg },
  title: { fontSize: type.size.title, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },

  warn: { backgroundColor: color.criticalWash, borderRadius: radius.lg, borderWidth: 1, borderColor: color.critical, padding: space.lg, gap: space.sm },
  warnTitle: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: color.criticalInk, fontFamily: type.family },
  warnBody: { fontSize: type.size.label, color: color.criticalInk, fontFamily: type.family, lineHeight: 23 },

  tips: { backgroundColor: color.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: color.border, padding: space.lg, gap: space.xs },
  tipsTitle: { fontSize: type.size.label, fontWeight: type.weight.black, color: color.text, fontFamily: type.family, marginBottom: space.xs },
  tipItem: { fontSize: type.size.label, color: color.textBody, fontFamily: type.family, lineHeight: 23 },

  footer: { padding: space.xl, borderTopWidth: 1, borderTopColor: color.border, backgroundColor: color.surface },
  gap: { height: space.sm },
});
