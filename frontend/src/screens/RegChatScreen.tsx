/**
 * 등록 탭 (spec §3.4, reg-content). 라이트 · 산책 그린 톤.
 * 디지털 트윈 사전등록 챗봇 — **대화를 서버가 몬다**(Phase 0, Mi:dm).
 * 다음 질문을 고르고 문장화하고 답에서 값을 뽑는 것은 전부 백엔드다. 이 화면은
 * 매 턴 서버가 준 messages 를 그리고, 완료되면 persona_id 를 RegDone 으로 넘긴다.
 *
 * 목업(reg-content.dc.html) 충실 재현:
 *  - 헤더: 뒤로 · 가운데 정렬 "가족 등록" · 진행 도트(현재 단계 알약 강조) · "N단계 · 5분이면 끝나요".
 *  - 그린 틴트 대화 배경 위 흰색 AI 말풍선(로봇 아바타) + 솔리드 그린 사용자 말풍선.
 *  - 상단 안심 배너("정보는 안전하게 보관되고, 발견 즉시 파기돼요 🔒").
 *  - 하단: 빠른응답 칩 + 큰 음성 마이크 컴포저.
 * 목업과 달라진 점(서버 계약에 맞춤):
 *  - 사진 첨부 단계 없음 — Phase 0 슬롯 12개에 사진이 없다(신고 화면의 관심사).
 *  - 진행 도트 = 채워진 슬롯 수. 질문 순서를 서버가 정하므로 고정 단계가 아니다.
 *  - 빠른응답 칩은 회피 답변만 — 도메인 보기를 프론트가 지어내면 슬롯과 어긋난다.
 *  - 완료 요약 카드 없음 — RegDone 화면이 맡는다.
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
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Circle, Path } from 'react-native-svg';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import { color, radius, space, type } from '../theme/tokens';
import { hexToRgba } from '../utils/color';
import type { RootStackParamList } from '../navigation/types';

import ChatBubble from '../components/ChatBubble';
import QuickChips from '../components/QuickChips';
import ChatComposer from '../components/ChatComposer';
import CTAButton from '../components/CTAButton';

import { ApiError } from '../api/config';
import {
  answerInterview,
  listSlots,
  startInterview,
  type InterviewSession,
  type SlotInfo,
} from '../api/phase0';

const ACCENT = color.walk;
const AVATAR_GRADIENT = [color.walk, color.walkInk] as const;

/**
 * 인증 도입 전 임시 보호자 이름 — 세션 생성에만 쓰이고 페르소나에는 안 들어간다.
 * 로그인이 붙으면 계정 표시명으로 교체한다.
 */
const GUARDIAN_NAME = '보호자';

/**
 * 빠른응답 칩. **질문 내용을 프론트가 지어내지 않는다** — 어떤 슬롯을 묻는지는
 * 서버가 정하므로, 어느 질문에나 안전하게 쓸 수 있는 회피 답변만 둔다. 도메인
 * 보기를 여기 박으면 서버의 슬롯과 어긋나 엉뚱한 값이 추출된다.
 *
 * ⚠ **tier 1(필수) 슬롯에는 띄우지 않는다.** 성함·나이·거주지를 "잘 모르겠어요"로
 * 넘기면 페르소나가 성립하지 않는데, 칩이 있으면 누르게 된다. 서버는 필수 슬롯을
 * 다시 묻지만("죄송해요, 한 번만 더 여쭐게요") 턴만 낭비되고 등록은 진행되지 않는다.
 */
const SKIP_CHIPS = ['잘 모르겠어요', '없어요'];
/** 마지막 확인("이대로 등록할까요?") 단계 전용. */
const CONFIRM_CHIPS = ['네, 맞아요', '아니요, 수정할게요'];

/**
 * 서버 질문에 들어 있는 예시를 뽑는다 — "(예: 쉬지 않고 약 30분 걷습니다)" 형태.
 * 마이크 버튼이 이 값을 입력창에 채운다. **프론트가 예시를 지어내지 않는다**는
 * 원칙은 유지된다(문구의 출처가 서버 질문 자체다). 음성 인식이 붙기 전까지의
 * 입력 보조이고, 보호자는 그대로 보내지 않고 고쳐 쓰면 된다.
 */
function exampleFromQuestion(q: string | undefined): string {
  const m = q?.match(/\(예:\s*([^)]+)\)/);
  return m ? m[1].trim() : '';
}

type Msg = { id: string; from: 'bot' | 'user'; text: string; pending?: boolean };

/** AI 상담 아바타 — 그린 그라데이션 원 + 로봇 얼굴(목업 재현). */
function BotAvatar() {
  return (
    <LinearGradient
      colors={AVATAR_GRADIENT}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={styles.avatar}
    >
      <Svg width={22} height={22} viewBox="0 0 24 24">
        <Path d="M12 7c0-2.2-1.5-3.8-3.6-3.8C8.4 5.4 9.9 7 12 7Z" fill="#FFFFFF" opacity={0.92} />
        <Path d="M12 7c0-2.2 1.5-3.8 3.6-3.8C15.6 5.4 14.1 7 12 7Z" fill="#FFFFFF" opacity={0.92} />
        <Circle cx={9.6} cy={12.4} r={1.35} fill="#FFFFFF" />
        <Circle cx={14.4} cy={12.4} r={1.35} fill="#FFFFFF" />
        <Path
          d="M9.7 15.4c1.4 1.2 3.2 1.2 4.6 0"
          stroke="#FFFFFF"
          strokeWidth={1.6}
          fill="none"
          strokeLinecap="round"
        />
      </Svg>
    </LinearGradient>
  );
}

export default function RegChatScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();

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

  // 완료 → 서버가 페르소나를 만들고 persona_id 를 채운다. 그 ID 를 다음 단계
  // (신고·예측)로 넘겨야 하므로 요약을 화면 안에서 끝내지 않고 RegDone 으로 넘긴다.
  useEffect(() => {
    if (!session?.done || !session.persona_id) return;
    const raw = session.draft_fields as Record<string, unknown>;
    navigation.replace('RegDone', {
      personaId: session.persona_id,
      name: String(raw.name ?? ''),
      // 서버는 "78세" 처럼 단위가 붙은 문자열로 담는다 — 숫자만 뽑는다.
      age: Number(String(raw.age ?? '').replace(/[^0-9]/g, '')) || 0,
    });
  }, [session, navigation]);

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

  const onChipSelect = (chip: string) => submitAnswer(chip);

  const canGoBack = navigation.canGoBack();

  const totalSlots = slots.length;
  const filledCount = session?.filled_keys.length ?? 0;
  // 지금 묻고 있는 슬롯 — tier 1이면 회피 칩을 감춘다(위 SKIP_CHIPS 주석).
  const targetSlot = slots.find((s) => s.key === session?.prev_target_key);
  const chips = session?.awaiting_confirmation
    ? CONFIRM_CHIPS
    : targetSlot?.tier === 1
      ? []
      : SKIP_CHIPS;

  // 마이크가 채울 예시: 서버 질문에 예시가 섞여 오면 그것을, 없으면 슬롯 카탈로그의
  // answer_example 을 쓴다. Mi:dm 이 질문마다 예시를 붙이는지는 보장되지 않는다.
  const lastQuestion = [...(session?.messages ?? [])]
    .reverse()
    .find((m) => m.role === 'assistant')?.text;
  const example =
    exampleFromQuestion(lastQuestion) || (targetSlot?.answer_example ?? '');

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
                <Svg width={24} height={24} viewBox="0 0 24 24">
                  <Path
                    d="M15 5l-7 7 7 7"
                    stroke={color.text}
                    strokeWidth={2.2}
                    fill="none"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </Svg>
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
              가족 등록
            </Text>
            <View style={styles.headerSpacer} />
          </View>

          <View style={styles.progress} accessible accessibilityLabel={progressA11y}>
            {/* 도트 = 서버 슬롯. 어떤 순서로 물을지는 서버가 정하므로 "몇 개를
                채웠나"만 표시한다(프론트 단계 인덱스는 더 이상 진실이 아니다). */}
            <View style={styles.dotsRow}>
              {slots.map((s, i) => {
                if (i === filledCount) {
                  return (
                    <View key={s.key} style={styles.dotGlow}>
                      <View style={styles.dotActive} />
                    </View>
                  );
                }
                return (
                  <View
                    key={s.key}
                    style={[styles.dot, i < filledCount ? styles.dotDone : styles.dotFuture]}
                  />
                );
              })}
            </View>
            <Text
              style={styles.progressSub}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
            >
              {totalSlots
                ? `${filledCount}/${totalSlots} 항목 · 5분이면 끝나요`
                : '5분이면 끝나요'}
            </Text>
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
          {/* 안심 배너 */}
          <View
            style={styles.safeBanner}
            accessible
            accessibilityLabel="정보는 안전하게 보관되고, 발견 즉시 파기돼요"
          >
            <Text
              style={styles.safeBannerText}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
            >
              🔒 정보는 안전하게 보관되고, 발견 즉시 파기돼요
            </Text>
          </View>

          {messages.map((m) => {
            if (m.from === 'bot') {
              return (
                <View key={m.id} style={styles.botRow}>
                  <BotAvatar />
                  <View style={styles.botBubbleWrap}>
                    <ChatBubble from="bot" text={m.text} />
                  </View>
                </View>
              );
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
              <BotAvatar />
              <View style={styles.typingBubble}>
                <ActivityIndicator size="small" color={ACCENT} />
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
                <CTAButton label="다시 시도" onPress={begin} accent={ACCENT} />
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
                ⚠️ AI 응답이 불안정해 기본 질문으로 이어가고 있어요. 등록은 계속 진행됩니다.
              </Text>
            </View>
          ) : null}

          {/* 완료 요약은 RegDone 화면이 맡는다 — persona_id 를 다음 단계로
              넘겨야 해서 화면 안에서 끝내지 않고 전환한다(위 useEffect). */}
        </ScrollView>

        {/* 입력 영역 */}
        <View style={[styles.footer, { paddingBottom: insets.bottom + space.sm }]}>
          {chips.length > 0 ? (
            <View style={styles.chipsWrap}>
              <QuickChips
                chips={chips}
                onSelect={onChipSelect}
                accent={ACCENT}
                disabled={!session || !!pending}
              />
            </View>
          ) : null}
          <ChatComposer
            value={input}
            onChangeText={setInput}
            onSend={() => submitAnswer(input)}
            // 음성 인식 붙기 전까지 — 서버 질문에 담긴 예시를 입력창에 채운다.
            onVoice={example ? () => setInput(example) : undefined}
            placeholder={session ? '답변을 입력하거나 말해보세요' : '연결 중이에요…'}
            accent={ACCENT}
          />
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surface },
  flex: { flex: 1 },

  // 헤더
  header: {
    backgroundColor: color.surface,
    paddingHorizontal: space.md,
    paddingTop: space.sm,
    paddingBottom: space.md,
    borderBottomWidth: 1,
    borderBottomColor: color.border,
  },
  headerRow: { flexDirection: 'row', alignItems: 'center' },
  backBtn: {
    width: 42,
    height: 42,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerSpacer: { width: 42, height: 42 },
  title: {
    flex: 1,
    textAlign: 'center',
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    letterSpacing: -0.3,
  },
  progress: { alignItems: 'center', gap: space.sm, marginTop: space.sm },
  dotsRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  dot: { width: 9, height: 9, borderRadius: 4.5 },
  dotDone: { backgroundColor: color.walk },
  dotFuture: { backgroundColor: hexToRgba(color.textBody, 0.25) },
  dotGlow: {
    backgroundColor: color.walkWash,
    borderRadius: radius.pill,
    paddingHorizontal: 3,
    paddingVertical: 3,
  },
  dotActive: { width: 22, height: 9, borderRadius: radius.pill, backgroundColor: color.walk },
  progressSub: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
  },

  // 대화
  scroll: { flex: 1, backgroundColor: color.walkWash },
  chatContent: { paddingHorizontal: space.lg, paddingVertical: space.lg, gap: space.sm },

  safeBanner: {
    alignSelf: 'center',
    backgroundColor: color.surface,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: hexToRgba(color.walk, 0.35),
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    marginBottom: space.xs,
  },
  safeBannerText: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.walkInk,
    fontFamily: type.family,
    textAlign: 'center',
  },

  // 봇 말풍선(아바타 + ChatBubble)
  botRow: { flexDirection: 'row', alignItems: 'flex-end', gap: space.sm },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: color.walk,
    shadowOpacity: 0.34,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
  botBubbleWrap: { flex: 1 },

  // 사용자 말풍선(솔리드 그린)
  userRow: { flexDirection: 'row', justifyContent: 'flex-end' },
  userBubble: {
    maxWidth: '82%',
    backgroundColor: color.walk,
    borderRadius: radius.lg,
    borderBottomRightRadius: radius.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    shadowColor: color.walk,
    shadowOpacity: 0.28,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 3,
  },
  userText: {
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: '#FFFFFF',
    fontFamily: type.family,
    lineHeight: 22,
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
    fontFamily: type.family,
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
    fontFamily: type.family,
    lineHeight: 20,
  },

  // 입력 영역
  footer: {
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    borderTopWidth: 1,
    borderTopColor: color.border,
    backgroundColor: color.surface,
    gap: space.sm,
  },
  chipsWrap: { marginBottom: space.xs },

  pressed: { opacity: 0.6 },
});
