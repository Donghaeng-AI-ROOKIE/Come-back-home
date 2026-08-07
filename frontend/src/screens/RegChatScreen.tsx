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
import { SvgXml } from 'react-native-svg';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import { color, radius, space, type } from '../theme/tokens';
import { gColor } from '../theme/guardianTokens';
import { hexToRgba } from '../utils/color';
import type { RootStackParamList } from '../navigation/types';

import { icBackXml } from '../assets/guardianSvg';
import ChatBubble from '../components/ChatBubble';
import QuickChips from '../components/QuickChips';
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

const ACCENT = gColor.progressGreen;

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

export default function RegChatScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
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
        navigation.replace('RegDone', {
          personaId: persona.id, name: persona.name, age: persona.age,
        });
      } catch (e) {
        if (cancelled) return;
        // 등록 자체는 성공했다 — 조회만 실패했으므로 진행은 시킨다.
        setError(e instanceof ApiError ? e.message : String(e));
        navigation.replace('RegDone', {
          personaId: session.persona_id!, name: '', age: 0,
        });
      }
    })();
    return () => { cancelled = true; };
  }, [session, navigation, setPersona]);

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
              return <ChatBubble key={m.id} from="bot" text={m.text} bg={botBubbleBg} />;
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
                accent={accent}
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
            accent={accent}
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
  progress: { gap: space.sm, marginTop: space.sm },
  progressTrack: {
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: gColor.track,
    overflow: 'hidden',
  },
  progressFill: {
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: gColor.progressGreen,
  },
  progressSub: {
    textAlign: 'center',
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
  },

  // 대화 — 피그마: 흰 배경 위 그린/그레이 말풍선
  scroll: { flex: 1, backgroundColor: gColor.surface },
  chatContent: { paddingHorizontal: space.lg, paddingVertical: space.lg, gap: space.sm },

  safeBanner: {
    alignSelf: 'center',
    backgroundColor: gColor.surface,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: hexToRgba(gColor.progressGreen, 0.35),
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    marginBottom: space.xs,
  },
  safeBannerText: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: gColor.progressGreen,
    fontFamily: type.family,
    textAlign: 'center',
  },

  // 봇 말풍선 행 (타이핑 표시용)
  botRow: { flexDirection: 'row', alignItems: 'flex-end', gap: space.sm },

  // 사용자 말풍선 — 피그마: #EDEDED 플랫, 검정 글자
  userRow: { flexDirection: 'row', justifyContent: 'flex-end' },
  userBubble: {
    maxWidth: '82%',
    backgroundColor: gColor.bubbleUser,
    borderRadius: radius.md,
    borderTopRightRadius: radius.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  userText: {
    fontSize: type.size.body,
    fontWeight: type.weight.medium,
    color: color.text,
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
