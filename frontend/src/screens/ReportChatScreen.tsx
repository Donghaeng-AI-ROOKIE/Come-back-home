import React, { useRef, useState } from 'react';
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
import { useMyLocation } from '../hooks/useMyLocation';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import FigmaStatusBar from '../components/FigmaStatusBar';

type Step = 'summary' | 'location' | 'time';

export default function ReportChatScreen() {
  const userId = useAuthStore((s) => s.userId);
  const { point: myPoint } = useMyLocation(true);
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const queryClient = useQueryClient();
  const { caseId } = useRoute<RouteProp<RootStackParamList, 'ReportChat'>>().params;
  const [step, setStep] = useState<Step>('summary');
  const [summary, setSummary] = useState('');
  const [location, setLocation] = useState('');
  const [seenAt, setSeenAt] = useState('');
  const [sending, setSending] = useState(false);
  /**
   * 서버가 '추가 확인'을 한 번이라도 돌려보냈는가.
   *
   * 서버는 **좌표**를 요구하는데 사용자는 글로만 답할 수 있다("신촌이요").
   * 그래서 답을 적어 다시 보내도 같은 질문이 또 오고, 화면이 앞으로 못 간다
   * (현장 제보 08-11 — '답변하고 제보하기'를 눌러도 그대로).
   * 사용자가 할 몫을 다 했으면 그 다음 전송은 강제로 접수한다 — 적어 준 글은
   * 제보 본문에 그대로 남아 지휘자가 읽을 수 있다.
   */
  const askedOnce = useRef(false);

  const submit = async ({ withoutLocation = false, withoutTime = false } = {}) => {
    if (sending) return;
    setSending(true);
    try {
      const includeLocation = !withoutLocation && !!location.trim();
      const includeTime = !withoutTime && !!seenAt.trim();
      const result = await submitTip(caseId, {
        // **목격 좌표는 제보자의 현재 위치로 보낸다.**
        //
        // 글로만 "서강대 정문"이라고 적으면 서버가 좌표로 바꾸지 못해
        // need_more(location) 로 되돌아오고, 제보가 **저장조차 되지 않는다**
        // (실측 08-11 — 사용자가 여러 번 보내도 '추가 확인이 필요해요'만 반복).
        // 강제로 보내도 좌표가 없으면 POA 갱신에 기여하지 못한다.
        //
        // 수색 중인 시민은 목격 지점에 서 있다 — 그 좌표가 가장 정확한 근사다.
        // 위치를 못 구했을 때만 예전처럼 자유서술로 보낸다.
        location: myPoint ?? undefined,
        seenAt: myPoint ? new Date().toISOString().slice(0, 19) : undefined,
        text: [
          summary.trim(),
          includeLocation && `목격 위치: ${location.trim()}`,
          includeTime && `목격 시각: ${seenAt.trim()}`,
        ].filter(Boolean).join(' / ') || '목격 제보',
      }, { force: withoutLocation || withoutTime || askedOnce.current, reporterUserId: userId ?? undefined });
      if ('status' in result) {
        askedOnce.current = true;   // 다음 전송은 반드시 접수된다
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
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'height' : undefined}>
        <ScrollView
          style={styles.flex}
          contentContainerStyle={[styles.scrollContent, long && styles.scrollContentLong]}
          keyboardShouldPersistTaps="handled"
          automaticallyAdjustKeyboardInsets
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
  scrollContent: { minHeight: 768, flexGrow: 1 },
  scrollContentLong: { minHeight: 905 },
  body: { flex: 1, paddingHorizontal: 23, paddingTop: 27 },
  title: { fontFamily: type.familyExtraBold, fontSize: 18, lineHeight: 23, color: '#000000', marginLeft: -3 },
  desc: { fontFamily: type.family, fontSize: 11, lineHeight: 14, color: '#525253', marginLeft: -3, marginTop: 16 },
  initialInput: { height: 112, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, marginTop: 26, fontFamily: type.family, fontSize: 12, color: '#525253' },
  initialButton: { height: 57, borderRadius: 27, backgroundColor: color.figmaRed, alignItems: 'center', justifyContent: 'center', marginTop: 18, shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  summaryLabel: { fontFamily: type.familySemiBold, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#525253', marginTop: 21 },
  summaryInput: { height: 74, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, marginTop: 4, fontFamily: type.family, fontSize: 12, color: '#525253' },
  locationLabel: { fontFamily: type.familySemiBold, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#525253', marginTop: 31 },
  timeLabel: { fontFamily: type.familySemiBold, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#525253', marginTop: 25 },
  question: { fontFamily: type.family, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253', marginTop: 12 },
  locationInput: { height: 112, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, marginTop: 12, fontFamily: type.family, fontSize: 12, color: '#525253' },
  timeInput: { height: 112, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, marginTop: 12, fontFamily: type.family, fontSize: 12, color: '#525253' },
  confirmChip: { alignSelf: 'flex-start', height: 16, minWidth: 58, borderRadius: 6, backgroundColor: '#DDF4D5', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6, marginTop: 6 },
  confirmChipText: { fontFamily: type.familyMedium, fontSize: 9, lineHeight: 11, color: '#328E6E' },
  primary: { height: 57, borderRadius: 27, backgroundColor: color.figmaRed, alignItems: 'center', justifyContent: 'center', marginTop: 22, shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  timePrimary: { marginTop: 38 },
  primaryText: { fontFamily: type.familyBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#FFFFFF' },
  secondary: { height: 57, borderRadius: 27, backgroundColor: '#D7D7D7', alignItems: 'center', justifyContent: 'center', marginTop: 9 },
  secondaryText: { fontFamily: type.familyBold, fontSize: 18, color: '#525253' },
});
