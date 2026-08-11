import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import { ApiError } from '../api/config';
import { getPersona, updatePersona, type AttractionPoint, type Persona } from '../api/guardian';
import { useGuardianStore } from '../store/guardianStore';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import BackIcon from '../../assets/figma/detail-back.svg';
import FilterIcon from '../../assets/figma/detail-filter.svg';
import PersonIcon from '../../assets/figma/detail-person.svg';
import MapIcon from '../../assets/figma/detail-map.svg';
import BookmarkIcon from '../../assets/figma/detail-bookmark.svg';
import FigmaStatusBar from '../components/FigmaStatusBar';

function splitNote(note: string): [string, string] {
  const i = note.indexOf(':');
  return i > 0 ? [note.slice(0, i).trim(), note.slice(i + 1).trim()] : ['기타', note.trim()];
}

const GROUPS = [
  { title: '혼자 자주 가는 장소·경로', keys: ['혼자', '자주', '경로', '장소'] },
  { title: '자전적 기억 기반 목적지', keys: ['기억', '과거', '고향', '목적지'] },
  { title: '이동·교통 능력', keys: ['이동', '교통', '보행', '걷'] },
  { title: '환경 위험 취약성', keys: ['환경', '위험', '취약', '도로', '물'] },
] as const;

export default function PersonaDetailScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { personaId } = useRoute<RouteProp<RootStackParamList, 'PersonaDetail'>>().params;
  const setStorePersona = useGuardianStore((s) => s.setPersona);
  const [persona, setPersona] = useState<Persona | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState('');
  const [age, setAge] = useState('');
  const [notes, setNotes] = useState<string[]>([]);
  const [points, setPoints] = useState<AttractionPoint[]>([]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const p = await getPersona(personaId);
      setPersona(p); setName(p.name); setAge(String(p.age));
      setNotes(p.behavior_notes ?? []); setPoints(p.attraction_points ?? []);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }, [personaId]);

  useEffect(() => { load(); }, [load]);

  const groups = useMemo(() => GROUPS.map((group, groupIndex) => {
    const items = notes
      .map(splitNote)
      .filter(([label, body]) => body && (group.keys.some((key) => `${label} ${body}`.includes(key)) || (groupIndex === 0 && !GROUPS.slice(1).some((g) => g.keys.some((key) => `${label} ${body}`.includes(key))))))
      .map(([, body]) => body)
      .filter((body, index, all) => all.indexOf(body) === index);
    return { title: group.title, items };
  }), [notes]);

  const save = async () => {
    if (!persona || saving) return;
    setSaving(true); setError(null);
    try {
      const updated = await updatePersona(persona.id, {
        name: name.trim() || persona.name,
        age: Number(age.replace(/[^0-9]/g, '')) || persona.age,
        behavior_notes: notes,
        attraction_points: points,
      });
      setPersona(updated); setStorePersona(updated); setEditing(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally { setSaving(false); }
  };

  const toggleEdit = () => {
    if (!persona) return;
    if (editing) { setName(persona.name); setAge(String(persona.age)); setNotes(persona.behavior_notes ?? []); setPoints(persona.attraction_points ?? []); }
    setEditing((value) => !value);
  };

  const removePoint = (label: string) => Alert.alert('이 장소를 지울까요?', label, [
    { text: '취소', style: 'cancel' },
    { text: '지우기', style: 'destructive', onPress: () => setPoints((prev) => prev.filter((p) => p.label !== label)) },
  ]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <View style={styles.header}>
        <Pressable onPress={() => navigation.goBack()} accessibilityRole="button" accessibilityLabel="뒤로" style={styles.headerSide}><BackIcon width={10} height={18} color="#8E8E93" /></Pressable>
        <Text style={styles.headerTitle}>등록 정보</Text>
        <Pressable onPress={toggleEdit} accessibilityRole="button" accessibilityLabel={editing ? '수정 취소' : '수정하기'} style={styles.headerSide}><FilterIcon width={18} height={18} color="#8E8E93" /></Pressable>
      </View>

      {!persona && !error ? <View style={styles.center}><ActivityIndicator color={color.guardian} /></View> : null}
      {error ? <Pressable onPress={load} style={styles.error}><Text style={styles.errorText}>{error}{`\n`}눌러서 다시 시도</Text></Pressable> : null}

      {persona ? <ScrollView style={styles.scroll} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <SectionTitle icon={<PersonIcon width={12} height={12} color={color.guardian} />} title="기본 정보" />
        <View style={styles.basicCard}>
          {editing ? <>
            <EditRow label="이름" value={name} onChange={setName} />
            <EditRow label="연령" value={age} onChange={setAge} numeric />
          </> : <>
            <InfoRow label="이름" value={persona.name || '이름'} />
            <InfoRow label="연령" value={persona.age ? `${persona.age}세` : '연령'} />
          </>}
          <InfoRow label="유형" value={persona.type === 'dementia' ? '치매' : '유형'} />
        </View>

        <SectionTitle icon={<MapIcon width={8} height={11} color={color.guardian} />} title="관련 장소" />
        <View style={styles.placeCard}>
          {(points.length ? points.slice(0, 2) : [{ label: '주소' }, { label: '주소' }]).map((point, index) => (
            <View key={`${point.label}-${index}`} style={styles.infoRow}>
              <Text style={styles.infoKey}>장소{index + 1}</Text>
              <Text style={styles.infoValue}>{point.label || '주소'}</Text>
              {editing && points.length ? <Pressable onPress={() => removePoint(point.label)}><Text style={styles.remove}>지우기</Text></Pressable> : null}
            </View>
          ))}
        </View>

        <SectionTitle icon={<BookmarkIcon width={9} height={11} color={color.guardian} />} title="주요 정보" />
        {groups.map((group, index) => <View key={group.title} style={[styles.noteCard, index === 0 && styles.noteCardTall]}>
          <Text style={styles.noteTitle}>{group.title}</Text>
          {(group.items.length ? group.items : Array.from({ length: index === 0 ? 3 : index === 1 ? 1 : 2 }, (_, i) => `정보 ${i + 1}`)).slice(0, index === 0 ? 3 : index === 1 ? 1 : 2).map((item) => <Text key={item} style={styles.noteText} numberOfLines={1}>{item}</Text>)}
        </View>)}

        {editing ? <Pressable onPress={save} disabled={saving} style={styles.save}><Text style={styles.saveText}>{saving ? '저장 중…' : '저장하기'}</Text></Pressable> : null}
      </ScrollView> : null}
      <FigmaFlowTabBar mode="guardian" active="home" />
    </SafeAreaView>
  );
}

function SectionTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return <View style={styles.sectionTitle}><View style={styles.sectionIcon}>{icon}</View><Text style={styles.sectionText}>{title}</Text></View>;
}
function InfoRow({ label, value }: { label: string; value: string }) {
  return <View style={styles.infoRow}><Text style={styles.infoKey}>{label}</Text><Text style={styles.infoValue}>{value}</Text></View>;
}
function EditRow({ label, value, onChange, numeric }: { label: string; value: string; onChange: (value: string) => void; numeric?: boolean }) {
  return <View style={styles.infoRow}><Text style={styles.infoKey}>{label}</Text><TextInput value={value} onChangeText={onChange} keyboardType={numeric ? 'number-pad' : 'default'} style={styles.editInput} /></View>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  header: { height: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#FFFFFF' },
  headerSide: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontFamily: type.familySemiBold, fontSize: 18, color: '#000000' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  error: { margin: 23, borderRadius: 10, backgroundColor: color.criticalWash, padding: 16 },
  errorText: { fontFamily: type.family, fontSize: 12, lineHeight: 18, color: color.critical, textAlign: 'center' },
  scroll: { flex: 1, backgroundColor: '#FFFFFF' },
  content: { paddingHorizontal: 22, paddingBottom: 24 },
  sectionTitle: { height: 55, flexDirection: 'row', alignItems: 'center' },
  sectionIcon: { width: 20, alignItems: 'center', justifyContent: 'center' },
  sectionText: { fontFamily: type.familySemiBold, fontSize: 14, color: '#000000' },
  basicCard: { height: 111, borderRadius: 10, backgroundColor: color.figmaField, paddingHorizontal: 18, paddingVertical: 15, justifyContent: 'center' },
  placeCard: { height: 84, borderRadius: 10, backgroundColor: color.figmaField, paddingHorizontal: 18, paddingVertical: 15, justifyContent: 'center' },
  infoRow: { minHeight: 27, flexDirection: 'row', alignItems: 'center' },
  infoKey: { width: 51, fontFamily: type.familySemiBold, fontSize: 12, color: '#316837' },
  infoValue: { flex: 1, fontFamily: type.family, fontSize: 12, color: '#4D4D4D' },
  editInput: { flex: 1, height: 25, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: color.guardian, paddingVertical: 0, fontFamily: type.family, fontSize: 12, color: '#4D4D4D' },
  remove: { fontFamily: type.familySemiBold, fontSize: 11, color: color.figmaRed },
  noteCard: { minHeight: 75, borderRadius: 10, backgroundColor: color.figmaField, paddingHorizontal: 18, paddingVertical: 13, marginBottom: 14 },
  noteCardTall: { minHeight: 117 },
  noteTitle: { fontFamily: type.familySemiBold, fontSize: 12, lineHeight: 18, color: '#316837', marginBottom: 5 },
  noteText: { fontFamily: type.family, fontSize: 12, lineHeight: 22, color: '#4D4D4D' },
  save: { height: 44, borderRadius: 22, backgroundColor: color.guardian, alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
  saveText: { fontFamily: type.familySemiBold, fontSize: 14, color: '#FFFFFF' },
});
