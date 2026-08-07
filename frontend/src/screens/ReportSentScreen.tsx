/**
 * 신고 접수 완료 + AI 예측 진행 — 피그마 [보호자] 신고 접수 완료 (2609:15370) 구현.
 *
 * 예측은 EXAONE 실호출 5회 + 몬테카를로 500명이라 **10초 안팎 걸린다.** 이 화면이
 * 진행 단계를 보여주는 이유가 그것이다 — 아무 표시 없이 기다리게 하면 멈춘 줄 안다.
 *
 * 실패해도 신고 자체는 접수돼 있다. 그래서 실패를 "신고 실패"로 보여주지 않고
 * 예측만 다시 시도할 수 있게 한다.
 */
import React, { useEffect } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { SvgXml } from 'react-native-svg';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import { gColor } from '../theme/guardianTokens';
import { icBroadcastGreenXml, icCheckXml, logoXml } from '../assets/guardianSvg';
import CTAButton from '../components/CTAButton';
import { useRunPrediction } from '../hooks/queries';

type Step = { n: string; label: string; state: 'done' | 'active' | 'todo' };

function Steps({ predicting, failed }: { predicting: boolean; failed: boolean }) {
  const steps: Step[] = [
    { n: '1', label: '신고 접수', state: 'done' },
    {
      n: '2',
      label: 'AI 예상 경로 분석',
      state: predicting ? 'active' : failed ? 'todo' : 'done',
    },
    { n: '3', label: '시민 제보', state: predicting || failed ? 'todo' : 'active' },
  ];
  return (
    <View style={styles.steps}>
      <View style={styles.stepLine} />
      {steps.map((s) => (
        <View key={s.n} style={styles.step}>
          <View
            style={[
              styles.stepCircle,
              s.state === 'done' && styles.stepDone,
              s.state === 'active' && styles.stepActive,
            ]}
          >
            {s.state === 'active' ? (
              <ActivityIndicator size="small" color="#FFFFFF" />
            ) : (
              <Text style={styles.stepNum}>{s.state === 'done' ? '✓' : s.n}</Text>
            )}
          </View>
          <Text style={styles.stepLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {s.label}
          </Text>
        </View>
      ))}
    </View>
  );
}

/** 행동 지침 — 전용 화면 시안이 아직 없어 핵심만 알림으로 띄운다. */
function showGuideline() {
  Alert.alert(
    '치매 가족 실종시 행동 지침',
    [
      '1. 112에 실종 신고를 하세요. 치매 환자는 접수 즉시 수색이 시작됩니다.',
      '2. 최근 사진과 당시 옷차림을 경찰에 전달하세요.',
      '3. 평소 자주 가시던 곳(옛 집·시장·직장)을 먼저 확인하세요.',
      '4. 한 명은 집에 남으세요 — 스스로 돌아오시는 경우가 많습니다.',
    ].join('\n'),
  );
}

export default function ReportSentScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { caseId } = useRoute<RouteProp<RootStackParamList, 'ReportSent'>>().params;
  const predict = useRunPrediction(caseId);

  // 화면에 들어오는 즉시 예측 시작. mutate 참조는 안정적이므로 1회만 돈다.
  useEffect(() => {
    predict.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const predicting = predict.isPending;
  const failed = predict.isError;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.hero}>
          <SvgXml xml={logoXml} width={77} height={42} />
          <SvgXml xml={icBroadcastGreenXml} width={27} height={25} />
          <Text style={styles.heroTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            신고 접수 완료
          </Text>
          <Text style={styles.heroSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            케이스 번호 {caseId}
          </Text>
        </View>

        <Steps predicting={predicting} failed={failed} />

        {predicting && (
          <View style={styles.card}>
            <Text style={styles.cardTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              안내사항
            </Text>
            <Text style={styles.cardBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              현재 AI가 실종자의 습관과 지형을 분석하여 이동 경로를 파악하고 있습니다.
              인근 시민들의 제보가 확인되는 대로 안내해 드리겠습니다.
            </Text>
          </View>
        )}

        {failed && (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.errTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              예측을 완료하지 못했습니다
            </Text>
            {/* 신고는 이미 접수됐다는 사실을 반드시 함께 말한다 — 다시 신고하게 만들면 안 된다. */}
            <Text style={styles.cardBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              신고는 접수돼 있습니다. 예측만 다시 시도할 수 있습니다.
            </Text>
            <Text style={styles.errDetail} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {String(predict.error)}
            </Text>
            <View style={styles.gap} />
            <CTAButton label="예측 다시 시도" onPress={() => predict.mutate()} accent={gColor.progressGreen} />
          </View>
        )}

        {predict.isSuccess && (
          <View style={styles.card}>
            <Text style={styles.cardTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              예측이 완료됐습니다
            </Text>
            <Text style={styles.cardBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              예상 구역 안의 시민들에게 알림이 준비됩니다. 제보가 들어오면 예측이 갱신됩니다.
            </Text>
          </View>
        )}

        <Pressable
          onPress={showGuideline}
          accessibilityRole="button"
          accessibilityLabel="치매 가족 실종시 행동 지침 보기"
          style={({ pressed }) => [styles.guideBtn, pressed && styles.pressed]}
        >
          <SvgXml xml={icCheckXml} width={13} height={10} />
          <Text style={styles.guideLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            치매 가족 실종시 행동 지침
          </Text>
        </Pressable>
      </ScrollView>

      <View style={styles.footer}>
        <CTAButton
          label="홈으로 돌아가기"
          onPress={() => navigation.navigate('GuardianTabs', { screen: 'GuardianHome' })}
          variant="ghost"
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: gColor.mint },
  scroll: { padding: space.xl, gap: space.lg, paddingBottom: space.xxl },
  hero: { alignItems: 'center', gap: space.md, paddingVertical: space.xl },
  heroTitle: { fontSize: type.size.title, fontWeight: type.weight.medium, color: color.text, fontFamily: type.family, marginTop: space.sm },
  heroSub: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family },

  steps: { flexDirection: 'row', justifyContent: 'space-between', gap: space.sm },
  stepLine: {
    position: 'absolute',
    left: space.md,
    right: space.md,
    top: 20,
    borderTopWidth: 1,
    borderStyle: 'dashed',
    borderColor: gColor.progressGreen,
  },
  step: { flex: 1, alignItems: 'center', gap: space.sm },
  stepCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: gColor.gray,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepDone: { backgroundColor: gColor.progressGreen },
  stepActive: { backgroundColor: gColor.cardGreen },
  stepNum: { fontSize: type.size.title, fontWeight: type.weight.bold, color: '#FFFFFF' },
  stepLabel: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: gColor.progressGreen,
    fontFamily: type.family,
    textAlign: 'center',
  },

  card: { borderRadius: radius.lg, padding: space.lg, gap: space.sm, backgroundColor: gColor.surface },
  cardTitle: { fontSize: type.size.caption, fontWeight: type.weight.medium, color: gColor.progressGreen, fontFamily: type.family },
  cardError: { backgroundColor: color.criticalWash },
  cardBody: { fontSize: type.size.caption, color: gColor.textMuted, fontFamily: type.family, lineHeight: 20 },
  errTitle: { fontSize: type.size.cardTitle, fontWeight: type.weight.bold, color: color.criticalInk, fontFamily: type.family },
  errDetail: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family },
  gap: { height: space.xs },

  guideBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    alignSelf: 'center',
    minWidth: 255,
    minHeight: 44,
    borderRadius: radius.pill,
    backgroundColor: gColor.surface,
    shadowColor: '#000000',
    shadowOffset: { width: 1, height: 1 },
    shadowOpacity: 0.25,
    shadowRadius: 2,
    elevation: 2,
  },
  guideLabel: { fontSize: type.size.label, fontWeight: type.weight.medium, color: gColor.textMuted, fontFamily: type.family },
  pressed: { opacity: 0.85 },

  footer: { padding: space.xl, backgroundColor: gColor.mint },
});
