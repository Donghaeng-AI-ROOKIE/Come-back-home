/**
 * 등록 탭 (spec §3.4, reg-content). 라이트 · 산책 그린 톤.
 * 디지털 트윈 사전등록 챗봇 — 로컬 useState 대화 스크립트.
 * ChatBubble 목록 + QuickChips(빠른 응답) + ChatComposer(음성입력).
 * 봇이 성함·관계·연세·자주 다니는 곳·인상착의·인지 상태를 차례로 묻고,
 * 사용자가 칩 또는 입력으로 답하면 다음 질문으로 진행 → 마지막에 "등록 완료" 요약 카드.
 * 모드 전환·실종 발동 트리거 없음(평시 예방 등록).
 */
import React, { useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import { color, radius, space, type } from '../theme/tokens';
import type { RootStackParamList } from '../navigation/types';

import ChatBubble from '../components/ChatBubble';
import QuickChips from '../components/QuickChips';
import ChatComposer from '../components/ChatComposer';
import CTAButton from '../components/CTAButton';

const ACCENT = color.walk;

type StepKey = 'name' | 'relation' | 'age' | 'place' | 'appearance' | 'cognition';

type Step = {
  key: StepKey;
  /** 요약 카드용 라벨. */
  label: string;
  question: string;
  chips: string[];
  /** 🎤 음성입력 시 채워지는 예시(데모 음성 인식 결과). */
  voiceExample: string;
};

const INTRO =
  '안녕하세요. 가족을 미리 등록해 두면 실종 시 더 빨리 찾을 수 있어요. 천천히 답해 주시면 돼요.';

const STEPS: Step[] = [
  {
    key: 'name',
    label: '성함',
    question: '먼저, 등록하실 어르신의 성함을 알려주세요.',
    chips: [],
    voiceExample: '김순자',
  },
  {
    key: 'relation',
    label: '관계',
    question: '나와 어떤 관계이신가요?',
    chips: ['어머니', '아버지', '배우자', '조부모'],
    voiceExample: '어머니',
  },
  {
    key: 'age',
    label: '연세',
    question: '연세가 어떻게 되세요?',
    chips: ['70대', '80대', '90대'],
    voiceExample: '78세',
  },
  {
    key: 'place',
    label: '자주 가시는 곳',
    question: '평소 자주 다니시는 곳이 있나요?',
    chips: ['정릉천 산책로', '정릉시장', '주민센터'],
    voiceExample: '정릉천 산책로',
  },
  {
    key: 'appearance',
    label: '인상착의',
    question: '요즘 자주 입으시는 옷차림이 궁금해요.',
    chips: ['회색 점퍼', '검은 바지', '지팡이'],
    voiceExample: '회색 점퍼에 검은 바지, 지팡이를 짚으세요',
  },
  {
    key: 'cognition',
    label: '인지 상태',
    question: '기억이나 길 찾기에 어려움이 있으세요?',
    chips: ['초기 치매', '중기 치매', '발달장애', '해당 없음'],
    voiceExample: '중기 치매',
  },
];

const OUTRO = '등록이 모두 끝났어요. 아래에서 등록 내용을 확인해 주세요.';

type Msg = { id: string; from: 'bot' | 'user'; text: string };

export default function RegChatScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();

  const idRef = useRef(0);
  const nextId = () => `m${idRef.current++}`;

  const initialMessages = (): Msg[] => [
    { id: nextId(), from: 'bot', text: INTRO },
    { id: nextId(), from: 'bot', text: STEPS[0].question },
  ];

  const [messages, setMessages] = useState<Msg[]>(initialMessages);
  const [stepIndex, setStepIndex] = useState(0);
  const [answers, setAnswers] = useState<Partial<Record<StepKey, string>>>({});
  const [input, setInput] = useState('');
  const done = stepIndex >= STEPS.length;

  const scrollRef = useRef<ScrollView>(null);

  const submitAnswer = (raw: string) => {
    const answer = raw.trim();
    if (!answer || done) return;

    const step = STEPS[stepIndex];
    const nextIndex = stepIndex + 1;
    const userMsg: Msg = { id: nextId(), from: 'user', text: answer };
    const botMsg: Msg = {
      id: nextId(),
      from: 'bot',
      text: nextIndex < STEPS.length ? STEPS[nextIndex].question : OUTRO,
    };

    setAnswers((prev) => ({ ...prev, [step.key]: answer }));
    setMessages((prev) => [...prev, userMsg, botMsg]);
    setStepIndex(nextIndex);
    setInput('');
  };

  const restart = () => {
    idRef.current = 0;
    setMessages(initialMessages());
    setStepIndex(0);
    setAnswers({});
    setInput('');
  };

  const goHome = () => navigation.navigate('CitizenTabs', { screen: 'Home' });

  const current = done ? undefined : STEPS[stepIndex];
  const progressLabel = done ? '등록 완료' : `${Math.min(stepIndex + 1, STEPS.length)} / ${STEPS.length}단계`;

  const summaryA11y = done
    ? '사전 등록 완료. ' +
      STEPS.map((s) => `${s.label} ${answers[s.key] ?? '미입력'}`).join(', ') +
      '.'
    : undefined;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={styles.header}>
          <View style={styles.headerRow}>
            <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              가족 예방 등록
            </Text>
            <View style={styles.progressPill}>
              <Text
                style={styles.progressText}
                allowFontScaling
                maxFontSizeMultiplier={type.maxScale}
                numberOfLines={1}
              >
                {progressLabel}
              </Text>
            </View>
          </View>
          <Text style={styles.subtitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            미리 등록해 두면 실종 시 더 빨리 도울 수 있어요.
          </Text>
        </View>

        <ScrollView
          ref={scrollRef}
          style={styles.flex}
          contentContainerStyle={styles.chatContent}
          showsVerticalScrollIndicator={false}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
        >
          {messages.map((m) => (
            <ChatBubble key={m.id} from={m.from} text={m.text} />
          ))}

          {done ? (
            <View style={styles.summaryCard} accessible accessibilityLabel={summaryA11y}>
              <View style={styles.summaryHead}>
                <View style={styles.checkCircle}>
                  <Text
                    style={styles.checkGlyph}
                    allowFontScaling
                    maxFontSizeMultiplier={type.maxScale}
                  >
                    ✓
                  </Text>
                </View>
                <Text
                  style={styles.summaryTitle}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  등록 완료
                </Text>
              </View>

              {STEPS.map((s) => (
                <View key={s.key} style={styles.summaryRow}>
                  <Text
                    style={styles.summaryLabel}
                    allowFontScaling
                    maxFontSizeMultiplier={type.maxScale}
                  >
                    {s.label}
                  </Text>
                  <Text
                    style={styles.summaryValue}
                    allowFontScaling
                    maxFontSizeMultiplier={type.maxScale}
                    numberOfLines={2}
                  >
                    {answers[s.key] ?? '—'}
                  </Text>
                </View>
              ))}

              <Text style={styles.summaryNote} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                등록 정보는 안전하게 보관되고, 실종경보가 연동될 때만 수색에 활용돼요.
              </Text>
            </View>
          ) : null}
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: insets.bottom + space.sm }]}>
          {done ? (
            <View style={styles.doneActions}>
              <CTAButton label="완료 · 홈으로" onPress={goHome} accent={ACCENT} />
              <CTAButton
                label="다시 등록하기"
                onPress={restart}
                variant="ghost"
                accessibilityHint="처음부터 다시 등록해요"
              />
            </View>
          ) : (
            <>
              {current && current.chips.length > 0 ? (
                <View style={styles.chipsWrap}>
                  <QuickChips chips={current.chips} onSelect={submitAnswer} accent={ACCENT} />
                </View>
              ) : null}
              <ChatComposer
                value={input}
                onChangeText={setInput}
                onSend={() => submitAnswer(input)}
                onVoice={() => current && setInput(current.voiceExample)}
                placeholder="답변을 입력하거나 🎤 로 말해 보세요"
                accent={ACCENT}
              />
            </>
          )}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surface },
  flex: { flex: 1 },
  header: {
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.md,
    borderBottomWidth: 1,
    borderBottomColor: color.border,
    gap: space.xs,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.sm,
  },
  title: {
    fontSize: type.size.title,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },
  progressPill: {
    backgroundColor: color.walkWash,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
  progressText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.black,
    color: color.walkInk,
    fontFamily: type.family,
  },
  subtitle: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
    lineHeight: 22,
  },
  chatContent: {
    paddingHorizontal: space.lg,
    paddingVertical: space.lg,
    gap: space.xs,
  },
  summaryCard: {
    marginTop: space.lg,
    backgroundColor: color.walkWash,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.walk,
    padding: space.lg,
    gap: space.sm,
  },
  summaryHead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    marginBottom: space.sm,
  },
  checkCircle: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: color.walk,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkGlyph: {
    fontSize: 22,
    fontWeight: type.weight.black,
    color: color.surface,
    fontFamily: type.family,
  },
  summaryTitle: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.walkInk,
    fontFamily: type.family,
  },
  summaryRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: space.xs,
    gap: space.md,
  },
  summaryLabel: {
    width: 96,
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
  },
  summaryValue: {
    flex: 1,
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },
  summaryNote: {
    marginTop: space.sm,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textBody,
    fontFamily: type.family,
    lineHeight: 20,
  },
  footer: {
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    borderTopWidth: 1,
    borderTopColor: color.border,
    backgroundColor: color.surface,
    gap: space.sm,
  },
  chipsWrap: { marginBottom: space.xs },
  doneActions: { gap: space.sm },
});
