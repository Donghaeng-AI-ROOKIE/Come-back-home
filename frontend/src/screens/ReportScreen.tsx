/**
 * 긴급 실종 신고 (와이어프레임) — 보호자 전용.
 *
 * 신고가 접수되면 케이스가 생기고, 다음 화면에서 예측이 돈다. 예측을 여기서
 * 기다리게 하지 않는 이유: 10초 안팎 걸리는데 그동안 "접수됐는지"조차 모른 채
 * 보고 있게 된다. 접수 확인을 먼저 주고 예측은 다음 화면에서 진행을 보여준다.
 */
import React, { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import { createReport } from '../api/guardian';
import { useGuardianStore } from '../store/guardianStore';

/** 시연 기본 위치 — 위치 권한이 붙기 전까지 LKP 를 이 값으로 둔다. */
const DEFAULT_LKP = { lat: 37.6061, lng: 127.0106 };

export default function ReportScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const persona = useGuardianStore((s) => s.persona);
  const setCaseId = useGuardianStore((s) => s.setCaseId);

  const [situation, setSituation] = useState('');
  const [withPhoto, setWithPhoto] = useState(false);
  const [withDocument, setWithDocument] = useState(false);
  const [sending, setSending] = useState(false);

  const onSubmit = async () => {
    setSending(true);
    try {
      const c = await createReport({
        missing_type: 'dementia',
        lkp: DEFAULT_LKP,
        // 백엔드는 로컬 naive 시각을 기대한다 — Z(UTC)를 붙이면 9시간 어긋난다.
        lkp_time: new Date().toISOString().replace('Z', ''),
        persona_id: persona?.id ?? null,
        with_photo: withPhoto,
        with_document: withDocument,
      });
      setCaseId(c.id);
      navigation.replace('ReportSent', { caseId: c.id });
    } catch (e) {
      Alert.alert('신고를 전송하지 못했습니다', String(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          긴급 실종 신고
        </Text>

        <View style={[styles.card, styles.personaCard]}>
          {persona ? (
            <>
              <Text style={styles.personaName} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                {persona.name} ({persona.age}세)
              </Text>
              <Text style={styles.personaSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                사전에 등록해 둔 정보를 불러왔습니다.
              </Text>
            </>
          ) : (
            // 사전등록 없이도 신고는 가능해야 한다 — 급한 상황에서 등록부터 하라고
            // 막으면 골든타임을 쓴다. 다만 개인화가 빠진다는 사실은 알린다.
            <>
              <Text style={styles.personaName} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                사전 등록 정보 없음
              </Text>
              <Text style={styles.personaSub} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                신고는 지금 바로 가능합니다. 다만 개인화 없이 통계 기반으로만 예측합니다.
              </Text>
            </>
          )}
        </View>

        <Text style={styles.label} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          마지막으로 목격된 위치
        </Text>
        <View style={styles.locBox}>
          <Text style={styles.locText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            정릉동 일대 (기본 위치)
          </Text>
          <Text style={styles.locNote} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            위치 권한 연결 전이라 기본 좌표로 접수됩니다.
          </Text>
        </View>

        <Text style={styles.label} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          실종 당시 상황
        </Text>
        <TextInput
          style={styles.textarea}
          value={situation}
          onChangeText={setSituation}
          placeholder="비가 오는데 우산 없이 나가셨습니다"
          placeholderTextColor={color.textCaption}
          multiline
          accessibilityLabel="실종 당시 상황 입력"
        />

        <Toggle
          label="사진 첨부"
          hint="가장 최근 사진"
          on={withPhoto}
          onToggle={() => setWithPhoto((v) => !v)}
        />
        <Toggle
          label="경찰 제출 문서 첨부"
          hint="실종신고서 · 진술서"
          on={withDocument}
          onToggle={() => setWithDocument((v) => !v)}
        />
      </ScrollView>

      <View style={styles.footer}>
        <Pressable
          onPress={onSubmit}
          disabled={sending}
          accessibilityRole="button"
          accessibilityLabel="실종 신고 및 AI 탐색 시작"
          style={({ pressed }) => [styles.sos, pressed && styles.pressed, sending && styles.disabled]}
        >
          <Text style={styles.sosLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {sending ? '전송 중…' : '실종 신고 및 AI 탐색 시작'}
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

function Toggle({ label, hint, on, onToggle }: { label: string; hint: string; on: boolean; onToggle: () => void }) {
  return (
    <Pressable
      onPress={onToggle}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: on }}
      accessibilityLabel={`${label}, ${hint}`}
      style={({ pressed }) => [styles.toggle, on && styles.toggleOn, pressed && styles.pressed]}
    >
      <View style={styles.toggleInfo}>
        <Text style={[styles.toggleLabel, on && styles.toggleLabelOn]} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          {label}
        </Text>
        <Text style={styles.toggleHint} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          {hint}
        </Text>
      </View>
      <Text style={[styles.toggleMark, on && styles.toggleMarkOn]}>{on ? '✓' : '+'}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  scroll: { padding: space.xl, gap: space.md, paddingBottom: space.xxl },
  title: { fontSize: type.size.title, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  label: { fontSize: type.size.label, fontWeight: type.weight.bold, color: color.text, fontFamily: type.family, marginTop: space.sm },

  card: { backgroundColor: color.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: color.border, padding: space.lg, gap: space.xs },
  personaCard: { backgroundColor: color.criticalWash, borderColor: color.critical },
  personaName: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: color.criticalInk, fontFamily: type.family },
  personaSub: { fontSize: type.size.caption, color: color.textBody, fontFamily: type.family, lineHeight: 20 },

  locBox: { backgroundColor: color.surface, borderRadius: radius.md, borderWidth: 1, borderColor: color.border, padding: space.lg, gap: space.xs },
  locText: { fontSize: type.size.label, fontWeight: type.weight.bold, color: color.text, fontFamily: type.family },
  locNote: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family },

  textarea: {
    minHeight: 96,
    backgroundColor: color.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    fontSize: type.size.label,
    color: color.text,
    fontFamily: type.family,
    textAlignVertical: 'top',
  },

  toggle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    backgroundColor: color.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    minHeight: 60,
  },
  toggleOn: { borderColor: color.walk, backgroundColor: color.walkWash },
  toggleInfo: { flex: 1, gap: 2 },
  toggleLabel: { fontSize: type.size.label, fontWeight: type.weight.bold, color: color.text, fontFamily: type.family },
  toggleLabelOn: { color: color.walkInk },
  toggleHint: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family },
  toggleMark: { fontSize: 20, fontWeight: type.weight.black, color: color.textCaption },
  toggleMarkOn: { color: color.walkInk },

  footer: { padding: space.xl, borderTopWidth: 1, borderTopColor: color.border, backgroundColor: color.surface },
  sos: { minHeight: 60, borderRadius: radius.lg, backgroundColor: color.critical, alignItems: 'center', justifyContent: 'center' },
  sosLabel: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: '#FFFFFF', fontFamily: type.family },
  pressed: { opacity: 0.85 },
  disabled: { opacity: 0.5 },
});
