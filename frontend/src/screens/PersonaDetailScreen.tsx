/**
 * 사전 등록 상세 — 저장된 내용을 전부 보여주고 보호자가 고칠 수 있게 한다.
 *
 * ## 왜 필요한가
 *
 * 등록 요약은 "…외 15가지 저장"으로 접혀서 **보호자가 무엇이 저장됐는지 볼 수
 * 없었다.** 그런데 인터뷰 추출은 완벽하지 않다 — 2026-08-05 실측에서 같은 답변이
 * 두 슬롯에 중복 저장됐고, 과거 발견 장소가 "가려는 곳(끌림점)"으로 분류됐다.
 * 그 오류가 그대로 예측 근거가 되므로, 보고 고칠 수 있는 화면이 있어야 한다.
 *
 * ## 설계
 *
 * - 서버가 진실이다. 스토어 캐시가 아니라 매번 `getPersona` 로 읽는다.
 * - 관찰 문장은 "슬롯라벨: 내용" 형태로 저장되므로 라벨 기준으로 묶어 보여준다
 *   (같은 슬롯 항목이 흩어져 있으면 중복처럼 보인다).
 * - 저장은 바뀐 필드만 PATCH 한다 — 축 점수·근거는 손대지 않는다(LLM 채점 결과라
 *   원발화와 짝을 이뤄야 의미가 있고, 값만 고치면 근거와 어긋난다).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import Svg, { Path } from 'react-native-svg';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import { hexToRgba } from '../utils/color';
import CTAButton from '../components/CTAButton';
import { ApiError } from '../api/config';
import { getPersona, updatePersona, type AttractionPoint, type Persona } from '../api/guardian';
import { useGuardianStore } from '../store/guardianStore';

const ACCENT = color.walk;

/** "슬롯라벨: 내용" → [라벨, 내용]. 라벨이 없으면 기타로 묶는다. */
function splitNote(note: string): [string, string] {
  const i = note.indexOf(':');
  if (i <= 0) return ['기타 관찰', note.trim()];
  return [note.slice(0, i).trim(), note.slice(i + 1).trim()];
}

/** 라벨 기준으로 묶기 — 같은 슬롯 항목이 흩어져 있으면 중복처럼 보인다. */
function groupNotes(notes: string[]): { label: string; items: string[] }[] {
  const map = new Map<string, string[]>();
  for (const n of notes) {
    const [label, body] = splitNote(n);
    if (!body) continue;
    const arr = map.get(label) ?? [];
    // 완전히 같은 문장은 한 번만 — 추출이 중복 저장하는 경우가 있다.
    if (!arr.includes(body)) arr.push(body);
    map.set(label, arr);
  }
  return [...map.entries()].map(([label, items]) => ({ label, items }));
}

function Field({
  label, value, onChange, keyboardType, multiline,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  keyboardType?: 'default' | 'number-pad';
  multiline?: boolean;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        {label}
      </Text>
      <TextInput
        style={[styles.input, multiline && styles.inputMulti]}
        value={value}
        onChangeText={onChange}
        keyboardType={keyboardType ?? 'default'}
        multiline={multiline}
        accessibilityLabel={label}
      />
    </View>
  );
}

export default function PersonaDetailScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { personaId } = useRoute<RouteProp<RootStackParamList, 'PersonaDetail'>>().params;
  const setStorePersona = useGuardianStore((s) => s.setPersona);

  const [persona, setPersona] = useState<Persona | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);

  // 편집 중 값 — 저장 전까지 서버 값과 분리해 둔다(취소하면 되돌아가야 한다).
  const [name, setName] = useState('');
  const [age, setAge] = useState('');
  const [notes, setNotes] = useState<string[]>([]);
  const [points, setPoints] = useState<AttractionPoint[]>([]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const p = await getPersona(personaId);
      setPersona(p);
      setName(p.name);
      setAge(String(p.age));
      setNotes(p.behavior_notes ?? []);
      setPoints(p.attraction_points ?? []);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }, [personaId]);

  useEffect(() => {
    load();
  }, [load]);

  const grouped = useMemo(() => groupNotes(notes), [notes]);

  const save = async () => {
    if (!persona || saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updatePersona(persona.id, {
        name: name.trim() || persona.name,
        // 숫자만 뽑는다 — "82세"처럼 단위가 붙어 들어와도 저장은 숫자여야 한다.
        age: Number(age.replace(/[^0-9]/g, '')) || persona.age,
        behavior_notes: notes,
        attraction_points: points,
      });
      setPersona(updated);
      setStorePersona(updated);   // 홈·신고 화면이 보는 캐시도 같이 갱신
      setEditing(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const cancel = () => {
    if (!persona) return;
    setName(persona.name);
    setAge(String(persona.age));
    setNotes(persona.behavior_notes ?? []);
    setPoints(persona.attraction_points ?? []);
    setEditing(false);
  };

  const removeNote = (target: string) => {
    Alert.alert('이 내용을 지울까요?', target, [
      { text: '취소', style: 'cancel' },
      {
        text: '지우기',
        style: 'destructive',
        onPress: () => setNotes((prev) => prev.filter((n) => splitNote(n)[1] !== target)),
      },
    ]);
  };

  const removePoint = (label: string) => {
    Alert.alert('이 장소를 지울까요?', `"${label}" 을 예측에서 제외합니다.`, [
      { text: '취소', style: 'cancel' },
      {
        text: '지우기',
        style: 'destructive',
        onPress: () => setPoints((prev) => prev.filter((p) => p.label !== label)),
      },
    ]);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={styles.header}>
          <Pressable
            onPress={() => navigation.goBack()}
            accessibilityRole="button"
            accessibilityLabel="뒤로"
            hitSlop={8}
            style={styles.backBtn}
          >
            <Svg width={24} height={24} viewBox="0 0 24 24">
              <Path d="M15 5l-7 7 7 7" stroke={color.text} strokeWidth={2.2} fill="none"
                    strokeLinecap="round" strokeLinejoin="round" />
            </Svg>
          </Pressable>
          <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            등록 정보
          </Text>
          <Pressable
            onPress={() => (editing ? cancel() : setEditing(true))}
            accessibilityRole="button"
            accessibilityLabel={editing ? '수정 취소' : '수정하기'}
            hitSlop={8}
            disabled={!persona}
          >
            <Text style={[styles.editBtn, !persona && styles.dim]} allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}>
              {editing ? '취소' : '수정'}
            </Text>
          </Pressable>
        </View>

        {!persona && !error ? (
          <View style={styles.center}><ActivityIndicator color={ACCENT} /></View>
        ) : null}

        {error ? (
          <View style={styles.errorCard}>
            <Text style={styles.errorText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {error}
            </Text>
            <CTAButton label="다시 시도" onPress={load} accent={ACCENT} />
          </View>
        ) : null}

        {persona ? (
          <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
            <View style={styles.card}>
              {editing ? (
                <>
                  <Field label="이름" value={name} onChange={setName} />
                  <Field label="나이" value={age} onChange={setAge} keyboardType="number-pad" />
                </>
              ) : (
                <>
                  <View style={styles.row}>
                    <Text style={styles.rowKey}>이름 / 연령</Text>
                    <Text style={styles.rowVal}>{persona.name} ({persona.age}세)</Text>
                  </View>
                  <View style={styles.row}>
                    <Text style={styles.rowKey}>유형</Text>
                    <Text style={styles.rowVal}>치매</Text>
                  </View>
                </>
              )}
            </View>

            <Text style={styles.section} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              가시려 할 만한 곳 {points.length}곳
            </Text>
            <View style={styles.card}>
              {points.length === 0 ? (
                <Text style={styles.empty}>등록된 장소가 없습니다.</Text>
              ) : points.map((p) => (
                <View key={p.label} style={styles.itemRow}>
                  <View style={styles.itemBody}>
                    <Text style={styles.itemTitle} allowFontScaling
                          maxFontSizeMultiplier={type.maxScale}>
                      {p.label}
                    </Text>
                    <Text style={styles.itemSub} allowFontScaling
                          maxFontSizeMultiplier={type.maxScale}>
                      {[p.area_text, p.place_type].filter(Boolean).join(' · ') || '위치 정보 없음'}
                    </Text>
                  </View>
                  {editing ? (
                    <Pressable onPress={() => removePoint(p.label)} hitSlop={8}
                               accessibilityRole="button"
                               accessibilityLabel={`${p.label} 지우기`}>
                      <Text style={styles.remove}>지우기</Text>
                    </Pressable>
                  ) : null}
                </View>
              ))}
            </View>

            <Text style={styles.section} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              저장된 내용 {notes.length}가지
            </Text>
            {grouped.map((g) => (
              <View key={g.label} style={styles.card}>
                <Text style={styles.groupLabel} allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}>
                  {g.label}
                </Text>
                {g.items.map((item) => (
                  <View key={item} style={styles.itemRow}>
                    <Text style={styles.noteText} allowFontScaling
                          maxFontSizeMultiplier={type.maxScale}>
                      {item}
                    </Text>
                    {editing ? (
                      <Pressable onPress={() => removeNote(item)} hitSlop={8}
                                 accessibilityRole="button" accessibilityLabel="이 내용 지우기">
                        <Text style={styles.remove}>지우기</Text>
                      </Pressable>
                    ) : null}
                  </View>
                ))}
              </View>
            ))}

            <View style={styles.notice}>
              <Text style={styles.noticeText} allowFontScaling
                    maxFontSizeMultiplier={type.maxScale}>
                이 내용이 예측의 근거가 됩니다. 사실과 다른 부분이 있으면 수정해 주세요.
                등록 정보는 사건이 종결되면 보관 기간에 따라 파기됩니다.
              </Text>
            </View>
          </ScrollView>
        ) : null}

        {persona && editing ? (
          <View style={styles.footer}>
            <CTAButton
              label={saving ? '저장 중…' : '저장하기'}
              onPress={save}
              accent={ACCENT}
              disabled={saving}
            />
          </View>
        ) : null}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  flex: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    backgroundColor: color.surface,
    borderBottomWidth: 1,
    borderBottomColor: color.border,
  },
  backBtn: { width: 32 },
  title: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },
  editBtn: {
    width: 32,
    textAlign: 'right',
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: ACCENT,
    fontFamily: type.family,
  },
  dim: { opacity: 0.4 },

  scroll: { padding: space.lg, gap: space.sm, paddingBottom: space.xl },
  card: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
    gap: space.sm,
  },
  section: {
    marginTop: space.md,
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.textBody,
    fontFamily: type.family,
  },
  groupLabel: {
    fontSize: type.size.caption,
    fontWeight: type.weight.black,
    color: ACCENT,
    fontFamily: type.family,
    marginBottom: space.xs,
  },

  row: { flexDirection: 'row', alignItems: 'flex-start', gap: space.md },
  rowKey: {
    width: 96,
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
  },
  rowVal: {
    flex: 1,
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },

  itemRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: space.md,
    paddingVertical: space.xs,
  },
  itemBody: { flex: 1 },
  itemTitle: {
    fontSize: type.size.label,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
  },
  itemSub: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
    marginTop: 2,
  },
  noteText: {
    flex: 1,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.text,
    fontFamily: type.family,
    lineHeight: 22,
  },
  remove: {
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: color.critical,
    fontFamily: type.family,
  },
  empty: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.textCaption,
    fontFamily: type.family,
  },

  field: { gap: space.xs },
  fieldLabel: {
    fontSize: type.size.caption,
    fontWeight: type.weight.bold,
    color: color.textBody,
    fontFamily: type.family,
  },
  input: {
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    fontSize: type.size.label,
    color: color.text,
    fontFamily: type.family,
    backgroundColor: color.surfaceAlt,
  },
  inputMulti: { minHeight: 72, textAlignVertical: 'top' },

  notice: {
    marginTop: space.md,
    backgroundColor: hexToRgba(ACCENT, 0.08),
    borderRadius: radius.lg,
    padding: space.lg,
  },
  noticeText: {
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    color: color.walkInk,
    fontFamily: type.family,
    lineHeight: 20,
  },

  errorCard: {
    margin: space.lg,
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
  },

  footer: {
    padding: space.lg,
    borderTopWidth: 1,
    borderTopColor: color.border,
    backgroundColor: color.surface,
  },
});
