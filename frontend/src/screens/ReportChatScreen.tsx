import React, { useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import type { TipResult } from '../types/domain';
import { useQueryClient } from '@tanstack/react-query';
import { color, type } from '../theme/tokens';
import { submitTip } from '../api/client';
import { useAuthStore } from '../store/authStore';
import { useMyLocation } from '../hooks/useMyLocation';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import FigmaStatusBar from '../components/FigmaStatusBar';

/** 서버가 되물을 수 있는 항목. */
type Missing = 'location' | 'time';

export default function ReportChatScreen() {
  const userId = useAuthStore((s) => s.userId);
  const { point: myPoint } = useMyLocation(true);
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const queryClient = useQueryClient();
  const { caseId } = useRoute<RouteProp<RootStackParamList, 'ReportChat'>>().params;
  /**
   * **서버가 되물은 항목만** 화면에 띄운다.
   *
   * 예전에는 화면이 summary → location → time 3단을 **무조건** 밟았다. 서버에
   * 물어보지도 않고 진행하는 순서라, 사용자가 "11시에 대흥역에서 봤어요"처럼
   * 다 적어도 위치와 시각을 또 물었다(실측 08-12 — "항상 다시 물어본다").
   *
   * 되묻기 판정은 서버에 이미 있다(backend tip_flow.process_tip): 제보 문장을
   * Mi:dm 2.0 Mini 로 구조화해 장소·시각을 뽑고, 장소는 지오코딩까지 해 본 뒤
   * 그래도 없을 때만 need_more 를 돌려준다. 그 판정을 쓰면 될 일이었다.
   */
  const [asked, setAsked] = useState<{ location: boolean; time: boolean }>({ location: false, time: false });
  const answering = asked.location || asked.time;
  const [summary, setSummary] = useState('');
  const [location, setLocation] = useState('');
  const [seenAt, setSeenAt] = useState('');
  const [sending, setSending] = useState(false);
  /** 전송이 오래 걸릴 때 화면에 띄우는 진행 안내(왜 기다리는지). */
  const [progress, setProgress] = useState('');

  /**
   * 서버로 한 번 보낸다. 되묻기면 그 항목을 화면에 세우고 `null` 을 돌려준다.
   *
   * 좌표·시각을 **기본으로 채워 보내지 않는다.** 예전에는 제보자의 현재 좌표와
   * 전송 시각을 항상 실어 보냈는데, 그러면 서버의 되묻기 게이트가 구조적으로
   * 한 번도 걸리지 않는다(위치·시각이 이미 채워진 것으로 보인다). 판정을
   * 서버에 맡기기로 한 이상 그 값을 앞질러 채우면 안 된다. 사용자가 적은
   * 문장을 그대로 보내고, 장소·시각 추출은 서버(Mi:dm Mini + 지오코딩)가 한다.
   *
   * `useMyPoint` 는 사용자가 '위치 없이 그대로 제보하기'를 골랐을 때만 쓴다 —
   * 수색 중인 시민은 목격 지점 근처에 서 있으므로, 글로 못 적겠다면 그 좌표가
   * 남아 있는 근사 중 가장 낫다.
   */
  const send = async (opts: { force?: boolean; useMyPoint?: boolean }, retried = false): Promise<TipResult | null> => {
    const result = await submitTip(caseId, {
      location: opts.useMyPoint ? (myPoint ?? undefined) : undefined,
      text: [
        summary.trim(),
        location.trim() && `목격 위치: ${location.trim()}`,
        seenAt.trim() && `목격 시각: ${seenAt.trim()}`,
      ].filter(Boolean).join(' / ') || '목격 제보',
    }, { force: !!opts.force, reporterUserId: userId ?? undefined });

    if (!('status' in result)) return result;

    const missing: Missing = result.missing.includes('location') ? 'location' : 'time';
    if (asked[missing] && !retried) {
      // 이미 물어본 항목을 또 되묻는다 = 우리가 받아 보낸 답을 서버가 좌표·시각으로
      // 바꾸지 못했다는 뜻이다. 여기서 또 물으면 답을 적어도 화면이 앞으로 못 가는
      // 막다른 골목이 된다(실측 08-11). 적어 준 글은 제보 본문에 그대로 남으므로
      // 지휘자가 읽을 수 있다 — 그대로 접수한다.
      //
      // 현재 좌표는 **위치를 못 잡았을 때만** 붙인다. 시각을 못 읽은 경우에는
      // 위치가 이미 글에서 지오코딩된 상태라, 여기서 좌표를 실어 보내면 그
      // 결과를 제보자의 현재 위치로 덮어쓴다.
      return send({ force: true, useMyPoint: missing === 'location' }, true);
    }
    setAsked((prev) => ({ ...prev, [missing]: true }));
    Alert.alert('추가 확인이 필요해요', result.reason || '목격 위치나 시각을 조금 더 알려주세요.');
    return null;
  };

  const submit = async (opts: { force?: boolean; useMyPoint?: boolean } = {}) => {
    if (sending) return;
    if (!summary.trim()) {
      Alert.alert('제보 내용을 입력해 주세요');
      return;
    }
    setSending(true);
    /**
     * 오래 걸리는 이유를 화면이 말하게 한다.
     *
     * 신뢰도가 높은 제보는 접수와 동시에 **예상 경로를 다시 계산한다**(층2).
     * 그 지역 도로망이 서버에 없으면 내려받느라 오래 걸린다 —
     * 실측 08-12: 신촌 사건에 망원역 제보를 넣으니 **88초**.
     *
     * 그동안 화면에는 '전송 중…'만 떠 있었다. 90초 가까이 그 상태면 사용자는
     * 앱이 멈춘 줄 안다("무한 로딩이 걸린다" 현장 제보). 실제로는 정상 동작이고,
     * 그 시간이 예상 경로를 좁히는 데 쓰이고 있다. 그러면 그렇게 말해야 한다.
     */
    setProgress('');
    const t1 = setTimeout(() => setProgress('제보를 반영해 예상 경로를 다시 계산하고 있어요.'), 6_000);
    const t2 = setTimeout(() => setProgress('처음 보는 지역이라 지도를 내려받는 중입니다. 최대 2분까지 걸릴 수 있어요.'), 25_000);
    try {
      const result = await send(opts);
      if (result == null) {   // 되묻기 — 화면이 그 항목을 띄운 상태다
        clearTimeout(t1); clearTimeout(t2); setProgress('');
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
    } finally {
      clearTimeout(t1);
      clearTimeout(t2);
      setProgress('');
    }
  };

  const long = asked.time;
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

            {!answering ? (
              <>
                <TextInput
                  value={summary}
                  onChangeText={setSummary}
                  multiline
                  style={styles.initialInput}
                  textAlignVertical="top"
                  accessibilityLabel="목격 내용"
                />
                {/* 이제 이 버튼이 **실제로 제보를 보낸다.** 위치·시각을 다 적었으면
                    여기서 끝난다 — 서버가 못 뽑은 항목만 아래에서 되묻는다. */}
                <Pressable style={styles.initialButton} onPress={() => submit()} disabled={sending}>
                  <Text style={styles.primaryText}>{sending ? '전송 중…' : '제보하기'}</Text>
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

                {/* 되묻는 항목만 띄운다 — 서버가 위치는 알아냈고 시각만 필요하다면
                    위치 칸은 나오지 않는다. */}
                {asked.location ? (
                  <>
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
                  </>
                ) : null}

                {asked.time ? (
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
                  </>
                ) : null}

                <Pressable
                  style={[styles.primary, asked.time && styles.timePrimary]}
                  onPress={() => submit()}
                  disabled={sending}
                >
                  <Text style={styles.primaryText}>{sending ? '전송 중…' : '답변하고 제보하기'}</Text>
                </Pressable>
                {/* 건너뛰기 — force 로 그대로 접수한다. 위치를 건너뛸 때는 제보자의
                    현재 좌표를 근사로 함께 보낸다(좌표가 없으면 POA 갱신에 기여하지
                    못한다). 시각은 근사로 지어내지 않는다 — 층2 판정의 입력이라
                    전송 시각을 목격 시각으로 적으면 지도를 틀리게 만든다. */}
                {asked.time ? (
                  <Pressable style={styles.secondary} onPress={() => submit({ force: true })} disabled={sending}>
                    <Text style={styles.secondaryText}>시각 없이 그대로 제보하기</Text>
                  </Pressable>
                ) : (
                  <Pressable style={styles.secondary} onPress={() => submit({ force: true, useMyPoint: true })} disabled={sending}>
                    <Text style={styles.secondaryText}>위치 없이 그대로 제보하기</Text>
                  </Pressable>
                )}
              </>
            )}

            {/* 왜 기다리는지 화면이 말한다. 문구는 만들어져 있었는데 **어디에도
                그려지지 않아** 사용자는 '전송 중…'만 90초 동안 봤다(실측 08-12).
                이제 첫 누름부터 실제 전송이 걸리므로 더 자주 보이는 자리다. */}
            {progress ? <Text style={styles.progress} accessibilityRole="alert">{progress}</Text> : null}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
      {/* 탭바는 스크롤 **밖**에 둔다. 안에 있으면 대화 내용과 함께 스크롤돼
          입력할 때마다 위치가 튀고, 목록 맨 아래로 밀려 화면에서 사라진다
          (현장 제보 08-12). 다른 화면 11곳은 모두 밖에 있고 여기만 안이었다. */}
      <FigmaFlowTabBar mode="citizen" active="alert" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  flex: { flex: 1 },
  scrollContent: { minHeight: 768, flexGrow: 1 },
  scrollContentLong: { minHeight: 905 },
  body: { flex: 1, paddingHorizontal: 23, paddingTop: 27 },
  title: { fontFamily: type.familyCssExtraBold, fontSize: 18, lineHeight: 23, color: '#000000', marginLeft: -3 },
  desc: { fontFamily: type.familyCss, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253', marginLeft: -3, marginTop: 16 },
  initialInput: { height: 112, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, marginTop: 26, fontFamily: type.familyCss, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253' },
  initialButton: { height: 57, borderRadius: 26, backgroundColor: color.figmaRed, alignItems: 'center', justifyContent: 'center', marginTop: 18, shadowColor: '#000000', shadowOpacity: 0.24, shadowRadius: 4, shadowOffset: { width: 0, height: 3 }, elevation: 4 },
  summaryLabel: { fontFamily: type.familyRobotoSemiBold, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#525253', marginTop: 21 },
  summaryInput: { height: 74, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, marginTop: 4, fontFamily: type.familyCss, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253' },
  locationLabel: { fontFamily: type.familyRobotoSemiBold, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#525253', marginTop: 31 },
  timeLabel: { fontFamily: type.familyRobotoSemiBold, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#525253', marginTop: 25 },
  question: { fontFamily: type.familyCss, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253', marginTop: 12 },
  locationInput: { height: 112, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, marginTop: 12, fontFamily: type.familyCss, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253' },
  timeInput: { height: 112, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, marginTop: 12, fontFamily: type.familyCss, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253' },
  confirmChip: { alignSelf: 'flex-start', height: 16, minWidth: 58, borderRadius: 6, backgroundColor: '#DDF4D5', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6, marginTop: 6 },
  confirmChipText: { fontFamily: type.familyCssMedium, fontSize: 9, lineHeight: 11, color: '#328E6E' },
  primary: { height: 57, borderRadius: 26, backgroundColor: color.figmaRed, alignItems: 'center', justifyContent: 'center', marginTop: 22, shadowColor: '#000000', shadowOpacity: 0.24, shadowRadius: 4, shadowOffset: { width: 0, height: 3 }, elevation: 4 },
  timePrimary: { marginTop: 38 },
  primaryText: { fontFamily: type.familyCssBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#FFFFFF' },
  secondary: { height: 57, borderRadius: 26, backgroundColor: '#DADADA', alignItems: 'center', justifyContent: 'center', marginTop: 9, shadowColor: '#000000', shadowOpacity: 0.14, shadowRadius: 3, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  secondaryText: { fontFamily: type.familyCssBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#8E8E93' },
  progress: { fontFamily: type.familyCss, fontSize: 11, lineHeight: 15, letterSpacing: 0.07, color: '#525253', textAlign: 'center', marginTop: 12 },
});
