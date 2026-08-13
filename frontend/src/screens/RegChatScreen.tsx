import { useQueryClient } from '@tanstack/react-query';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import { ApiError } from '../api/config';
import { answerInterview, getPersona, listSlots, startInterview, startTier1Interview, type InterviewSession, type SlotInfo } from '../api/guardian';
import { useGuardianStore } from '../store/guardianStore';
import { useAuthStore } from '../store/authStore';
import BackIcon from '../../assets/figma/detail-back.svg';
import FigmaStatusBar from '../components/FigmaStatusBar';

const GUARDIAN_NAME = '보호자';
type Msg = { id: string; from: 'bot' | 'user'; text: string; pending?: boolean };

export default function RegChatScreen() {
  const qc = useQueryClient();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'RegChat'>>();
  const quick = route.params?.mode === 'quick';
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [slots, setSlots] = useState<SlotInfo[]>([]);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);
  const setPersona = useGuardianStore((state) => state.setPersona);
  // 이 인터뷰로 만들어질 페르소나의 **주인**. 안 넘기면 소유자 없는 페르소나가
  // 되어 등록해 놓고도 목록에 안 뜬다(소유자별 분리, 08-12).
  const guardianId = useAuthStore((state) => state.userId);

  const begin = useCallback(async () => {
    setError(null); setSession(null); setPending(null);
    try {
      // 빠른 등록(신고 직전 미니챗)은 **Tier1 5문항만** 묻는다. 여기까지 온 보호자는
      // 이미 가족이 사라진 상태라, 온보딩과 같은 12문항을 물으면 골든타임이 대화로
      // 간다. 나머지 7문항은 신고 접수 뒤 보완챗이 받는다.
      const opening = quick
        ? startTier1Interview(GUARDIAN_NAME, guardianId ?? undefined)
        : startInterview(GUARDIAN_NAME, undefined, guardianId ?? undefined);
      const [nextSession, catalog] = await Promise.all([opening, listSlots().catch(() => [] as SlotInfo[])]);
      setSession(nextSession); setSlots(catalog);
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
  }, [guardianId, quick]);

  useEffect(() => { begin(); }, [begin]);

  useEffect(() => {
    if (!session?.done || !session.persona_id) return;
    let cancelled = false;
    (async () => {
      try {
        const persona = await getPersona(session.persona_id!);
        if (cancelled) return;
        setPersona(persona);
        // 새로 등록한 가족이 홈 목록에 바로 뜨게 한다 — 목록은 별도 쿼리라
        // 무효화하지 않으면 다음에 앱을 켤 때까지 안 보인다.
        qc.invalidateQueries({ queryKey: ['personas'] });
        if (quick) navigation.replace('Report');
        else navigation.replace('RegDone', { personaId: persona.id, name: persona.name, age: persona.age });
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : String(e));
        qc.invalidateQueries({ queryKey: ['personas'] });
        if (quick) navigation.replace('Report');
        else navigation.replace('RegDone', { personaId: session.persona_id!, name: '', age: 0 });
      }
    })();
    return () => { cancelled = true; };
  }, [quick, session, navigation, setPersona]);

  const messages = useMemo<Msg[]>(() => {
    const server = (session?.messages ?? []).map((message, index) => ({
      id: `message-${index}`,
      from: message.role === 'assistant' ? ('bot' as const) : ('user' as const),
      text: message.text,
    }));
    return pending ? [...server, { id: 'pending', from: 'user' as const, text: pending, pending: true }] : server;
  }, [session, pending]);

  const submit = async () => {
    const answer = input.trim();
    if (!answer || !session || pending || session.done) return;
    setInput(''); setPending(answer); setError(null);
    try { setSession(await answerInterview(session.id, answer)); }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); setInput(answer); }
    finally { setPending(null); }
  };

  const filled = session?.filled_keys.length ?? 0;
  // 분모는 **이 세션이 실제로 묻는 슬롯 수**다. 미니챗은 tier1 만 물으므로 카탈로그
  // 전체(12)를 깔면 다 답해도 막대가 절반을 못 넘어 "아직 한참 남았나" 싶어진다.
  // 서버가 세션에 실어 주는 target_tiers 로 거른다 — 프론트에 개수를 박지 않는다.
  const tiers = session?.target_tiers;
  const scoped = tiers?.length ? slots.filter((slot) => tiers.includes(slot.tier)) : slots;
  const total = scoped.length || (quick ? 5 : 12);
  const progress = Math.max(25, Math.min(100, Math.round((filled / total) * 100))) as number;

  /**
   * 대화를 항상 맨 아래로 붙인다.
   *
   * `onContentSizeChange` 는 **메시지가 늘어날 때**만 온다. 키보드가 열리는 것은
   * 내용이 아니라 ScrollView 의 **높이**가 줄어드는 일이라 그 콜백이 안 걸리고,
   * 스크롤 위치가 그대로 남아 첫 질문이 보였다(현장 제보 08-12).
   * `onLayout` 은 자기 영역 크기가 바뀔 때 오므로 키보드 열림·닫힘·회전을 모두
   * 잡는다. 키보드 때문에 움직이는 것은 애니메이션 없이 붙인다 — 사용자가
   * 시킨 스크롤이 아니라서 미끄러지면 오히려 어수선하다.
   */
  const stickToBottom = (animated: boolean) => scrollRef.current?.scrollToEnd({ animated });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'height' : undefined}>
        <View style={styles.header}>
          <Pressable onPress={() => quick ? navigation.goBack() : navigation.navigate('GuardianTabs', { screen: 'GuardianHome' })} accessibilityRole="button" accessibilityLabel="뒤로" style={styles.back}><BackIcon width={10} height={18} color="#8E8E93" /></Pressable>
          <Text style={styles.title}>{quick ? '빠른 등록' : '사전 등록 인터뷰'}</Text>
          <View style={styles.headerSide} />
        </View>

        <View style={styles.progressWrap} accessibilityLabel={`${filled}개 항목 완료, 총 ${total}개`}>
          <View style={styles.progressTrack}><View style={[styles.progressActive, quick && styles.quickAccent, { width: `${progress}%` }]} /></View>
        </View>

        <ScrollView ref={scrollRef} style={styles.chat} contentContainerStyle={styles.chatContent} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled" onContentSizeChange={() => stickToBottom(true)} onLayout={() => stickToBottom(false)}>
          {!session && !error ? <View style={[styles.botBubble, quick && styles.quickBubble]}><ActivityIndicator size="small" color={quick ? color.figmaRed : color.brand} /></View> : null}
          {messages.map((message) => <View key={message.id} style={message.from === 'bot' ? styles.botRow : styles.userRow}>
            <View style={[message.from === 'bot' ? styles.botBubble : styles.userBubble, quick && message.from === 'bot' && styles.quickBubble, message.pending && styles.pending]}>
              <Text style={styles.messageText}>{message.text}</Text>
            </View>
          </View>)}
          {pending ? <View style={styles.botRow}><View style={styles.botBubble}><ActivityIndicator size="small" color={color.brand} /></View></View> : null}
          {error ? <Pressable onPress={!session ? begin : undefined} style={styles.error}><Text style={styles.errorText}>{error}</Text></Pressable> : null}
          {session?.llm_degraded ? <View style={styles.notice}><Text style={styles.noticeText}>AI 응답이 불안정해 기본 질문으로 이어가고 있어요. 등록은 계속 진행됩니다.</Text></View> : null}
        </ScrollView>

        <View style={styles.composer}>
          <TextInput
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder={session?.awaiting_confirmation ? '등록할까요? 답변해 주세요' : session ? '답변을 입력해 주세요' : '연결 중이에요…'}
            placeholderTextColor={color.figmaGray}
            returnKeyType="send"
            onSubmitEditing={submit}
            editable={!!session && !pending}
          />
          <Pressable onPress={submit} disabled={!input.trim() || !session || !!pending} accessibilityRole="button" accessibilityLabel="보내기" style={({ pressed }) => [styles.send, quick && styles.quickAccent, (!input.trim() || !session || !!pending) && styles.sendDisabled, pressed && styles.pressed]}><Text style={styles.sendText}>↑</Text></Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' }, flex: { flex: 1 },
  header: { height: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#FFFFFF' },
  back: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center' },
  headerSide: { width: 48, height: 48 },
  title: { fontFamily: type.familySemiBold, fontSize: 18, color: '#000000' },
  progressWrap: { height: 44, justifyContent: 'center', paddingHorizontal: 16, backgroundColor: '#FFFFFF' },
  progressTrack: { height: 4, borderRadius: 12, backgroundColor: '#E5E5EA', overflow: 'hidden' },
  progressActive: { height: 4, borderRadius: 12, backgroundColor: color.brand },
  quickAccent: { backgroundColor: color.figmaRed },
  chat: { flex: 1, backgroundColor: '#FFFFFF' },
  chatContent: { paddingTop: 0, paddingBottom: 12 },
  botRow: { alignItems: 'flex-start', paddingHorizontal: 21, paddingVertical: 7 },
  userRow: { alignItems: 'flex-end', paddingHorizontal: 21, paddingVertical: 7 },
  botBubble: { maxWidth: 280, minHeight: 38, borderRadius: 10, backgroundColor: '#DDF6D2', paddingHorizontal: 14, paddingVertical: 10, justifyContent: 'center' },
  quickBubble: { backgroundColor: '#F7B5B5' },
  userBubble: { maxWidth: 280, minHeight: 38, borderRadius: 10, backgroundColor: '#EDEDED', paddingHorizontal: 14, paddingVertical: 10, justifyContent: 'center' },
  messageText: { fontFamily: type.family, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#000000' },
  pending: { opacity: 0.55 },
  error: { marginHorizontal: 21, marginTop: 7, borderRadius: 10, backgroundColor: color.criticalWash, padding: 12 },
  errorText: { fontFamily: type.family, fontSize: 12, lineHeight: 18, color: color.critical },
  notice: { marginHorizontal: 21, marginTop: 7, borderRadius: 10, backgroundColor: color.figmaField, padding: 12 },
  noticeText: { fontFamily: type.family, fontSize: 11, lineHeight: 16, color: '#525253' },
  composer: { height: 68, flexDirection: 'row', alignItems: 'center', paddingLeft: 16, paddingRight: 12, backgroundColor: '#FFFFFF' },
  input: { flex: 1, height: 36, borderRadius: 17, borderWidth: 1, borderColor: 'rgba(0,0,0,0.06)', backgroundColor: '#FAFAFA', paddingHorizontal: 12, paddingVertical: 0, fontFamily: type.family, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: '#000000' },
  send: { width: 28, height: 30, borderRadius: 15, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center', marginLeft: 8 },
  sendDisabled: { opacity: 0.55 }, sendText: { fontFamily: type.familyBold, fontSize: 23, lineHeight: 25, color: '#FFFFFF' }, pressed: { opacity: 0.75 },
});
