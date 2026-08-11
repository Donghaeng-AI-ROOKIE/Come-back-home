import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import * as Location from 'expo-location';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import Svg, { Path, Rect } from 'react-native-svg';
import PersonIcon from '../../assets/figma/detail-person.svg';
import MapIcon from '../../assets/figma/detail-map.svg';
import { color, type } from '../theme/tokens';
import { createReport } from '../api/guardian';
import { useGuardianStore } from '../store/guardianStore';
import { usePersonas } from '../hooks/queries';
import BaseMap from '../components/BaseMap';
import MapPin from '../components/MapPin';
import WebMap from '../components/WebMap';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import FigmaStatusBar from '../components/FigmaStatusBar';

export default function ReportScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const cachedPersona = useGuardianStore((s) => s.persona);
  const setPersona = useGuardianStore((s) => s.setPersona);
  const setCaseId = useGuardianStore((s) => s.setCaseId);
  const { data: serverPersonas, isLoading: personasLoading } = usePersonas();
  const personas = useMemo(() => {
    if (serverPersonas?.length) return serverPersonas;
    return cachedPersona ? [cachedPersona] : [];
  }, [cachedPersona, serverPersonas]);
  const [selectedPersonaId, setSelectedPersonaId] = useState<string | null>(cachedPersona?.id ?? null);
  const persona = personas.find((item) => item.id === selectedPersonaId) ?? personas[0] ?? null;
  const [pickerOpen, setPickerOpen] = useState(false);
  const [situation, setSituation] = useState('');
  // 인상착의는 칸을 나눠 받는다 — 한 칸에 몰아 받으면 서버가 상의/하의/신발을
  // 구분하지 못해 **색상 추출이 통째로 실패**하고(실루엣이 회색으로 남는다)
  // 알림 문구도 뭉개진다. 백엔드 스키마(top/bottom/shoes/etc)와 1:1로 맞춘다.
  const [apTop, setApTop] = useState('');
  const [apBottom, setApBottom] = useState('');
  const [apShoes, setApShoes] = useState('');
  const [apEtc, setApEtc] = useState('');
  const [lkp, setLkp] = useState(cachedPersona?.home ?? null);
  const [locationSource, setLocationSource] = useState<'persona' | 'current' | null>(cachedPersona ? 'persona' : null);
  const [locating, setLocating] = useState(false);
  const [sending, setSending] = useState(false);

  // 홈은 서버 목록을 읽는데 신고 화면만 메모리 캐시를 읽으면, 앱을 다시 연 뒤
  // persona_id 없이 신고하게 된다. 서버 목록의 첫 가족을 기본 선택하고 등록 위치도
  // 함께 복원해 Phase 2 개인화 입력이 빠지지 않게 한다.
  useEffect(() => {
    if (personas.length === 0) return;
    if (!selectedPersonaId || !personas.some((item) => item.id === selectedPersonaId)) {
      const first = personas[0];
      setSelectedPersonaId(first.id);
      setPersona(first);
      if (locationSource !== 'current') {
        setLkp(first.home);
        setLocationSource('persona');
      }
    }
  }, [locationSource, personas, selectedPersonaId, setPersona]);

  const selectPersona = (next: typeof persona) => {
    if (!next) return;
    setSelectedPersonaId(next.id);
    setPersona(next);
    setLkp(next.home);
    setLocationSource('persona');
    setPickerOpen(false);
  };

  const useCurrentLocation = async () => {
    if (locating) return;
    setLocating(true);
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status !== 'granted') {
        Alert.alert('위치 권한이 필요합니다', '현재 위치를 마지막 목격 장소로 쓰려면 위치 권한을 허용해 주세요.');
        return;
      }
      const current = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      setLkp({ lat: current.coords.latitude, lng: current.coords.longitude });
      setLocationSource('current');
    } catch (e) {
      Alert.alert('현재 위치를 확인하지 못했습니다', String(e));
    } finally {
      setLocating(false);
    }
  };

  const onSubmit = async () => {
    if (!lkp) {
      Alert.alert('마지막 목격 장소가 필요합니다', '현재 위치를 선택하거나 사전등록 정보를 확인해 주세요.');
      return;
    }
    setSending(true);
    try {
      const c = await createReport({
        missing_type: 'dementia', lkp,
        lkp_time: new Date().toISOString().replace('Z', ''), persona_id: persona?.id ?? null,
        appearance:
          apTop.trim() || apBottom.trim() || apShoes.trim() || apEtc.trim()
            ? {
                top: apTop.trim(),
                bottom: apBottom.trim(),
                shoes: apShoes.trim(),
                etc: apEtc.trim(),
              }
            : null,
        situation: situation.trim(),
      });
      setCaseId(c.id);
      navigation.replace('ReportSent', { caseId: c.id });
    } catch (e) { Alert.alert('신고를 전송하지 못했습니다', String(e)); }
    finally { setSending(false); }
  };
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <View style={styles.header}>
        <Pressable onPress={() => navigation.goBack()} hitSlop={10}><Text style={styles.back}>‹</Text></Pressable>
        <Text style={styles.title}>긴급 실종 신고</Text><View style={styles.headerSide} />
      </View>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Section icon={<PersonIcon width={13} height={13} color={color.figmaRed} />} title="가족 선택">
          <Pressable
            style={styles.field}
            onPress={() => personas.length ? setPickerOpen(true) : navigation.navigate('RegChat', { mode: 'quick' })}
            accessibilityRole="button"
            accessibilityLabel={persona ? `선택된 가족 ${persona.name} ${persona.age}세, 변경하기` : '사전 등록 시작하기'}
          >
            {personasLoading && personas.length === 0 ? <ActivityIndicator size="small" color={color.guardian} /> : (
              <><Text style={styles.fieldText}>{persona ? `${persona.name} (${persona.age}세)` : '사전 등록 정보 없음'}</Text><Text style={styles.fieldChevron}>›</Text></>
            )}
          </Pressable>
        </Section>
        <Section icon={<MapIcon width={10} height={13} color={color.figmaRed} />} title="마지막 목격 장소">
          <Pressable style={styles.search} onPress={useCurrentLocation} disabled={locating}>
            {/* '⌖' 같은 희귀 글리프는 폰 폰트에 없어 □ 로 깨진다 — 아이콘은 SVG 로. */}
            <MapIcon width={10} height={13} color={color.figmaGray} />
            <Text style={styles.placeholder}>{locating ? '현재 위치 확인 중…' : '현재 위치 사용'}</Text>
          </Pressable>
          <View style={styles.map}>
            {Platform.OS === 'web' ? (
              <WebMap style={StyleSheet.absoluteFill} center={lkp ?? undefined} marker={lkp ?? undefined} zoom={16} accessibilityLabel="마지막 목격 장소 지도" />
            ) : (
              <BaseMap
                key={lkp ? `${lkp.lat}-${lkp.lng}` : 'empty'}
                style={StyleSheet.absoluteFill}
                region={lkp ? { latitude: lkp.lat, longitude: lkp.lng, latitudeDelta: 0.008, longitudeDelta: 0.008 } : undefined}
                accessibilityLabel="마지막 목격 장소 지도"
              >
                {lkp ? <MapPin kind="lastSeen" coordinate={lkp} title="마지막 목격 장소" /> : null}
              </BaseMap>
            )}
          </View>
          <Text style={styles.address}>
            {lkp
              ? `${locationSource === 'persona' ? '사전등록 위치' : '선택한 현재 위치'} · ${lkp.lat.toFixed(5)}, ${lkp.lng.toFixed(5)}`
              : '마지막 목격 장소를 선택해 주세요'}
          </Text>
        </Section>
        <Section icon={<PencilIcon />} title="실종 당시 상황"><TextInput value={situation} onChangeText={setSituation} multiline style={styles.textarea} /></Section>
        <Section icon={<CameraIcon />} title="인상착의 설명">
          {/* 시안: 1행에 상의·하의·신발 세 칸, 2행에 키/체형/소지품 한 칸.
              라벨은 입력칸 **왼쪽**에 붙는다. */}
          <View style={styles.apRow}>
            <ApField label="상의" value={apTop} onChange={setApTop} />
            <ApField label="하의" value={apBottom} onChange={setApBottom} />
            <ApField label="신발" value={apShoes} onChange={setApShoes} />
          </View>
          <View style={styles.apRow}>
            <ApField label="키/체형/소지품" value={apEtc} onChange={setApEtc} wide />
          </View>
        </Section>
        <Pressable onPress={onSubmit} disabled={sending} style={({ pressed }) => [styles.submit, pressed && styles.pressed, sending && styles.disabled]}>
          <Text style={styles.submitText}>{sending ? '접수 중…' : '실종 접수'}</Text>
        </Pressable>
      </ScrollView>
      <Modal visible={pickerOpen} transparent animationType="fade" onRequestClose={() => setPickerOpen(false)}>
        <Pressable style={styles.modalBackdrop} onPress={() => setPickerOpen(false)}>
          <Pressable style={styles.picker} onPress={(event) => event.stopPropagation()}>
            <Text style={styles.pickerTitle}>실종 신고할 가족 선택</Text>
            {personas.map((item) => (
              <Pressable key={item.id} style={[styles.personaOption, item.id === persona?.id && styles.personaOptionSelected]} onPress={() => selectPersona(item)}>
                <View><Text style={styles.personaName}>{item.name} ({item.age}세)</Text><Text style={styles.personaMeta}>치매 사전 등록</Text></View>
                <Text style={styles.personaCheck}>{item.id === persona?.id ? '✓' : ''}</Text>
              </Pressable>
            ))}
            <Pressable style={styles.cancel} onPress={() => setPickerOpen(false)}><Text style={styles.cancelText}>취소</Text></Pressable>
          </Pressable>
        </Pressable>
      </Modal>
      <FigmaFlowTabBar mode="guardian" active="home" />
    </SafeAreaView>
  );
}

/** 인상착의 한 칸 — 시안대로 라벨이 입력칸 왼쪽에 붙는다. */
function ApField({ label, value, onChange, wide }: {
  label: string; value: string; onChange: (v: string) => void; wide?: boolean;
}) {
  return (
    <View style={[styles.apField, wide && styles.apFieldWide]}>
      <Text style={styles.apLabel} numberOfLines={1}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        style={styles.apInput}
        accessibilityLabel={`인상착의 ${label}`}
      />
    </View>
  );
}

/** 연필 — 시안의 '실종 당시 상황' 아이콘. 에셋이 없어 경로로 그린다. */
function PencilIcon() {
  return (
    <Svg width={13} height={13} viewBox="0 0 24 24">
      <Path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"
        fill={color.figmaRed} />
    </Svg>
  );
}

/** 캠코더 — 시안의 '인상착의 설명' 아이콘. */
function CameraIcon() {
  return (
    <Svg width={14} height={13} viewBox="0 0 24 24">
      <Rect x={2} y={6} width={13} height={12} rx={2.5} fill={color.figmaRed} />
      <Path d="M16.5 10.5L21.2 7.6a.7.7 0 011.05.6v7.6a.7.7 0 01-1.05.6L16.5 13.5v-3z" fill={color.figmaRed} />
    </Svg>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHead}>
        {icon}
        <Text style={styles.sectionTitle}>{title}</Text>
      </View>
      {children}
    </View>
  );
}
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  header: { height: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 18 },
  headerSide: { width: 22 }, back: { fontFamily: type.family, fontSize: 36, lineHeight: 38, color: color.figmaGray },
  title: { fontFamily: type.familySemiBold, fontSize: 18, color: '#000000' },
  // 812px 기기에서는 제출 버튼이 85px 탭바 뒤에 겹친다. 마지막 CTA가 탭 위까지
  // 실제로 스크롤되도록 탭 높이+여백을 확보한다.
  content: { paddingBottom: 108 }, section: { paddingHorizontal: 23, paddingTop: 18 },
  sectionHead: { flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: 7 },
  sectionTitle: { fontFamily: type.familySemiBold, fontSize: 14, color: '#000000', marginBottom: 14 },
  sectionIcon: { color: color.figmaRed },
  field: { height: 61, borderRadius: 10, backgroundColor: color.figmaField, justifyContent: 'center', paddingHorizontal: 16 },
  fieldText: { fontFamily: type.family, fontSize: 12, color: '#525253' },
  fieldChevron: { position: 'absolute', right: 16, fontFamily: type.family, fontSize: 24, color: color.guardian },
  search: { height: 30, borderRadius: 8, backgroundColor: color.figmaField, flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12 },
  placeholder: { fontFamily: type.family, fontSize: 12, color: '#9A9A9B' },
  map: { height: 155, borderRadius: 10, overflow: 'hidden', marginTop: 12, backgroundColor: '#EAE8E3' },
  address: { fontFamily: type.familySemiBold, fontSize: 12, color: '#525253', marginTop: 10 },
  textarea: { height: 61, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, fontFamily: type.family, fontSize: 12, textAlignVertical: 'top' },
  // 시안: 라벨(빨강)이 입력칸 왼쪽. 1행 3칸 + 2행 1칸(전체 폭).
  apRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  apField: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 5 },
  apFieldWide: { flex: 1 },
  apLabel: { fontFamily: type.family, fontSize: 11, lineHeight: 14, color: color.figmaRed },
  apInput: { flex: 1, height: 26, borderRadius: 6, backgroundColor: color.figmaField, paddingHorizontal: 8, fontFamily: type.family, fontSize: 12, color: '#525253' },
  submit: { alignSelf: 'center', width: 204, height: 49, borderRadius: 30, backgroundColor: '#F14444', alignItems: 'center', justifyContent: 'center', marginTop: 20 },
  submitText: { fontFamily: type.familySemiBold, fontSize: 20, color: '#FFFFFF' }, pressed: { opacity: 0.8 }, disabled: { opacity: 0.5 },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.28)', justifyContent: 'flex-end' },
  picker: { backgroundColor: '#FFFFFF', borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingHorizontal: 23, paddingTop: 22, paddingBottom: 34 },
  pickerTitle: { fontFamily: type.familySemiBold, fontSize: 18, color: '#000000', marginBottom: 16 },
  personaOption: { minHeight: 67, borderRadius: 10, backgroundColor: color.figmaField, paddingHorizontal: 16, marginBottom: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  personaOptionSelected: { backgroundColor: color.guardianWash, borderWidth: 1, borderColor: color.guardian },
  personaName: { fontFamily: type.familySemiBold, fontSize: 15, color: '#525253' },
  personaMeta: { fontFamily: type.family, fontSize: 11, color: color.figmaGray, marginTop: 5 },
  personaCheck: { fontFamily: type.familyBold, fontSize: 18, color: color.guardian },
  cancel: { height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', marginTop: 2 },
  cancelText: { fontFamily: type.familySemiBold, fontSize: 15, color: '#525253' },
});
