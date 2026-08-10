import React, { useEffect } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import { useRunPrediction } from '../hooks/queries';
import { useGuardianCaseStore } from '../store/guardianCaseStore';
import FigmaLogo from '../components/FigmaLogo';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import FigmaStatusBar from '../components/FigmaStatusBar';

export default function ReportSentScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { caseId } = useRoute<RouteProp<RootStackParamList, 'ReportSent'>>().params;
  const predict = useRunPrediction(caseId);
  const addCase = useGuardianCaseStore((s) => s.addCase);
  // 신고의 유일한 착지점 — 여기서 기기에 사건 id 를 적어 둬야 알림 탭이 이 사건의
  // 제보를 따라갈 수 있다(서버에 보호자-사건 바인딩이 없다).
  useEffect(() => { addCase(caseId); predict.mutate(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [caseId]);
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <View style={styles.body}>
        <FigmaLogo mode="guardian" />
        <Text style={styles.signal}>⌁</Text>
        <Text style={styles.title}>신고 접수 완료</Text>
        <View style={styles.steps}>
          <Step n="1" label="신고 접수" state="done" />
          <View style={styles.line} />
          <Step n="2" label="AI 예상 경로 분석" state={predict.isPending ? 'active' : 'done'} loading={predict.isPending} />
          <View style={styles.line} />
          <Step n="3" label="시민 제보" state={predict.isSuccess ? 'active' : 'todo'} />
        </View>
        <View style={styles.notice}>
          <Text style={styles.noticeTitle}>안내사항</Text>
          <Text style={styles.noticeText}>{predict.isError ? '신고는 접수됐습니다. AI 분석만 다시 시도해 주세요.' : '현재 AI가 실종자의 습관과 지형을 분석하여 이동 경로를 파악하고 있습니다. 인근 시민들의 제보가 확인되는 대로 안내해 드리겠습니다.'}</Text>
        </View>
        {predict.isError ? <Pressable style={styles.retry} onPress={() => predict.mutate()}><Text style={styles.retryText}>AI 분석 다시 시도</Text></Pressable> : null}
        <Pressable style={styles.guide} onPress={() => navigation.navigate('GuardianTabs', { screen: 'GuardianHome' })}>
          <Text style={styles.guideText}>✓ 치매 가족 실종시 행동 지침</Text>
        </Pressable>
      </View>
      <FigmaFlowTabBar mode="guardian" active="home" />
    </SafeAreaView>
  );
}

function Step({ n, label, state, loading }: { n: string; label: string; state: 'done' | 'active' | 'todo'; loading?: boolean }) {
  const bg = state === 'done' ? '#62B270' : state === 'active' ? '#A7D88E' : color.figmaGray;
  return <View style={styles.step}><View style={[styles.circle, { backgroundColor: bg }]}>{loading ? <ActivityIndicator size="small" color="#FFFFFF" /> : <Text style={styles.n}>{n}</Text>}</View><Text style={[styles.stepLabel, state !== 'todo' && styles.stepOn]}>{label}</Text></View>;
}
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.guardianWash }, body: { flex: 1, alignItems: 'center', paddingTop: 84 },
  signal: { fontFamily: type.family, fontSize: 31, lineHeight: 34, color: color.brand, marginTop: 8 },
  title: { fontFamily: type.familySemiBold, fontSize: 20, color: '#000000', marginTop: 7 },
  steps: { width: 292, flexDirection: 'row', alignItems: 'center', marginTop: 55 },
  step: { width: 76, alignItems: 'center' }, line: { flex: 1, height: 1, borderTopWidth: 1, borderStyle: 'dashed', borderColor: color.brand, marginTop: -18 },
  circle: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  n: { fontFamily: type.familyBold, fontSize: 17, color: '#FFFFFF' }, stepLabel: { fontFamily: type.family, fontSize: 11, color: color.figmaGray, marginTop: 6, textAlign: 'center' }, stepOn: { color: color.brand },
  notice: { width: 330, minHeight: 69, backgroundColor: '#FFFFFF', borderRadius: 10, marginTop: 61, padding: 14 },
  noticeTitle: { fontFamily: type.familySemiBold, fontSize: 11, color: color.brand }, noticeText: { fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#525253', marginTop: 4 },
  retry: { marginTop: 12, backgroundColor: color.figmaRed, borderRadius: 20, paddingHorizontal: 20, paddingVertical: 10 }, retryText: { fontFamily: type.familySemiBold, fontSize: 12, color: '#FFFFFF' },
  guide: { position: 'absolute', bottom: 157, width: 255, height: 38, borderRadius: 22, backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 2, shadowOffset: { width: 0, height: 1 } },
  guideText: { fontFamily: type.family, fontSize: 13, color: '#525253' },
});
