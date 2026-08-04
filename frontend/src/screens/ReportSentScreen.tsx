/**
 * 신고 전송 완료 + AI 예측 진행 (와이어프레임).
 *
 * 예측은 EXAONE 실호출 5회 + 몬테카를로 500명이라 **10초 안팎 걸린다.** 이 화면이
 * 진행 단계를 보여주는 이유가 그것이다 — 아무 표시 없이 기다리게 하면 멈춘 줄 안다.
 *
 * 실패해도 신고 자체는 접수돼 있다. 그래서 실패를 "신고 실패"로 보여주지 않고
 * 예측만 다시 시도할 수 있게 한다.
 */
import React, { useEffect } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
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
    { n: '3', label: '시민 제보 대기', state: predicting || failed ? 'todo' : 'active' },
  ];
  return (
    <View style={styles.steps}>
      {steps.map((s) => (
        <View key={s.n} style={styles.step}>
          <View
            style={[
              styles.stepCircle,
              s.state === 'done' && styles.stepDone,
              s.state === 'active' && styles.stepActive,
            ]}
          >
            <Text style={[styles.stepNum, s.state !== 'todo' && styles.stepNumOn]}>
              {s.state === 'done' ? '✓' : s.n}
            </Text>
          </View>
          <Text
            style={[styles.stepLabel, s.state !== 'todo' && styles.stepLabelOn]}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
          >
            {s.label}
          </Text>
        </View>
      ))}
    </View>
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
          <Text style={styles.heroTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            신고가 접수됐습니다
          </Text>
          <Text style={styles.heroSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            케이스 번호 {caseId}
          </Text>
        </View>

        <Steps predicting={predicting} failed={failed} />

        {predicting && (
          <View style={[styles.card, styles.cardInfo]}>
            <ActivityIndicator color={color.search} />
            <Text style={styles.cardBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              실종자의 습관과 지형을 함께 분석해 이동 경로를 계산하고 있습니다. 10초 정도 걸립니다.
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
            <CTAButton label="예측 다시 시도" onPress={() => predict.mutate()} accent={color.search} />
          </View>
        )}

        {predict.isSuccess && (
          <View style={[styles.card, styles.cardOk]}>
            <Text style={styles.okTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              예측이 완료됐습니다
            </Text>
            <Text style={styles.cardBody} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              예상 구역 안의 시민들에게 알림이 준비됩니다. 제보가 들어오면 예측이 갱신됩니다.
            </Text>
          </View>
        )}
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
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  scroll: { padding: space.xl, gap: space.lg, paddingBottom: space.xxl },
  hero: { alignItems: 'center', gap: space.xs, paddingVertical: space.xl },
  heroTitle: { fontSize: 24, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  heroSub: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family },

  steps: { flexDirection: 'row', justifyContent: 'space-between', gap: space.sm },
  step: { flex: 1, alignItems: 'center', gap: space.sm },
  stepCircle: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: color.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepDone: { backgroundColor: color.walk },
  stepActive: { backgroundColor: color.search },
  stepNum: { fontSize: type.size.caption, fontWeight: type.weight.black, color: color.textCaption },
  stepNumOn: { color: '#FFFFFF' },
  stepLabel: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family, textAlign: 'center' },
  stepLabelOn: { color: color.text, fontWeight: type.weight.bold },

  card: { borderRadius: radius.lg, padding: space.lg, gap: space.sm, alignItems: 'center' },
  cardInfo: { backgroundColor: color.searchWash },
  cardOk: { backgroundColor: color.walkWash },
  cardError: { backgroundColor: color.criticalWash, alignItems: 'stretch' },
  cardBody: { fontSize: type.size.label, color: color.textBody, fontFamily: type.family, lineHeight: 22, textAlign: 'center' },
  okTitle: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: color.walkInk, fontFamily: type.family },
  errTitle: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: color.criticalInk, fontFamily: type.family },
  errDetail: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family },
  gap: { height: space.xs },

  footer: { padding: space.xl, borderTopWidth: 1, borderTopColor: color.border, backgroundColor: color.surface },
});
