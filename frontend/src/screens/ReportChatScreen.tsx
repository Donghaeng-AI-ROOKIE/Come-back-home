/**
 * 제보 챗봇 (spec §3.4, CONTRACT screen #6). Root card · LIGHT · 앰버(수색) 강조.
 * report-content.dc.html 목업 고충실 이식: 4단계 진행바 · 안심 배너 · 그라데이션
 * 아바타 봇 말풍선(꼬리) · 솔리드 앰버 유저 말풍선 · 위치 첨부 칩 · "지금까지 이해한
 * 내용" 요약 카드(수정/되돌리기) · 가로 빠른선택 칩 · 마이크/전송 앰버 원형 입력바.
 *
 * 수집 단계: 시간 → 위치 → 방향 → 인상착의 → 확인.
 * 최종 전송 → submitTip(DEMO_CASE_ID, input) → 스피너 → replace('ReportDone', TipResult delta).
 * 앰버 강조(수색) — 긴급 빨강 아님. 죽은 버튼 없음: 칩·음성·첨부·전송 모두 실제 핸들러.
 * 목업의 장식용 색은 토큰(color.search/searchInk/searchWash…)으로 매핑.
 */
import React, { useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import type { ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Circle, Path, Rect } from 'react-native-svg';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import { hexToRgba } from '../utils/color';
import CTAButton from '../components/CTAButton';
import { DEMO_CASE_ID, MISSING_ANON, LAST_SEEN } from '../data/missing';
import { submitTip } from '../api/client';
import type { TipInput } from '../types/domain';

const WHITE = color.surface;
const ACCENT = color.search;
const INK = color.searchInk;
const AVATAR_GRADIENT = [color.search, color.searchInk] as const;

// ── 대화 단계 ─────────────────────────────────────────
type CollectStep = 'time' | 'location' | 'direction' | 'appearance';
type Step = CollectStep | 'confirm';
type Answers = Partial<Record<CollectStep, string>>;
type Msg =
  | { id: string; kind: 'bot'; text: string }
  | { id: string; kind: 'user'; text: string; location?: string };

const COLLECT: CollectStep[] = ['time', 'location', 'direction', 'appearance'];

const STEP_LONG: Record<Step, string> = {
  time: '목격 시각',
  location: '목격 위치',
  direction: '이동 방향',
  appearance: '인상착의',
  confirm: '내용 확인',
};

const SUMMARY_LABEL: Record<CollectStep, string> = {
  time: '시간',
  location: '위치',
  direction: '방향',
  appearance: '인상착의',
};

const STEP_CFG: Record<CollectStep, { q: string; chips: string[]; ack: string }> = {
  time: {
    q: '어르신을 언제쯤 보셨어요?',
    chips: ['방금 전', '10분쯤 전', '30분쯤 전', '1시간 이상 전', '잘 모르겠어요'],
    ack: '네, 목격 시각을 기록했어요.',
  },
  location: {
    q: '어디서 보셨는지 알려주시겠어요? 위치를 첨부하셔도 좋아요',
    chips: ['정릉천 산책로', '정릉시장 근처', '주민센터 앞', '잘 모르겠어요'],
    ack: '위치를 확인했어요.',
  },
  direction: {
    q: '어느 쪽으로 가시는 것 같았어요? 대략이라도 괜찮아요',
    chips: ['⬆ 북쪽', '⬇ 남쪽', '➡ 동쪽', '⬅ 서쪽', '잘 모르겠어요'],
    ack: '이동 방향을 기록했어요.',
  },
  appearance: {
    q: '옷차림이나 특징이 기억나시나요? 생각나는 만큼만요',
    chips: ['회색 점퍼', '검은 바지', '지팡이를 짚음', '기억이 안 나요'],
    ack: '인상착의를 확인했어요. 큰 도움이 됩니다.',
  },
};

const INTRO = `${MISSING_ANON}를 보셨군요. 제보해 주셔서 정말 고마워요. 몇 가지만 여쭤볼게요.`;
const CLOSING = '말씀 고맙습니다. 아래 내용을 확인하고 전송해 주세요.';
const LOC_CHIP = '위치 첨부됨 · 정릉동';

function isDontKnow(chip: string): boolean {
  return chip.includes('모르') || chip.includes('기억이 안');
}

/** answers + step 으로부터 대화 메시지를 순수 함수로 파생 — 수정/되돌리기가 간단·결정적. */
function deriveMessages(answers: Answers, step: Step, locationAttached: boolean): Msg[] {
  const out: Msg[] = [{ id: 'intro', kind: 'bot', text: INTRO }];
  const upto = step === 'confirm' ? COLLECT.length - 1 : COLLECT.indexOf(step);
  for (let i = 0; i <= upto; i++) {
    const s = COLLECT[i];
    out.push({ id: `q-${s}`, kind: 'bot', text: STEP_CFG[s].q });
    const ans = answers[s];
    if (ans !== undefined) {
      out.push({
        id: `a-${s}`,
        kind: 'user',
        text: ans,
        location: s === 'location' && locationAttached ? LOC_CHIP : undefined,
      });
      out.push({ id: `ack-${s}`, kind: 'bot', text: STEP_CFG[s].ack });
    }
  }
  if (step === 'confirm') out.push({ id: 'closing', kind: 'bot', text: CLOSING });
  return out;
}

// ── 아이콘 (react-native-svg, 목업 라인 아이콘 재현) ───────────
type IconProps = { size?: number; stroke?: string };

function BotAvatar() {
  return (
    <LinearGradient
      colors={AVATAR_GRADIENT}
      start={{ x: 0.15, y: 0 }}
      end={{ x: 0.85, y: 1 }}
      style={styles.avatar}
    >
      <Svg width={22} height={22} viewBox="0 0 24 24">
        <Circle cx={9.6} cy={12.4} r={1.35} fill={WHITE} />
        <Circle cx={14.4} cy={12.4} r={1.35} fill={WHITE} />
        <Path d="M9.7 15.4c1.4 1.2 3.2 1.2 4.6 0" stroke={WHITE} strokeWidth={1.6} fill="none" strokeLinecap="round" />
        <Path d="M7.5 7.5 9 6M16.5 7.5 15 6" stroke={WHITE} strokeWidth={1.6} strokeLinecap="round" />
      </Svg>
    </LinearGradient>
  );
}

function ChevronLeftIcon({ size = 24, stroke = color.text }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path d="M15 5l-7 7 7 7" stroke={stroke} strokeWidth={2.2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

function MicIcon({ size = 27, stroke = WHITE }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Rect x={9} y={3} width={6} height={11} rx={3} stroke={stroke} strokeWidth={2} fill="none" />
      <Path d="M5.5 11a6.5 6.5 0 0 0 13 0" stroke={stroke} strokeWidth={2} fill="none" strokeLinecap="round" />
      <Path d="M12 17.5V21" stroke={stroke} strokeWidth={2} strokeLinecap="round" />
    </Svg>
  );
}

function SendUpIcon({ size = 23, stroke = WHITE }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path d="M12 19V6M6 12l6-6 6 6" stroke={stroke} strokeWidth={2.2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

function PinIcon({ size = 16, stroke = INK }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path d="M12 21s6.5-5.6 6.5-10.5a6.5 6.5 0 0 0-13 0C5.5 15.4 12 21 12 21Z" stroke={stroke} strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <Circle cx={12} cy={10.5} r={2.3} stroke={stroke} strokeWidth={2} fill="none" />
    </Svg>
  );
}

function PhotoIcon({ size = 22, stroke = color.textCaption }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Rect x={3} y={6.5} width={18} height={13} rx={3} stroke={stroke} strokeWidth={1.9} fill="none" />
      <Circle cx={12} cy={13} r={3.2} stroke={stroke} strokeWidth={1.9} fill="none" />
      <Path d="M8 6.5l1.4-2.2h5.2L16 6.5" stroke={stroke} strokeWidth={1.9} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

function CheckBadgeIcon({ size = 18, stroke = INK }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Rect x={3.5} y={3.5} width={17} height={17} rx={5} stroke={stroke} strokeWidth={2} fill="none" />
      <Path d="M9 11l2.5 2.5L16 8" stroke={stroke} strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

function EditIcon({ size = 15, stroke = color.textCaption }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path d="M4 20l4-1 10-10-3-3L5 16z" stroke={stroke} strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M13.5 6.5l3 3" stroke={stroke} strokeWidth={2} strokeLinecap="round" />
    </Svg>
  );
}

function UndoIcon({ size = 15, stroke = color.textCaption }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path d="M9 5 4 10l5 5" stroke={stroke} strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M4 10h11a5 5 0 0 1 0 10h-2" stroke={stroke} strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export default function ReportChatScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();

  const [step, setStep] = useState<Step>('time');
  const [answers, setAnswers] = useState<Answers>({});
  const [input, setInput] = useState('');
  const [locationAttached, setLocationAttached] = useState(false);
  const [hasPhoto, setHasPhoto] = useState(false);
  const [sending, setSending] = useState(false);

  const scrollRef = useRef<ScrollView>(null);

  const messages = useMemo(
    () => deriveMessages(answers, step, locationAttached),
    [answers, step, locationAttached],
  );

  const answeredSteps = COLLECT.filter((s) => answers[s] !== undefined);
  const answeredCount = answeredSteps.length;
  const activeIdx = step === 'confirm' ? COLLECT.length : COLLECT.indexOf(step);
  const stepNumber = step === 'confirm' ? COLLECT.length : activeIdx + 1;

  // ── 핸들러 ────────────────────────────────────────
  const submitAnswer = (raw: string, opts?: { location?: boolean }) => {
    const answer = raw.trim();
    if (!answer || sending || step === 'confirm') return;
    if (opts?.location) setLocationAttached(true);
    const idx = COLLECT.indexOf(step);
    const next = COLLECT[idx + 1];
    setAnswers((prev) => ({ ...prev, [step]: answer }));
    setStep(next ?? 'confirm');
    setInput('');
  };

  const onComposerSend = () => submitAnswer(input);

  const onVoice = () => {
    if (step === 'confirm') return;
    // 데모: 음성 인식 결과를 입력창에 채워 넣음(실제 핸들러).
    setInput(STEP_CFG[step].chips[0]);
  };

  const onAttachLocation = () => {
    if (step === 'location') {
      submitAnswer('정릉동 주민센터 앞', { location: true });
    } else {
      setLocationAttached(true);
    }
  };

  const onAttachPhoto = () => setHasPhoto(true);

  const onEdit = () => {
    setAnswers({});
    setStep('time');
    setLocationAttached(false);
    setHasPhoto(false);
    setInput('');
  };

  const onUndo = () => {
    if (answeredSteps.length === 0) return;
    const last = answeredSteps[answeredSteps.length - 1];
    setAnswers((prev) => {
      const na = { ...prev };
      delete na[last];
      return na;
    });
    setStep(last);
    if (last === 'location') setLocationAttached(false);
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
      location: locationAttached ? LAST_SEEN : undefined,
      hasPhoto,
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
    }
  };

  // ── 렌더 ─────────────────────────────────────────
  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="dark" />

      {/* 헤더 + 4단계 진행바 */}
      <View style={styles.header}>
        <View style={styles.headerRow}>
          <Pressable
            onPress={() => navigation.goBack()}
            accessibilityRole="button"
            accessibilityLabel="뒤로"
            hitSlop={12}
            style={({ pressed }) => [styles.back, pressed && styles.pressed]}
          >
            <ChevronLeftIcon />
          </Pressable>
          <Text
            style={styles.title}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
            numberOfLines={1}
          >
            제보하기
          </Text>
          <View style={styles.back} />
        </View>

        <View
          style={styles.stepper}
          accessibilityRole="progressbar"
          accessibilityLabel={`${COLLECT.length}단계 중 ${stepNumber}단계 · ${STEP_LONG[step]}`}
        >
          <View style={styles.segRow}>
            {COLLECT.map((s, i) => {
              const done = i < activeIdx;
              const active = i === activeIdx && step !== 'confirm';
              if (done) return <View key={s} style={styles.segDone} />;
              if (active)
                return (
                  <View key={s} style={styles.segActiveHalo}>
                    <View style={styles.segDone} />
                  </View>
                );
              return <View key={s} style={styles.segTodo} />;
            })}
          </View>
          <Text
            style={styles.stepMeta}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
          >
            {`${COLLECT.length}단계 중 ${stepNumber}단계 · ${STEP_LONG[step]}`}
          </Text>
        </View>
      </View>

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          ref={scrollRef}
          style={styles.chat}
          contentContainerStyle={styles.chatContent}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* 안심 배너 */}
          <View style={styles.reassure} accessibilityRole="text" accessibilityLabel="편하게 말씀만 주세요. 정리는 제가 할게요.">
            <PinIcon size={15} />
            <Text style={styles.reassureText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              편하게 말씀만 주세요. 정리는 제가 할게요 🙂
            </Text>
          </View>

          {messages.map((m) =>
            m.kind === 'bot' ? (
              <View
                key={m.id}
                style={styles.botRow}
                accessible
                accessibilityLabel={`상담원. ${m.text}`}
              >
                <BotAvatar />
                <View style={styles.botBubble}>
                  <Text style={styles.botText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    {m.text}
                  </Text>
                </View>
              </View>
            ) : (
              <View
                key={m.id}
                style={styles.userCol}
                accessible
                accessibilityLabel={`나. ${m.text}${m.location ? `. ${m.location}` : ''}`}
              >
                <View style={styles.userBubble}>
                  <Text style={styles.userText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    {m.text}
                  </Text>
                </View>
                {m.location ? (
                  <View style={styles.locChip}>
                    <PinIcon size={16} />
                    <Text style={styles.locChipText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      {m.location}
                    </Text>
                  </View>
                ) : null}
              </View>
            ),
          )}

          {/* 요약 카드 — "지금까지 이해한 내용" */}
          {answeredCount >= 2 ? (
            <View
              style={styles.summaryCard}
              accessibilityRole="summary"
              accessibilityLabel={`지금까지 이해한 내용. ${answeredSteps
                .map((s) => `${SUMMARY_LABEL[s]} ${answers[s]}`)
                .join(', ')}`}
            >
              <View style={styles.summaryHead}>
                <CheckBadgeIcon size={18} />
                <Text style={styles.summaryTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                  지금까지 이해한 내용
                </Text>
              </View>
              <View style={styles.summaryRows}>
                {answeredSteps.map((s) => (
                  <View key={s} style={styles.summaryRow}>
                    <Text style={styles.summaryTag} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                      {SUMMARY_LABEL[s]}
                    </Text>
                    <Text
                      style={styles.summaryValue}
                      allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}
                      numberOfLines={2}
                    >
                      {answers[s]}
                    </Text>
                  </View>
                ))}
              </View>
              <View style={styles.summaryBtns}>
                <Pressable
                  onPress={onEdit}
                  accessibilityRole="button"
                  accessibilityLabel="처음부터 수정하기"
                  style={({ pressed }) => [styles.summaryBtn, pressed && styles.pressed]}
                >
                  <EditIcon />
                  <Text style={styles.summaryBtnText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    수정하기
                  </Text>
                </Pressable>
                <Pressable
                  onPress={onUndo}
                  accessibilityRole="button"
                  accessibilityLabel="마지막 답변 되돌리기"
                  style={({ pressed }) => [styles.summaryBtn, pressed && styles.pressed]}
                >
                  <UndoIcon />
                  <Text style={styles.summaryBtnText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                    되돌리기
                  </Text>
                </Pressable>
              </View>
            </View>
          ) : null}
        </ScrollView>

        {/* 입력 영역 */}
        <View style={styles.footer}>
          {step === 'confirm' ? (
            <View style={styles.confirmFooter}>
              <CTAButton
                label="제보 전송하기"
                onPress={onSubmitTip}
                accent={ACCENT}
                loading={sending}
                accessibilityHint="수집한 내용을 수색팀에 익명으로 전달합니다"
              />
              <Text style={styles.anonNote} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                익명으로 전달돼요 · 제보자 정보는 노출되지 않아요
              </Text>
            </View>
          ) : (
            <>
              {locationAttached || hasPhoto ? (
                <View style={styles.attachRow}>
                  {locationAttached ? (
                    <View style={styles.attachPill}>
                      <PinIcon size={14} />
                      <Text style={styles.attachText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                        위치 첨부됨
                      </Text>
                    </View>
                  ) : null}
                  {hasPhoto ? (
                    <View style={styles.attachPill}>
                      <PhotoIcon size={14} />
                      <Text style={styles.attachText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                        사진 첨부됨
                      </Text>
                    </View>
                  ) : null}
                </View>
              ) : null}

              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                style={styles.chipScroll}
                contentContainerStyle={styles.chipScrollContent}
                keyboardShouldPersistTaps="handled"
              >
                {STEP_CFG[step].chips.map((chip) => {
                  const muted = isDontKnow(chip);
                  return (
                    <Pressable
                      key={chip}
                      onPress={() => submitAnswer(chip)}
                      disabled={sending}
                      accessibilityRole="button"
                      accessibilityLabel={chip}
                      hitSlop={6}
                      style={({ pressed }) => [
                        styles.chip,
                        muted ? styles.chipMuted : styles.chipAmber,
                        pressed && styles.pressed,
                      ]}
                    >
                      <Text
                        style={[styles.chipText, muted ? styles.chipTextMuted : styles.chipTextAmber]}
                        allowFontScaling
                        maxFontSizeMultiplier={type.maxScale}
                        numberOfLines={1}
                      >
                        {chip}
                      </Text>
                    </Pressable>
                  );
                })}
              </ScrollView>

              <View style={styles.inputBar}>
                <Pressable
                  onPress={onVoice}
                  disabled={sending}
                  accessibilityRole="button"
                  accessibilityLabel="음성으로 입력"
                  style={({ pressed }) => [styles.voiceBtn, pressed && styles.pressed]}
                >
                  <MicIcon />
                </Pressable>

                <View style={styles.field}>
                  <TextInput
                    style={styles.input}
                    value={input}
                    onChangeText={setInput}
                    placeholder="답하거나 말해보세요"
                    placeholderTextColor={color.textCaption}
                    editable={!sending}
                    allowFontScaling
                    maxFontSizeMultiplier={type.maxScale}
                    accessibilityLabel="제보 내용 입력"
                    returnKeyType="send"
                    onSubmitEditing={onComposerSend}
                  />
                  <Pressable
                    onPress={onAttachLocation}
                    disabled={sending}
                    accessibilityRole="button"
                    accessibilityLabel="현재 위치 첨부"
                    hitSlop={6}
                    style={({ pressed }) => [styles.fieldIcon, pressed && styles.pressed]}
                  >
                    <PinIcon size={22} stroke={color.textCaption} />
                  </Pressable>
                  <Pressable
                    onPress={onAttachPhoto}
                    disabled={sending}
                    accessibilityRole="button"
                    accessibilityLabel="사진 첨부"
                    hitSlop={6}
                    style={({ pressed }) => [styles.fieldIcon, pressed && styles.pressed]}
                  >
                    <PhotoIcon size={22} />
                  </Pressable>
                </View>

                <Pressable
                  onPress={onComposerSend}
                  disabled={sending || input.trim().length === 0}
                  accessibilityRole="button"
                  accessibilityLabel="보내기"
                  accessibilityState={{ disabled: sending || input.trim().length === 0 }}
                  style={({ pressed }) => [
                    styles.sendBtn,
                    (sending || input.trim().length === 0) && styles.sendDisabled,
                    pressed && styles.pressed,
                  ]}
                >
                  <SendUpIcon />
                </Pressable>
              </View>
            </>
          )}
        </View>
      </KeyboardAvoidingView>

      {/* 전송 중 오버레이 */}
      {sending ? (
        <View
          style={styles.overlay}
          accessibilityLiveRegion="assertive"
          accessibilityRole="alert"
          accessibilityLabel="제보를 전달하고 있어요"
        >
          <View style={styles.overlayCard}>
            <ActivityIndicator size="large" color={ACCENT} />
            <Text style={styles.overlayText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              제보를 전달하고 있어요
            </Text>
          </View>
        </View>
      ) : null}
    </SafeAreaView>
  );
}

// 카드/말풍선 그림자 (토큰 색 기반, 목업 rgba(46,32,24,.07~.12) 근사)
const softShadow: ViewStyle = {
  shadowColor: color.text,
  shadowOffset: { width: 0, height: 3 },
  shadowOpacity: 0.08,
  shadowRadius: 11,
  elevation: 2,
};
const amberShadow: ViewStyle = {
  shadowColor: color.search,
  shadowOffset: { width: 0, height: 4 },
  shadowOpacity: 0.32,
  shadowRadius: 12,
  elevation: 4,
};

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surface },
  flex: { flex: 1 },
  pressed: { opacity: 0.7 },

  // 헤더
  header: {
    backgroundColor: color.surface,
    borderBottomWidth: 1,
    borderBottomColor: color.border,
    paddingHorizontal: space.md,
    paddingBottom: space.md,
  },
  headerRow: { flexDirection: 'row', alignItems: 'center' },
  back: { width: 42, height: 42, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  title: {
    flex: 1,
    textAlign: 'center',
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    letterSpacing: -0.2,
  },
  stepper: { alignItems: 'center', gap: space.sm, marginTop: space.xs },
  segRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  segDone: { width: 22, height: 8, borderRadius: radius.pill, backgroundColor: color.search },
  segActiveHalo: {
    borderRadius: radius.pill,
    padding: 4,
    backgroundColor: color.searchWash,
  },
  segTodo: { width: 8, height: 8, borderRadius: 4, backgroundColor: color.border },
  stepMeta: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
  },

  // 채팅
  chat: { flex: 1, backgroundColor: color.successWash },
  chatContent: { padding: space.lg, paddingBottom: space.xl, gap: space.md },
  reassure: {
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: color.searchWash,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  reassureText: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.searchInk,
    fontFamily: type.family,
  },

  // 봇
  botRow: { flexDirection: 'row', alignItems: 'flex-end', alignSelf: 'flex-start', gap: space.sm, maxWidth: '88%' },
  avatar: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', ...amberShadow },
  botBubble: {
    flexShrink: 1,
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderBottomLeftRadius: radius.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    ...softShadow,
  },
  botText: { fontSize: type.size.body, fontWeight: type.weight.medium, color: color.text, fontFamily: type.family, lineHeight: 24 },

  // 유저
  userCol: { alignSelf: 'flex-end', alignItems: 'flex-end', gap: space.sm, maxWidth: '82%' },
  userBubble: {
    backgroundColor: color.search,
    borderRadius: radius.lg,
    borderBottomRightRadius: radius.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    ...amberShadow,
  },
  userText: { fontSize: type.size.body, fontWeight: type.weight.bold, color: WHITE, fontFamily: type.family, lineHeight: 24 },
  locChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    ...softShadow,
  },
  locChipText: { fontSize: type.size.caption, fontWeight: type.weight.bold, color: color.text, fontFamily: type.family },

  // 요약 카드
  summaryCard: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    ...softShadow,
  },
  summaryHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  summaryTitle: { fontSize: type.size.label, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  summaryRows: { gap: space.sm, marginTop: space.md },
  summaryRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  summaryTag: {
    width: 52,
    textAlign: 'center',
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: color.searchInk,
    backgroundColor: color.searchWash,
    borderRadius: radius.sm,
    paddingVertical: space.xs,
    fontFamily: type.family,
    overflow: 'hidden',
  },
  summaryValue: { flex: 1, fontSize: type.size.label, fontWeight: type.weight.medium, color: color.text, fontFamily: type.family },
  summaryBtns: { flexDirection: 'row', gap: space.sm, marginTop: space.lg },
  summaryBtn: {
    flex: 1,
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    backgroundColor: color.surface,
  },
  summaryBtnText: { fontSize: type.size.label, fontWeight: type.weight.bold, color: color.textBody, fontFamily: type.family },

  // 푸터/입력
  footer: {
    backgroundColor: color.surface,
    borderTopWidth: 1,
    borderTopColor: color.border,
    paddingHorizontal: space.md,
    paddingTop: space.md,
    paddingBottom: space.lg,
  },
  confirmFooter: { gap: space.sm },
  anonNote: {
    textAlign: 'center',
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
  },
  attachRow: { flexDirection: 'row', gap: space.sm, marginBottom: space.sm },
  attachPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    backgroundColor: color.searchWash,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
  attachText: { fontSize: type.size.caption, fontWeight: type.weight.bold, color: color.searchInk, fontFamily: type.family },

  chipScroll: { marginBottom: space.md },
  chipScrollContent: { gap: space.sm, paddingRight: space.md },
  chip: { minHeight: 44, borderRadius: radius.pill, paddingHorizontal: space.lg, alignItems: 'center', justifyContent: 'center' },
  chipAmber: { backgroundColor: color.searchWash },
  chipMuted: { backgroundColor: color.surfaceAlt },
  chipText: { fontSize: type.size.label, fontWeight: type.weight.bold, fontFamily: type.family },
  chipTextAmber: { color: color.searchInk },
  chipTextMuted: { color: color.textCaption },

  inputBar: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  voiceBtn: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: color.search,
    alignItems: 'center',
    justifyContent: 'center',
    ...amberShadow,
  },
  field: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    height: 52,
    backgroundColor: color.surfaceAlt,
    borderRadius: 26,
    paddingLeft: space.lg,
    paddingRight: space.xs,
  },
  input: { flex: 1, fontSize: type.size.label, color: color.text, fontFamily: type.family, paddingVertical: 0 },
  fieldIcon: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center' },
  sendBtn: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: color.search,
    alignItems: 'center',
    justifyContent: 'center',
    ...amberShadow,
  },
  sendDisabled: { opacity: 0.4 },

  // 오버레이
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: hexToRgba(color.text, 0.55),
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
