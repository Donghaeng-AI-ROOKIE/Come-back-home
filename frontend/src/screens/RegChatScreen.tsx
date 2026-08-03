/**
 * 등록 탭 (spec §3.4, reg-content). 라이트 · 산책 그린 톤.
 * 디지털 트윈 사전등록 챗봇 — 로컬 useState 대화 스크립트.
 *
 * 목업(reg-content.dc.html) 충실 재현:
 *  - 헤더: 뒤로 · 가운데 정렬 "가족 등록" · 진행 도트(현재 단계 알약 강조) · "N단계 · 5분이면 끝나요".
 *  - 그린 틴트 대화 배경 위 흰색 AI 말풍선(로봇 아바타) + 솔리드 그린 사용자 말풍선.
 *  - 상단 안심 배너("정보는 안전하게 보관되고, 발견 즉시 파기돼요 🔒").
 *  - 하단: 빠른응답 칩 + 큰 음성 마이크 컴포저.
 *  - 마지막 단계에서 최근 사진 첨부(실루엣 썸네일 + 파일명) → "등록 완료" 요약 카드.
 * 정정: 모드 전환·실종 발동 트리거 없음(평시 예방 등록). walk 그린 강조.
 */
import React, { useRef, useState } from 'react';
import {
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

const ACCENT = color.walk;
const AVATAR_GRADIENT = [color.walk, color.walkInk] as const;
const PHOTO_GRADIENT = [color.surfaceAlt, color.border] as const;

const PHOTO_CHIP = '📷 사진 올리기';
const PHOTO_FILENAME = '어머니_최근사진.jpg';

type StepKey = 'relation' | 'hometown' | 'place' | 'appearance' | 'cognition' | 'photo';

type Step = {
  key: StepKey;
  /** 요약 카드용 라벨. */
  label: string;
  question: string;
  chips: string[];
  /** 🎤 음성입력 시 채워지는 예시(데모 음성 인식 결과). */
  voiceExample: string;
  /** 사진 첨부 단계. */
  photo?: boolean;
};

const INTRO =
  '안녕하세요 🌿 가족을 미리 등록해 두면, 실종 시 훨씬 빨리 찾을 수 있어요. 천천히 답해 주세요.';

const STEPS: Step[] = [
  {
    key: 'relation',
    label: '관계',
    question: '먼저, 등록하실 분과 어떤 사이신가요?',
    chips: ['어머니', '아버지', '배우자', '조부모'],
    voiceExample: '어머니',
  },
  {
    key: 'hometown',
    label: '오래 사신 동네',
    question: '어머님이 오래 사신 동네가 있을까요? 30년 넘게 지내신 곳처럼요.',
    chips: [],
    voiceExample: '망원동',
  },
  {
    key: 'place',
    label: '자주 가시던 곳',
    question: '그 동네에서 자주 가시던 곳이 있나요? 시장이나 교회처럼요 🙂',
    chips: ['🛒 시장', '⛪ 교회', '🌳 공원', '잘 모르겠어요'],
    voiceExample: '망원시장에 매일 가셨어요',
  },
  {
    key: 'appearance',
    label: '인상착의',
    question: '요즘 즐겨 입으시는 옷차림이 궁금해요.',
    chips: ['회색 점퍼', '검은 바지', '지팡이'],
    voiceExample: '회색 점퍼에 검은 바지, 지팡이를 짚으세요',
  },
  {
    key: 'cognition',
    label: '인지 상태',
    question: '기억이나 길 찾기에 어려움이 있으세요?',
    chips: ['초기 치매', '중기 치매', '중증 치매', '해당 없음'],
    voiceExample: '중기 치매',
  },
  {
    key: 'photo',
    label: '최근 사진',
    question: '좋아요 🌿 마지막으로 어머님 최근 사진 한 장만 올려주시겠어요?',
    chips: [PHOTO_CHIP, '나중에 올릴게요'],
    voiceExample: '',
    photo: true,
  },
];

const OUTRO = '등록이 모두 끝났어요. 아래에서 등록 내용을 확인해 주세요.';

type Msg = { id: string; from: 'bot' | 'user'; text: string; photo?: boolean };

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

/** 사진 썸네일 실루엣(실 사진 미사용 — 개인정보 최소). */
function PhotoSilhouette() {
  return (
    <Svg width={50} height={50} viewBox="0 0 24 24">
      <Circle
        cx={12}
        cy={9}
        r={4}
        stroke={hexToRgba(color.textBody, 0.55)}
        strokeWidth={1.6}
        fill="none"
      />
      <Path
        d="M4.5 20c0-4.2 3.4-7 7.5-7s7.5 2.8 7.5 7"
        stroke={hexToRgba(color.textBody, 0.55)}
        strokeWidth={1.6}
        fill="none"
        strokeLinecap="round"
      />
    </Svg>
  );
}

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

  const submitAnswer = (raw: string, asPhoto = false) => {
    if (done) return;
    const answer = raw.trim();
    if (!answer && !asPhoto) return;

    const step = STEPS[stepIndex];
    const nextIndex = stepIndex + 1;
    const userMsg: Msg = asPhoto
      ? { id: nextId(), from: 'user', text: PHOTO_FILENAME, photo: true }
      : { id: nextId(), from: 'user', text: answer };
    const botMsg: Msg = {
      id: nextId(),
      from: 'bot',
      text: nextIndex < STEPS.length ? STEPS[nextIndex].question : OUTRO,
    };

    setAnswers((prev) => ({ ...prev, [step.key]: asPhoto ? '사진 등록됨' : answer }));
    setMessages((prev) => [...prev, userMsg, botMsg]);
    setStepIndex(nextIndex);
    setInput('');
  };

  const onChipSelect = (chip: string) => {
    if (!done && STEPS[stepIndex].photo && chip === PHOTO_CHIP) {
      submitAnswer('', true);
    } else {
      submitAnswer(chip);
    }
  };

  const restart = () => {
    idRef.current = 0;
    setMessages(initialMessages());
    setStepIndex(0);
    setAnswers({});
    setInput('');
  };

  const goHome = () => navigation.navigate('CitizenTabs', { screen: 'Home' });
  const canGoBack = navigation.canGoBack();

  const current = done ? undefined : STEPS[stepIndex];
  const totalSteps = STEPS.length;

  const progressA11y = done
    ? '등록 완료'
    : `${stepIndex + 1}단계, 총 ${totalSteps}단계. 5분이면 끝나요.`;

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
            <View style={styles.dotsRow}>
              {STEPS.map((s, i) => {
                const state = done || i < stepIndex ? 'done' : i === stepIndex ? 'active' : 'future';
                if (state === 'active') {
                  return (
                    <View key={s.key} style={styles.dotGlow}>
                      <View style={styles.dotActive} />
                    </View>
                  );
                }
                return (
                  <View
                    key={s.key}
                    style={[styles.dot, state === 'done' ? styles.dotDone : styles.dotFuture]}
                  />
                );
              })}
            </View>
            <Text
              style={styles.progressSub}
              allowFontScaling
              maxFontSizeMultiplier={type.maxScale}
            >
              {done ? '등록이 완료됐어요' : `${stepIndex + 1}단계 · 5분이면 끝나요`}
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
            if (m.photo) {
              return (
                <View key={m.id} style={styles.userRow}>
                  <View
                    style={styles.photoCard}
                    accessible
                    accessibilityLabel={`나. 최근 사진을 첨부했어요. ${m.text}`}
                  >
                    <LinearGradient
                      colors={PHOTO_GRADIENT}
                      start={{ x: 0, y: 0 }}
                      end={{ x: 1, y: 1 }}
                      style={styles.photoThumb}
                    >
                      <PhotoSilhouette />
                    </LinearGradient>
                    <View style={styles.photoCaption}>
                      <Text
                        style={styles.photoCaptionText}
                        allowFontScaling
                        maxFontSizeMultiplier={type.maxScale}
                        numberOfLines={1}
                      >
                        {m.text}
                      </Text>
                    </View>
                  </View>
                </View>
              );
            }
            return (
              <View key={m.id} style={styles.userRow}>
                <View style={styles.userBubble} accessible accessibilityLabel={`나. ${m.text}`}>
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

              <Text
                style={styles.summaryNote}
                allowFontScaling
                maxFontSizeMultiplier={type.maxScale}
              >
                등록 정보는 안전하게 보관되고, 실종경보가 연동될 때만 수색에 활용돼요.
              </Text>
            </View>
          ) : null}
        </ScrollView>

        {/* 입력 영역 */}
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
                  <QuickChips chips={current.chips} onSelect={onChipSelect} accent={ACCENT} />
                </View>
              ) : null}
              <ChatComposer
                value={input}
                onChangeText={setInput}
                onSend={() => submitAnswer(input)}
                onVoice={() => current && setInput(current.voiceExample)}
                placeholder="답변을 입력하거나 말해보세요"
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

  // 사진 첨부 버블
  photoCard: {
    width: 156,
    borderRadius: radius.lg,
    borderBottomRightRadius: radius.sm,
    borderWidth: 2,
    borderColor: color.walk,
    overflow: 'hidden',
    backgroundColor: color.surface,
    shadowColor: color.text,
    shadowOpacity: 0.14,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 5 },
    elevation: 4,
  },
  photoThumb: { height: 118, alignItems: 'center', justifyContent: 'center' },
  photoCaption: { backgroundColor: color.surface, paddingHorizontal: space.md, paddingVertical: space.sm },
  photoCaptionText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
  },

  // 요약 카드
  summaryCard: {
    marginTop: space.md,
    backgroundColor: color.surface,
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
    color: '#FFFFFF',
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
    width: 108,
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
  doneActions: { gap: space.sm },
  pressed: { opacity: 0.6 },
});
