/**
 * 제보 챗봇 (spec §3.4, CONTRACT screen #6). Root card, LIGHT, 앰버(수색) 강조.
 * 시간/위치/방향/인상착의를 ChatBubble + QuickChips + ChatComposer(음성)로 수집.
 * 마지막 전송 → submitTip(DEMO_CASE_ID, input) → 스피너 → replace('ReportDone', TipResult delta).
 * 앰버 강조 — 긴급(빨강) 아님. 죽은 버튼 없음: 칩·음성·전송 모두 실제 핸들러.
 */
import React, { useRef, useState } from 'react';
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
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import ChatBubble from '../components/ChatBubble';
import ChatComposer from '../components/ChatComposer';
import QuickChips from '../components/QuickChips';
import CTAButton from '../components/CTAButton';
import { DEMO_CASE_ID, MISSING_ANON } from '../data/missing';
import { submitTip } from '../api/client';
import type { TipInput } from '../types/domain';

// ── 대화 단계 ─────────────────────────────────────────
type CollectStep = 'time' | 'location' | 'direction' | 'appearance';
type Step = CollectStep | 'confirm';
type Answers = Partial<Record<CollectStep, string>>;
type Msg = { id: string; from: 'bot' | 'user'; text: string; time: string };

const COLLECT: CollectStep[] = ['time', 'location', 'direction', 'appearance'];

const STEP_LABEL: Record<CollectStep, string> = {
  time: '시간',
  location: '위치',
  direction: '방향',
  appearance: '인상착의',
};

const STEP_CFG: Record<CollectStep, { q: string; chips: string[]; ack: string }> = {
  time: {
    q: '어르신을 언제쯤 보셨나요?',
    chips: ['방금 전', '10분쯤 전', '30분쯤 전', '1시간 이상 전'],
    ack: '네, 목격하신 시각을 기록했어요.',
  },
  location: {
    q: '어디쯤에서 보셨나요? 아시는 만큼만 알려주세요.',
    chips: ['정릉천 산책로', '정릉시장 근처', '주민센터 앞', '잘 모르겠어요'],
    ack: '위치를 확인했어요.',
  },
  direction: {
    q: '어느 방향으로 가고 계셨나요?',
    chips: ['북한산 방향(북쪽)', '시장 방향(남쪽)', '천을 따라', '잘 모르겠어요'],
    ack: '이동 방향을 기록했어요.',
  },
  appearance: {
    q: '옷차림이나 특징이 기억나시나요?',
    chips: ['회색 점퍼', '검은 바지', '지팡이를 짚음', '기억이 안 나요'],
    ack: '인상착의를 확인했어요.',
  },
};

function clock(): string {
  const d = new Date();
  const ap = d.getHours() < 12 ? '오전' : '오후';
  let h = d.getHours() % 12;
  if (h === 0) h = 12;
  return `${ap} ${h}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function buildConfirm(a: Answers): string {
  const line = (label: string, v?: string) => `· ${label}: ${v ?? '—'}`;
  return [
    '말씀해주신 내용을 정리했어요.',
    line('시각', a.time),
    line('위치', a.location),
    line('방향', a.direction),
    line('인상착의', a.appearance),
    '아래 “제보 전송하기”를 누르면 수색팀에 바로 전달돼요. 익명으로 전달되니 안심하세요.',
  ].join('\n');
}

export default function ReportChatScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();

  const idRef = useRef(2);
  const nextId = () => `m${idRef.current++}`;

  const [messages, setMessages] = useState<Msg[]>(() => [
    { id: 'm0', from: 'bot', text: `${MISSING_ANON}를 보셨군요. 제보해 주셔서 정말 고마워요. 몇 가지만 여쭤볼게요.`, time: clock() },
    { id: 'm1', from: 'bot', text: STEP_CFG.time.q, time: clock() },
  ]);
  const [step, setStep] = useState<Step>('time');
  const [answers, setAnswers] = useState<Answers>({});
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);

  const scrollRef = useRef<ScrollView>(null);
  const currentIndex = step === 'confirm' ? COLLECT.length : COLLECT.indexOf(step);

  const submitAnswer = (raw: string) => {
    const answer = raw.trim();
    if (!answer || sending) return;

    if (step === 'confirm') {
      setMessages((prev) => [
        ...prev,
        { id: nextId(), from: 'user', text: answer, time: clock() },
        { id: nextId(), from: 'bot', text: '네, 참고해서 함께 전달할게요.', time: clock() },
      ]);
      return;
    }

    const nextAnswers: Answers = { ...answers, [step]: answer };
    setAnswers(nextAnswers);

    const idx = COLLECT.indexOf(step);
    const next = COLLECT[idx + 1];
    const additions: Msg[] = [
      { id: nextId(), from: 'user', text: answer, time: clock() },
      { id: nextId(), from: 'bot', text: STEP_CFG[step].ack, time: clock() },
    ];
    if (next) {
      additions.push({ id: nextId(), from: 'bot', text: STEP_CFG[next].q, time: clock() });
      setStep(next);
    } else {
      additions.push({ id: nextId(), from: 'bot', text: buildConfirm(nextAnswers), time: clock() });
      setStep('confirm');
    }
    setMessages((prev) => [...prev, ...additions]);
  };

  const onComposerSend = () => {
    submitAnswer(input);
    setInput('');
  };

  const onVoice = () => {
    if (step === 'confirm') {
      setInput('네, 이대로 전송할게요');
      return;
    }
    // 데모: 음성 인식 결과를 입력창에 채워 넣음(실제 핸들러).
    setInput(STEP_CFG[step].chips[0]);
  };

  const onSubmitTip = async () => {
    if (sending) return;
    setSending(true);
    const text =
      [
        answers.time && `목격 시각: ${answers.time}`,
        answers.location && `위치: ${answers.location}`,
        answers.direction && `이동 방향: ${answers.direction}`,
        answers.appearance && `인상착의: ${answers.appearance}`,
      ]
        .filter((s): s is string => !!s)
        .join(' / ') || '목격 제보';
    const tipInput: TipInput = {
      text,
      seenAt: answers.time,
      direction: answers.direction,
      hasPhoto: false,
    };
    try {
      const result = await submitTip(DEMO_CASE_ID, tipInput);
      navigation.replace('ReportDone', {
        caseId: DEMO_CASE_ID,
        beforeAreaKm2: result.beforeAreaKm2,
        afterAreaKm2: result.afterAreaKm2,
        deltaPct: result.deltaPct,
      });
    } catch {
      setSending(false);
      setMessages((prev) => [
        ...prev,
        { id: nextId(), from: 'bot', text: '연결이 불안정해요. 잠시 후 다시 보내주세요.', time: clock() },
      ]);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="dark" />

      {/* 헤더 */}
      <View style={styles.header}>
        <Pressable
          onPress={() => navigation.goBack()}
          accessibilityRole="button"
          accessibilityLabel="뒤로"
          hitSlop={12}
          style={({ pressed }) => [styles.back, pressed && styles.pressed]}
        >
          <Text style={styles.backIcon} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            ‹
          </Text>
        </Pressable>
        <View style={styles.headerText}>
          <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
            봤어요 · 제보하기
          </Text>
          <Text style={styles.subtitle} allowFontScaling maxFontSizeMultiplier={type.maxScale} numberOfLines={1}>
            {MISSING_ANON}를 보신 곳을 알려주세요
          </Text>
        </View>
      </View>

      {/* 진행 단계 */}
      <View
        style={styles.stepper}
        accessibilityRole="text"
        accessibilityLabel={`제보 단계 ${Math.min(currentIndex + 1, COLLECT.length)} / ${COLLECT.length}`}
      >
        {COLLECT.map((s, i) => {
          const on = i <= currentIndex;
          const active = i === currentIndex;
          return (
            <View key={s} style={styles.stepItem}>
              <View style={[styles.stepDot, { backgroundColor: on ? color.search : color.border }]} />
              <Text
                style={[
                  styles.stepLabel,
                  { color: on ? color.searchInk : color.textCaption, fontWeight: active ? type.weight.black : type.weight.medium },
                ]}
                allowFontScaling
                maxFontSizeMultiplier={type.maxScale}
                numberOfLines={1}
              >
                {STEP_LABEL[s]}
              </Text>
            </View>
          );
        })}
      </View>

      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          ref={scrollRef}
          style={styles.flex}
          contentContainerStyle={styles.messages}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
          keyboardShouldPersistTaps="handled"
        >
          {messages.map((m) => (
            <ChatBubble key={m.id} from={m.from} text={m.text} time={m.time} />
          ))}
        </ScrollView>

        {/* 빠른 답변 / 전송 */}
        <View style={styles.footer}>
          {step !== 'confirm' ? (
            <View style={styles.chipsWrap}>
              <Text style={styles.quickLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                빠른 답변
              </Text>
              <QuickChips chips={STEP_CFG[step].chips} onSelect={submitAnswer} accent={color.search} disabled={sending} />
            </View>
          ) : (
            <CTAButton
              label="제보 전송하기"
              onPress={onSubmitTip}
              accent={color.search}
              loading={sending}
              accessibilityHint="수집한 내용을 수색팀에 익명으로 전달합니다"
              style={styles.sendCta}
            />
          )}

          <ChatComposer
            value={input}
            onChangeText={setInput}
            onSend={onComposerSend}
            onVoice={onVoice}
            placeholder="직접 입력하거나 마이크로 말해보세요"
            accent={color.search}
          />
        </View>
      </KeyboardAvoidingView>

      {/* 전송 중 오버레이 */}
      {sending ? (
        <View style={styles.overlay} accessibilityLiveRegion="assertive" accessibilityRole="alert" accessibilityLabel="제보를 전달하고 있어요">
          <View style={styles.overlayCard}>
            <ActivityIndicator size="large" color={color.search} />
            <Text style={styles.overlayText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              제보를 전달하고 있어요
            </Text>
          </View>
        </View>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surface },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.md,
    paddingBottom: space.sm,
    gap: space.sm,
  },
  back: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: color.surfaceAlt,
  },
  backIcon: { fontSize: 30, lineHeight: 32, color: color.text, fontFamily: type.family },
  headerText: { flex: 1 },
  title: { fontSize: type.size.title, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  subtitle: { marginTop: 2, fontSize: type.size.label, fontWeight: type.weight.medium, color: color.textBody, fontFamily: type.family },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    backgroundColor: color.searchWash,
  },
  stepItem: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  stepDot: { width: 9, height: 9, borderRadius: 5 },
  stepLabel: { fontSize: type.size.caption, fontFamily: type.family },
  messages: { padding: space.lg, paddingBottom: space.xl, gap: space.xs },
  footer: {
    borderTopWidth: 1,
    borderTopColor: color.border,
    backgroundColor: color.surface,
  },
  chipsWrap: { paddingHorizontal: space.lg, paddingTop: space.md, paddingBottom: space.sm, gap: space.sm },
  quickLabel: { fontSize: type.size.caption, fontWeight: type.weight.bold, color: color.textCaption, fontFamily: type.family },
  sendCta: { marginHorizontal: space.lg, marginTop: space.md, marginBottom: space.sm },
  pressed: { opacity: 0.7 },
  overlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(20,22,28,0.45)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
  },
  overlayCard: {
    backgroundColor: color.surface,
    borderRadius: radius.xl,
    paddingVertical: space.xl,
    paddingHorizontal: space.xxl,
    alignItems: 'center',
    gap: space.md,
  },
  overlayText: { fontSize: type.size.cardTitle, fontWeight: type.weight.bold, color: color.text, fontFamily: type.family },
});
