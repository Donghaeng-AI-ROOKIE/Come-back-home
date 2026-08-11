import React, { useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useQueryClient } from '@tanstack/react-query';
import { color, type } from '../theme/tokens';
import { submitTip } from '../api/client';
import { useAuthStore } from '../store/authStore';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import FigmaStatusBar from '../components/FigmaStatusBar';

type Step = 'summary' | 'location' | 'time';

export default function ReportChatScreen() {
  const userId = useAuthStore((s) => s.userId);
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const queryClient = useQueryClient();
  const { caseId } = useRoute<RouteProp<RootStackParamList, 'ReportChat'>>().params;
  const [step, setStep] = useState<Step>('summary');
  const [summary, setSummary] = useState('');
  const [location, setLocation] = useState('');
  const [seenAt, setSeenAt] = useState('');
  const [sending, setSending] = useState(false);

  const submit = async ({ withoutLocation = false, withoutTime = false } = {}) => {
    if (sending) return;
    setSending(true);
    try {
      const includeLocation = !withoutLocation && !!location.trim();
      const includeTime = !withoutTime && !!seenAt.trim();
      const result = await submitTip(caseId, {
        // 자유서술 위치·시각은 서버의 제보 구조화/지오코딩 파이프라인이 좌표와
        // datetime 으로 바꾼다. 데모 좌표나 파싱 불가능한 문자열을 명시 필드에
        // 넣지 않는다.
        text: [
          summary.trim(),
          includeLocation && `목격 위치: ${location.trim()}`,
          includeTime && `목격 시각: ${seenAt.trim()}`,
        ].filter(Boolean).join(' / ') || '목격 제보',
      }, { force: withoutLocation || withoutTime, reporterUserId: userId ?? undefined });
      if ('status' in result) {
        setStep(result.missing.includes('location') ? 'location' : 'time');
        Alert.alert('추가 확인이 필요해요', result.reason || '목격 위치나 시각을 조금 더 알려주세요.');
        setSending(false);
        return;
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['guardianCases'] }),
        queryClient.invalidateQueries({ queryKey: ['activeAlerts'] }),
        queryClient.invalidateQueries({ queryKey: ['case', caseId] }),
      ]);
      navigation.replace('ReportDone', {
        caseId,
        beforeAreaKm2: result.beforeAreaKm2,
        afterAreaKm2: result.afterAreaKm2,
        deltaPct: result.deltaPct,
      });
    } catch (e) {
      Alert.alert('제보를 전송하지 못했습니다', String(e));
      setSending(false);
    }
  };

  const nextFromSummary = () => {
    if (!summary.trim()) {
      Alert.alert('제보 내용을 입력해 주세요');
      return;
    }
    setStep('location');
  };

  const nextFromLocation = () => {
    if (!location.trim()) {
      Alert.alert('목격 위치를 입력해 주세요');
      return;
    }
    setStep('time');
  };

  const long = step === 'time';
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          style={styles.flex}
          contentContainerStyle={[styles.scrollContent, long && styles.scrollContentLong]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.body}>
            <Text style={styles.title}>실종자 제보</Text>
            <Text style={styles.desc}>목격하신 내용을 편하게 적어주세요.{`\n`}위치와 시각, 인상착의, 어느 쪽으로 가셨는지를 알려주시면 큰 도움이 됩니다.</Text>

            {step === 'summary' ? (
              <>
                <TextInput
                  value={summary}
                  onChangeText={setSummary}
                  multiline
                  style={styles.initialInput}
                  textAlignVertical="top"
                  accessibilityLabel="목격 내용"
                />
                <Pressable style={styles.initialButton} onPress={nextFromSummary}>
                  <Text style={styles.primaryText}>제보하기</Text>
                </Pressable>
              </>
            ) : (
              <>
                <Text style={styles.summaryLabel}>방금 남기신 내용</Text>
                <TextInput
                  value={summary}
                  onChangeText={setSummary}
                  multiline
                  style={styles.summaryInput}
                  textAlignVertical="top"
                  accessibilityLabel="방금 남긴 제보 내용"
                />

                <Text style={styles.locationLabel}>추가 확인이 필요해요</Text>
                <Text style={styles.question}>정확히 목격하신 위치가 어디인가요?</Text>
                <TextInput
                  value={location}
                  onChangeText={setLocation}
                  multiline
                  style={styles.locationInput}
                  textAlignVertical="top"
                  accessibilityLabel="목격 위치"
                />

                {step === 'time' ? (
                  <>
                    <View style={styles.confirmChip}><Text style={styles.confirmChipText}>✓ 위치 확인</Text></View>
                    <Text style={styles.timeLabel}>추가 확인이 필요해요</Text>
                    <Text style={styles.question}>정확히 몇 시쯤 보셨나요?</Text>
                    <TextInput
                      value={seenAt}
                      onChangeText={setSeenAt}
                      multiline
                      style={styles.timeInput}
                      textAlignVertical="top"
                      accessibilityLabel="목격 시각"
                    />
                    <Pressable style={[styles.primary, styles.timePrimary]} onPress={() => submit()}>
                      <Text style={styles.primaryText}>{sending ? '전송 중…' : '답변하고 제보하기'}</Text>
                    </Pressable>
                    <Pressable style={styles.secondary} onPress={() => submit({ withoutTime: true })}>
                      <Text style={styles.secondaryText}>시각 없이 그대로 제보하기</Text>
                    </Pressable>
                  </>
                ) : (
                  <>
                    <Pressable style={styles.primary} onPress={nextFromLocation}>
                      <Text style={styles.primaryText}>답변하고 제보하기</Text>
                    </Pressable>
                    <Pressable style={styles.secondary} onPress={() => submit({ withoutLocation: true })}>
                      <Text style={styles.secondaryText}>{sending ? '전송 중…' : '위치 없이 그대로 제보하기'}</Text>
                    </Pressable>
                  </>
                )}
              </>
            )}
          </View>
          <FigmaFlowTabBar mode="citizen" active="alert" />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  flex: { flex: 1 },
  scrollContent: { minHeight: 768 },
  scrollContentLong: { minHeight: 905 },
  body: { flex: 1, paddingHorizontal: 23, paddingTop: 27 },
  title: { fontFamily: type.familyExtraBold, fontSize: 18, lineHeight: 23, color: '#000000', marginLeft: -3 },
  desc: { fontFamily: type.family, fontSize: 11, lineHeight: 14, color: '#525253', marginLeft: -3, marginTop: 16 },
  initialInput: { height: 112, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, marginTop: 26, fontFamily: type.family, fontSize: 12, color: '#525253' },
  initialButton: { height: 57, borderRadius: 27, backgroundColor: color.figmaRed, alignItems: 'center', justifyContent: 'center', marginTop: 18 },
  summaryLabel: { fontFamily: type.familySemiBold, fontSize: 13, lineHeight: 18, color: '#525253', marginTop: 21 },
  summaryInput: { height: 74, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, marginTop: 4, fontFamily: type.family, fontSize: 12, color: '#525253' },
  locationLabel: { fontFamily: type.familySemiBold, fontSize: 13, lineHeight: 18, color: '#525253', marginTop: 31 },
  timeLabel: { fontFamily: type.familySemiBold, fontSize: 13, lineHeight: 18, color: '#525253', marginTop: 25 },
  question: { fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#525253', marginTop: 12 },
  locationInput: { height: 112, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, marginTop: 12, fontFamily: type.family, fontSize: 12, color: '#525253' },
  timeInput: { height: 112, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, marginTop: 12, fontFamily: type.family, fontSize: 12, color: '#525253' },
  confirmChip: { alignSelf: 'flex-start', height: 16, minWidth: 58, borderRadius: 6, backgroundColor: '#DDF4D5', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6, marginTop: 6 },
  confirmChipText: { fontFamily: type.familyMedium, fontSize: 9, lineHeight: 11, color: '#328E6E' },
  primary: { height: 57, borderRadius: 27, backgroundColor: color.figmaRed, alignItems: 'center', justifyContent: 'center', marginTop: 22, shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 } },
  timePrimary: { marginTop: 38 },
  primaryText: { fontFamily: type.familyBold, fontSize: 20, color: '#FFFFFF' },
  secondary: { height: 57, borderRadius: 27, backgroundColor: '#D7D7D7', alignItems: 'center', justifyContent: 'center', marginTop: 9 },
  secondaryText: { fontFamily: type.familyBold, fontSize: 18, color: '#9A9A9F' },
});
