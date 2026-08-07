/**
 * 등록 탭 (spec §3.4, reg-content). 라이트 · 산책 그린 톤.
 * 디지털 트윈 사전등록 챗봇 — **대화를 서버가 몬다**(Phase 0, Mi:dm).
 * 다음 질문을 고르고 문장화하고 답에서 값을 뽑는 것은 전부 백엔드다. 이 화면은
 * 매 턴 서버가 준 messages 를 그리고, 완료되면 persona_id 를 RegDone 으로 넘긴다.
 *
 * Figma 확정 프레임에 맞춰 헤더·4px 진행바·13px 말풍선·원형 위쪽 전송 버튼만
 * 보인다. 진행률은 서버의 채워진 슬롯 수로 계산하며 질문 순서는 서버가 정한다.
 * 완료 요약은 RegDone 화면이 맡는다.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { SvgXml } from 'react-native-svg';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import { color, radius, space, type } from '../theme/tokens';
import { gColor, gFont } from '../theme/guardianTokens';
import { hexToRgba } from '../utils/color';
import type { RootStackParamList } from '../navigation/types';

import { icBackXml } from '../assets/guardianSvg';
import ChatBubble from '../components/ChatBubble';
import ChatComposer from '../components/ChatComposer';
import CTAButton from '../components/CTAButton';

import { ApiError } from '../api/config';
import {
  answerInterview,
  getPersona,
  listSlots,
  startInterview,
  type InterviewSession,
  type SlotInfo,
} from '../api/guardian';
import { useGuardianStore } from '../store/guardianStore';
import { GuardianStandaloneTabBar } from '../components/GuardianTabBar';

const ACCENT = gColor.progressGreen;

/**
 * 인증 도입 전 임시 보호자 이름 — 세션 생성에만 쓰이고 페르소나에는 안 들어간다.
 * 로그인이 붙으면 계정 표시명으로 교체한다.
 */
const GUARDIAN_NAME = '보호자';

type Msg = { id: string; from: 'bot' | 'user'; text: string; pending?: boolean };

export default function RegChatScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  // 탭에서 열린 일반 등록은 현재 navigation이 BottomTabNavigation이다. 완료 화면은
  // 루트 스택에 올려야 하므로 부모를 사용하고, 빠른 등록(root 화면)은 현재 객체를 쓴다.
  const stackNavigation = navigation.getParent<NativeStackNavigationProp<RootStackParamList>>() ?? navigation;
  // 빠른 등록(신고 중 미등록) 모드 — 같은 인터뷰를 적색 팔레트로 진행한다.
  // 서버 인터뷰가 필수(tier 1) 슬롯부터 묻기 때문에 백엔드 분기는 필요 없다.
  // 탭으로 열리면 params 가 없으므로 기본(그린) 모드다.
  const route = useRoute<RouteProp<RootStackParamList, 'RegChat'>>();
  const quick = route.params?.quick ?? false;
  const accent = quick ? gColor.quickRed : ACCENT;
  const botBubbleBg = quick ? gColor.bubbleBotQuick : gColor.bubbleBot;

  const [session, setSession] = useState<InterviewSession | null>(null);
  const [slots, setSlots] = useState<SlotInfo[]>([]);
  const [input, setInput] = useState('');
  /** 전송 중 사용자 발화 — 서버 왕복(Mi:dm 추출+문장화) 동안 화면에 먼저 띄운다. */
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<ScrollView>(null);

  const begin = useCallback(async () => {
    setError(null);
    setSession(null);
    setPending(null);
    try {
      // 슬롯 카탈로그는 진행률의 분모다. 실패해도 대화는 계속돼야 하므로 따로 잡는다.
      const [s, catalog] = await Promise.all([
        startInterview(GUARDIAN_NAME),
        listSlots().catch(() => [] as SlotInfo[]),
      ]);
      setSession(s);
      setSlots(catalog);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    begin();
  }, [begin]);

  // 완료 → 서버가 페르소나를 만들고 persona_id 를 채운다.
  //
  // **draft_fields 에서 이름을 꺼내지 않는다.** 그건 인터뷰 도중의 초안이라
  // 중첩 구조({identity:{name}})일 수 있고, 최종 정규화는 서버가 한다.
  // 서버가 만든 페르소나를 다시 읽는 것이 유일하게 믿을 수 있는 값이다
  // (2026-08-05: 초안에서 꺼내다가 이름이 빈 채로 넘어간 버그).
  //
  // 스토어에도 넣는다 — 보호자 홈·신고 화면이 "사전 등록해 둔 정보"를 띄우려면
  // 이게 있어야 한다. setPersona 를 아무도 부르지 않아 홈이 계속 "등록된 가족
  // 없음"이던 문제의 원인이었다.
  const setPersona = useGuardianStore((st) => st.setPersona);
  useEffect(() => {
    if (!session?.done || !session.persona_id) return;
    let cancelled = false;
    (async () => {
      try {
        const persona = await getPersona(session.persona_id!);
        if (cancelled) return;
        setPersona(persona);
        if (quick) stackNavigation.goBack();
        else stackNavigation.navigate('RegDone', {
          personaId: persona.id, name: persona.name, age: persona.age,
        });
      } catch (e) {
        if (cancelled) return;
        // 등록 자체는 성공했다 — 조회만 실패했으므로 진행은 시킨다.
        setError(e instanceof ApiError ? e.message : String(e));
        if (quick) stackNavigation.goBack();
        else stackNavigation.navigate('RegDone', {
          personaId: session.persona_id!, name: '', age: 0,
        });
      }
    })();
    return () => { cancelled = true; };
  }, [session, quick, setPersona, stackNavigation]);

  const messages = useMemo<Msg[]>(() => {
    const fromServer = (session?.messages ?? []).map((m, i) => ({
      id: `s${i}`,
      from: m.role === 'assistant' ? ('bot' as const) : ('user' as const),
      text: m.text,
    }));
    return pending
      ? [...fromServer, { id: 'pending', from: 'user' as const, text: pending, pending: true }]
      : fromServer;
  }, [session, pending]);

  const submitAnswer = async (raw: string) => {
    const answer = raw.trim();
    if (!answer || !session || pending || session.done) return;
    setInput('');
    setPending(answer);
    setError(null);
    try {
      setSession(await answerInterview(session.id, answer));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setInput(answer); // 실패한 답변을 되돌려 준다 — 다시 타이핑하게 만들지 않는다
    } finally {
      setPending(null);
    }
  };

  const canGoBack = navigation.canGoBack();

  const totalSlots = slots.length;
  const filledCount = session?.filled_keys.length ?? 0;
  const progressA11y = totalSlots
    ? `${filledCount}개 항목 완료, 총 ${totalSlots}개.`
    : '등록 진행 중';

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        {/* 헤더 */}
        <View style={styles.header}>
          <View style={styles.headerRow}>
            {canGoBack ? (
              <Pressable
                onPress={() => navigation.goBack()}
                accessibilityRole="button"
                accessibilityLabel="뒤로"
                hitSlop={8}
                style={({ pressed }) => [styles.backBtn, pressed && styles.pressed]}
              >
                <SvgXml xml={icBackXml} width={10} height={18} />
              </Pressable>
            ) : (
              <View style={styles.headerSpacer} />
            )}
            <Text
              style={styles.title}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
              numberOfLines={1}
            >
              {quick ? '빠른 등록' : '사전 등록 인터뷰'}
            </Text>
            <View style={styles.headerSpacer} />
          </View>

          <View style={styles.progress} accessible accessibilityLabel={progressA11y}>
            {/* 진행바 = 채운 슬롯 비율. 어떤 순서로 물을지는 서버가 정하므로
                "몇 개를 채웠나"만 표시한다(프론트 단계 인덱스는 진실이 아니다). */}
            <View style={styles.progressTrack}>
              <View
                style={[
                  styles.progressFill,
                  { width: `${totalSlots ? Math.max((filledCount / totalSlots) * 100, 4) : 4}%`, backgroundColor: accent },
                ]}
              />
            </View>
          </View>
        </View>

        {/* 대화 */}
        <ScrollView
          ref={scrollRef}
          style={styles.scroll}
          contentContainerStyle={styles.chatContent}
          showsVerticalScrollIndicator={false}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
        >
          {messages.map((m) => {
            if (m.from === 'bot') {
              return <ChatBubble key={m.id} from="bot" text={m.text} bg={botBubbleBg} guardian />;
            }
            return (
              <View key={m.id} style={styles.userRow}>
                <View
                  style={[styles.userBubble, m.pending && styles.bubblePending]}
                  accessible
                  accessibilityLabel={`나. ${m.text}`}
                >
                  <Text
                    style={styles.userText}
                    allowFontScaling
                    maxFontSizeMultiplier={type.maxScale}
                  >
                    {m.text}
                  </Text>
                </View>
              </View>
            );
          })}

          {/* Mi:dm 이 답을 읽고 다음 질문을 만드는 동안 — 무응답으로 보이지 않게 */}
          {pending ? (
            <View style={styles.botRow} accessible accessibilityLabel="답변을 확인하고 있어요">
              <View style={styles.typingBubble}>
                <ActivityIndicator size="small" color={accent} />
              </View>
            </View>
          ) : null}

          {error ? (
            <View style={styles.errorCard} accessible accessibilityLabel={`오류. ${error}`}>
              <Text
                style={styles.errorText}
                allowFontScaling
                maxFontSizeMultiplier={type.maxScale}
              >
                {session ? '전송하지 못했어요.' : '등록을 시작하지 못했어요.'} {error}
              </Text>
              {!session ? (
                <CTAButton label="다시 시도" onPress={begin} accent={accent} />
              ) : null}
            </View>
          ) : null}

          {/* Mi:dm 호출이 반복 실패해 고정 문장으로 떨어진 상태 — 숨기지 않는다 */}
          {session?.llm_degraded ? (
            <View style={styles.warnCard}>
              <Text
                style={styles.warnText}
                allowFontScaling
                maxFontSizeMultiplier={type.maxScale}
              >
                AI 응답이 불안정해 기본 질문으로 이어가고 있어요. 등록은 계속 진행됩니다.
              </Text>
            </View>
          ) : null}

          {/* 완료 요약은 RegDone 화면이 맡는다 — persona_id 를 다음 단계로
              넘겨야 해서 화면 안에서 끝내지 않고 전환한다(위 useEffect). */}
        </ScrollView>

        {/* 입력 영역 */}
        <View style={styles.footer}>
          <ChatComposer
            value={input}
            onChangeText={setInput}
            onSend={() => submitAnswer(input)}
            placeholder={session ? '메시지를 입력하세요' : '연결 중이에요…'}
            accent={accent}
            guardian
          />
        </View>
      </KeyboardAvoidingView>
      {quick ? <GuardianStandaloneTabBar active="GuardianReg" accent={accent} /> : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surface },
  flex: { flex: 1 },

  // 헤더
  header: {
    backgroundColor: color.surface,
    paddingHorizontal: 16,
    paddingTop: 0,
    paddingBottom: 0,
  },
  headerRow: { flexDirection: 'row', alignItems: 'center' },
  backBtn: {
    width: 42,
    height: 48,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerSpacer: { width: 42, height: 48 },
  title: {
    flex: 1,
    textAlign: 'center',
    fontSize: 18,
    color: '#000000',
    fontFamily: gFont.semiBold,
    letterSpacing: -0.3,
  },
  progress: { height: 44, justifyContent: 'flex-start' },
  progressTrack: {
    height: 4,
    borderRadius: 0,
    backgroundColor: gColor.track,
    overflow: 'hidden',
  },
  progressFill: {
    height: 4,
    borderRadius: 0,
    backgroundColor: gColor.progressGreen,
  },
  // 대화 — 피그마: 흰 배경 위 그린/그레이 말풍선
  scroll: { flex: 1, backgroundColor: gColor.surface },
  chatContent: { paddingHorizontal: 24, paddingVertical: 16, gap: 8 },

  // 봇 말풍선 행 (타이핑 표시용)
  botRow: { flexDirection: 'row', alignItems: 'flex-end', gap: space.sm },

  // 사용자 말풍선 — 피그마: #EDEDED 플랫, 검정 글자
  userRow: { flexDirection: 'row', justifyContent: 'flex-end' },
  userBubble: {
    maxWidth: 280,
    backgroundColor: gColor.bubbleUser,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  userText: {
    fontSize: 13,
    color: '#000000',
    fontFamily: gFont.regular,
    lineHeight: 19,
  },

  /** 전송 중인 사용자 발화 — 아직 서버가 못 받았음을 흐리게 표시. */
  bubblePending: { opacity: 0.55 },

  /** Mi:dm 이 답을 읽고 다음 질문을 만드는 동안의 자리표시 버블. */
  typingBubble: {
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.lg,
    borderBottomLeftRadius: radius.sm,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
  },

  // 오류·경고
  errorCard: {
    marginTop: space.md,
    backgroundColor: hexToRgba(color.critical, 0.08),
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: hexToRgba(color.critical, 0.35),
    padding: space.lg,
    gap: space.md,
  },
  errorText: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.critical,
    fontFamily: gFont.semiBold,
    lineHeight: 20,
  },
  warnCard: {
    marginTop: space.md,
    backgroundColor: color.surfaceAlt,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.md,
  },
  warnText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: gFont.medium,
    lineHeight: 20,
  },

  // 입력 영역
  footer: {
    paddingHorizontal: 0,
    paddingTop: 0,
    backgroundColor: color.surface,
  },

  pressed: { opacity: 0.6 },
});
