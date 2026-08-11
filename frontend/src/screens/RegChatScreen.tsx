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
import { answerInterview, getPersona, listSlots, startInterview, type InterviewSession, type SlotInfo } from '../api/guardian';
import { useGuardianStore } from '../store/guardianStore';
import BackIcon from '../../assets/figma/detail-back.svg';
import FigmaStatusBar from '../components/FigmaStatusBar';

const GUARDIAN_NAME = '보호자';
type Msg = { id: string; from: 'bot' | 'user'; text: string; pending?: boolean };

export default function RegChatScreen() {
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

  const begin = useCallback(async () => {
    setError(null); setSession(null); setPending(null);
    try {
      const [nextSession, catalog] = await Promise.all([startInterview(GUARDIAN_NAME), listSlots().catch(() => [] as SlotInfo[])]);
      setSession(nextSession); setSlots(catalog);
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
  }, []);

  useEffect(() => { begin(); }, [begin]);

  useEffect(() => {
    if (!session?.done || !session.persona_id) return;
    let cancelled = false;
    (async () => {
      try {
        const persona = await getPersona(session.persona_id!);
        if (cancelled) return;
        setPersona(persona);
        if (quick) navigation.replace('Report');
        else navigation.replace('RegDone', { personaId: persona.id, name: persona.name, age: persona.age });
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : String(e));
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
  const total = slots.length || 12;
  const progress = Math.max(25, Math.min(100, Math.round((filled / total) * 100))) as number;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.header}>
          <Pressable onPress={() => quick ? navigation.goBack() : navigation.navigate('GuardianTabs', { screen: 'GuardianHome' })} accessibilityRole="button" accessibilityLabel="뒤로" style={styles.back}><BackIcon width={10} height={18} color="#8E8E93" /></Pressable>
          <Text style={styles.title}>{quick ? '빠른 등록' : '사전 등록 인터뷰'}</Text>
          <View style={styles.headerSide} />
        </View>

        <View style={styles.progressWrap} accessibilityLabel={`${filled}개 항목 완료, 총 ${total}개`}>
          <View style={styles.progressTrack}><View style={[styles.progressActive, quick && styles.quickAccent, { width: `${progress}%` }]} /></View>
        </View>

        <ScrollView ref={scrollRef} style={styles.chat} contentContainerStyle={styles.chatContent} showsVerticalScrollIndicator={false} onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}>
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
  messageText: { fontFamily: type.family, fontSize: 13, lineHeight: 18, color: '#000000' },
  pending: { opacity: 0.55 },
  error: { marginHorizontal: 21, marginTop: 7, borderRadius: 10, backgroundColor: color.criticalWash, padding: 12 },
  errorText: { fontFamily: type.family, fontSize: 12, lineHeight: 18, color: color.critical },
  notice: { marginHorizontal: 21, marginTop: 7, borderRadius: 10, backgroundColor: color.figmaField, padding: 12 },
  noticeText: { fontFamily: type.family, fontSize: 11, lineHeight: 16, color: '#525253' },
  composer: { height: 68, flexDirection: 'row', alignItems: 'center', paddingLeft: 16, paddingRight: 12, backgroundColor: '#FFFFFF' },
  input: { flex: 1, height: 36, borderRadius: 17, borderWidth: 1, borderColor: 'rgba(0,0,0,0.06)', backgroundColor: '#FAFAFA', paddingHorizontal: 12, paddingVertical: 0, fontFamily: type.family, fontSize: 13, color: '#000000' },
  send: { width: 28, height: 30, borderRadius: 15, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center', marginLeft: 8 },
  sendDisabled: { opacity: 0.55 }, sendText: { fontFamily: type.familyBold, fontSize: 23, lineHeight: 25, color: '#FFFFFF' }, pressed: { opacity: 0.75 },
});
