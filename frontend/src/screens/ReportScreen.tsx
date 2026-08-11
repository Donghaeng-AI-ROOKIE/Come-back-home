import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import { useQueryClient } from '@tanstack/react-query';
import { createReport, searchPlace } from '../api/guardian';
import { useGuardianStore } from '../store/guardianStore';
import { usePersonas } from '../hooks/queries';
import { useMyLocation } from '../hooks/useMyLocation';
import BaseMap from '../components/BaseMap';
import WebMap from '../components/WebMap';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import FigmaStatusBar from '../components/FigmaStatusBar';
import BackIcon from '../../assets/figma/detail-back.svg';
import SearchIcon from '../../assets/figma/report-search.svg';
import EditIcon from '../../assets/figma/report-edit.svg';
import CameraIcon from '../../assets/figma/report-camera.svg';

// report-location-map.png(시안 목업)은 더 이상 쓰지 않는다 — 미국 지도라
// 검색 전 화면에 깔면 "지도가 외국 지도"가 된다(제보 08-12). 실제 지도를 쓴다.
const PERSON_ICON = require('../../assets/figma/report-person.png');
const MAP_ICON = require('../../assets/figma/report-map.png');

export default function ReportScreen() {
  const qc = useQueryClient();
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
  const [top, setTop] = useState('');
  const [bottom, setBottom] = useState('');
  const [shoes, setShoes] = useState('');
  const [etc, setEtc] = useState('');
  const [addressQuery, setAddressQuery] = useState('');
  const [selectedAddress, setSelectedAddress] = useState('서강대학교 정문 교차로 (주소)');
  const [lkp, setLkp] = useState<{ lat: number; lng: number } | null>(null);
  const [searching, setSearching] = useState(false);
  const [sending, setSending] = useState(false);
  /**
   * 화면에 남는 오류 문구.
   *
   * 원래는 `Alert.alert` 였는데 **웹에서는 아무것도 뜨지 않는다**(RN Web 미구현).
   * 접수 버튼을 눌러도 반응이 없던 원인이 이것이다 — 막힌 이유를 말해 주려던
   * 코드가 오히려 이유를 감췄다. 폼 화면이니 팝업보다 인라인이 맞기도 하다.
   */
  const [error, setError] = useState('');
  // 검색 전 지도에 쓸 현재 위치 — 시안 목업 PNG(미국 지도) 대신 그린다.
  const { point: here } = useMyLocation(true);

  // 홈과 신고 화면이 같은 서버 페르소나를 쓰도록 복원한다. 화면의 빈 선택 카드는
  // Figma 원본 표현이지만, 접근성 라벨과 모달에는 실제 선택값이 유지된다.
  useEffect(() => {
    if (personas.length === 0) return;
    if (!selectedPersonaId || !personas.some((item) => item.id === selectedPersonaId)) {
      const first = personas[0];
      setSelectedPersonaId(first.id);
      setPersona(first);
    }
  }, [personas, selectedPersonaId, setPersona]);

  const selectPersona = (next: typeof persona) => {
    if (!next) return;
    setSelectedPersonaId(next.id);
    setPersona(next);
    setPickerOpen(false);
  };

  /**
   * 주소 검색 — **서버 지오코더**를 쓴다.
   *
   * 전에는 `Location.geocodeAsync` 였는데 그 함수는 **웹에서 동작하지 않는다.**
   * 배포본이 웹이라 검색이 늘 실패했고, 그래서 좌표가 안 잡혀 지도는 시안
   * 목업(미국 지도)에 머물고 아래 주소 문구도 기본값 그대로였다. 게다가 실패
   * 안내가 `Alert.alert` 라 웹에서는 그마저 안 보였다(현장 제보 08-12).
   *
   * 서버 경로는 온보딩 끌림점과 같은 체인(카카오 우선)이라 두 곳이 같은 좌표를 준다.
   */
  const searchAddress = async () => {
    const query = addressQuery.trim();
    if (!query || searching) return;
    setSearching(true);
    setError('');
    try {
      const place = await searchPlace(query);
      setLkp({ lat: place.lat, lng: place.lng });
      // 검색어가 아니라 **매칭된 정식 명칭**을 보여준다 — 무엇에 걸렸는지 알아야
      // 엉뚱한 곳으로 신고되는 것을 보호자가 알아챌 수 있다.
      setSelectedAddress(place.label);
    } catch (e) {
      setError(`"${query}" 을(를) 찾지 못했습니다. 장소명이나 도로명을 조금 더 구체적으로 적어 주세요.`);
    } finally {
      setSearching(false);
    }
  };

  const onSubmit = async () => {
    if (!lkp) {
      // 웹에서는 Alert.alert 가 아무것도 띄우지 않는다 — 그래서 이 검증이
      // 걸릴 때마다 **버튼이 고장 난 것처럼** 보였다(현장 제보 08-12).
      // 화면 안에 남는 문구로 바꾼다.
      setError('마지막 목격 장소를 먼저 검색해 주세요. 위 검색창에 장소를 입력하고 검색(엔터)하면 지도가 그 위치로 바뀝니다.');
      return;
    }
    setError('');
    const hasAppearance = [top, bottom, shoes, etc].some((value) => value.trim().length > 0);
    setSending(true);
    try {
      const c = await createReport({
        missing_type: 'dementia',
        lkp,
        lkp_time: new Date().toISOString().replace('Z', ''),
        persona_id: persona?.id ?? null,
        appearance: hasAppearance ? {
          top: top.trim(),
          bottom: bottom.trim(),
          shoes: shoes.trim(),
          etc: etc.trim(),
        } : null,
        situation: situation.trim(),
      });
      setCaseId(c.id);
      // 보호자 알림 탭은 내 사건을 따로 조회한다 — 새 신고가 바로 잡히게 무효화한다.
      qc.invalidateQueries({ queryKey: ['guardianCase'] });
      navigation.replace('ReportSent', { caseId: c.id });
    } catch (e) {
      setError(`신고를 전송하지 못했습니다. ${String(e)}`);
    } finally {
      setSending(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />

      <View style={styles.header}>
        <Pressable style={styles.headerSide} onPress={() => navigation.goBack()} hitSlop={10} accessibilityLabel="뒤로 가기">
          <BackIcon width={10} height={18} />
        </Pressable>
        <Text style={styles.title}>긴급 실종 신고</Text>
        <View style={styles.headerSide} />
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.familySection}>
          <SectionHeader icon={<Image source={PERSON_ICON} style={styles.personIcon} />} title="가족 선택" />
          <Pressable
            style={styles.familyField}
            onPress={() => personas.length ? setPickerOpen(true) : navigation.navigate('RegChat', { mode: 'quick' })}
            accessibilityRole="button"
            accessibilityLabel={persona ? `선택된 가족 ${persona.name} ${persona.age}세, 변경하기` : '사전 등록 시작하기'}
          >
            {/* 시안의 이 자리는 빈 회색 상자인데, **누구를 신고하는지 화면에
                안 보이면 안 된다.** 실제로 "한 명 선택해도 여기 안 뜬다"는
                제보를 받았다(08-12) — 선택은 되고 있었고 표시만 없었다.
                실종 신고에서 대상자 확인은 생략할 수 있는 정보가 아니다. */}
            {personasLoading && personas.length === 0
              ? <ActivityIndicator size="small" color={color.figmaGray} />
              : persona
                ? (
                  <View style={styles.familyPicked}>
                    <Text style={styles.familyName}>{persona.name} ({persona.age}세)</Text>
                    <Text style={styles.familyHint}>{personas.length > 1 ? '눌러서 변경' : '치매 등록'}</Text>
                  </View>
                )
                : <Text style={styles.familyHint}>사전 등록된 가족이 없습니다. 눌러서 등록해 주세요.</Text>}
          </Pressable>
        </View>

        <View style={styles.locationSection}>
          <SectionHeader icon={<Image source={MAP_ICON} style={styles.mapIcon} />} title="마지막 목격 장소" />
          <View style={styles.searchField}>
            <SearchIcon width={14} height={14} />
            <TextInput
              value={addressQuery}
              onChangeText={setAddressQuery}
              onSubmitEditing={searchAddress}
              placeholder={searching ? '주소 검색 중…' : '주소 검색'}
              placeholderTextColor="#9A9A9B"
              returnKeyType="search"
              style={styles.searchInput}
              accessibilityLabel="마지막 목격 장소 주소 검색"
            />
          </View>
          <Pressable style={styles.mapFrame} onPress={searchAddress} accessibilityLabel="마지막 목격 장소 지도">
            {lkp ? (
              <>
                {Platform.OS === 'web' ? (
                  <WebMap style={StyleSheet.absoluteFill} center={lkp} zoom={16} accessibilityLabel="검색한 마지막 목격 장소 지도" />
                ) : (
                  <BaseMap
                    style={StyleSheet.absoluteFill}
                    region={{ latitude: lkp.lat, longitude: lkp.lng, latitudeDelta: 0.008, longitudeDelta: 0.008 }}
                    scrollEnabled={false}
                    accessibilityLabel="검색한 마지막 목격 장소 지도"
                  />
                )}
                <View pointerEvents="none" style={styles.locationRadius} />
                <View pointerEvents="none" style={styles.locationDot} />
              </>
            ) : (
              /* 좌표가 아직 없을 때 시안 목업 PNG 를 깔면 **미국 지도**가 뜬다
                 (시안 이미지가 그렇다 — "지도도 외국 지도 같다"는 제보 08-12).
                 검색 전에도 여기가 어디인지 보이는 편이 낫고, 실제 지도가 떠야
                 검색 후 바뀌는 것도 알아본다. 그래서 **보호자의 현재 위치**를
                 그린다. 위치도 없으면 그때만 안내 문구로 물러난다. */
              here ? (
                <>
                  {Platform.OS === 'web' ? (
                    <WebMap style={StyleSheet.absoluteFill} center={here} zoom={15} accessibilityLabel="현재 위치 지도" />
                  ) : (
                    <BaseMap
                      style={StyleSheet.absoluteFill}
                      region={{ latitude: here.lat, longitude: here.lng, latitudeDelta: 0.01, longitudeDelta: 0.01 }}
                      scrollEnabled={false}
                      accessibilityLabel="현재 위치 지도"
                    />
                  )}
                  <View pointerEvents="none" style={styles.locationRadius} />
                  <View pointerEvents="none" style={styles.locationDot} />
                </>
              ) : (
                <View style={styles.mapEmpty}><Text style={styles.mapEmptyText}>위 검색창에 마지막 목격 장소를 입력해 주세요</Text></View>
              )
            )}
          </Pressable>
          <Text style={styles.address} numberOfLines={1}>
            {lkp ? selectedAddress : '아직 장소를 선택하지 않았습니다'}
          </Text>
          {error ? (
            <View style={styles.errorBox} accessibilityRole="alert">
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}
        </View>

        <View style={styles.situationSection}>
          <SectionHeader icon={<EditIcon width={12} height={12} />} title="실종 당시 상황" />
          <TextInput
            value={situation}
            onChangeText={setSituation}
            multiline
            textAlignVertical="top"
            style={styles.textarea}
            accessibilityLabel="실종 당시 상황"
          />
        </View>

        <View style={styles.appearanceSection}>
          <SectionHeader compact icon={<CameraIcon width={12.24} height={8} />} title="인상착의 설명" />
          <View style={styles.appearanceTopRow}>
            <AppearanceField label="상의" value={top} onChangeText={setTop} accessibilityLabel="상의 설명" />
            <AppearanceField label="하의" value={bottom} onChangeText={setBottom} accessibilityLabel="하의 설명" />
            <AppearanceField label="신발" value={shoes} onChangeText={setShoes} accessibilityLabel="신발 설명" />
          </View>
          <View style={styles.appearanceBottomRow}>
            <Text style={styles.appearanceEtcLabel}>키/체형/소지품</Text>
            <TextInput value={etc} onChangeText={setEtc} style={styles.appearanceEtcInput} accessibilityLabel="키 체형 소지품 설명" />
          </View>
        </View>

        <View style={styles.ctaSection}>
          <Pressable onPress={onSubmit} disabled={sending} style={({ pressed }) => [styles.submit, pressed && styles.pressed, sending && styles.disabled]}>
            <Text style={styles.submitText}>{sending ? '접수 중…' : '실종 접수'}</Text>
          </Pressable>
        </View>
      </ScrollView>

      <Modal visible={pickerOpen} transparent animationType="fade" onRequestClose={() => setPickerOpen(false)}>
        <Pressable style={styles.modalBackdrop} onPress={() => setPickerOpen(false)}>
          <Pressable style={styles.picker} onPress={(event) => event.stopPropagation()}>
            <Text style={styles.pickerTitle}>실종 신고할 가족 선택</Text>
            {personas.map((item) => (
              <Pressable key={item.id} style={[styles.personaOption, item.id === persona?.id && styles.personaOptionSelected]} onPress={() => selectPersona(item)}>
                <View>
                  <Text style={styles.personaName}>{item.name} ({item.age}세)</Text>
                  <Text style={styles.personaMeta}>치매 사전 등록</Text>
                </View>
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

function SectionHeader({ icon, title, compact = false }: { icon: React.ReactNode; title: string; compact?: boolean }) {
  return (
    <View style={[styles.sectionHeader, compact && styles.sectionHeaderCompact]}>
      <View style={styles.sectionIcon}>{icon}</View>
      <Text style={styles.sectionTitle}>{title}</Text>
    </View>
  );
}

function AppearanceField({ label, value, onChangeText, accessibilityLabel }: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  accessibilityLabel: string;
}) {
  return (
    <View style={styles.appearanceField}>
      <Text style={styles.appearanceLabel}>{label}</Text>
      <TextInput value={value} onChangeText={onChangeText} style={styles.appearanceInput} accessibilityLabel={accessibilityLabel} />
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  header: { height: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerSide: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center' },
  title: { fontFamily: type.familySemiBold, fontSize: 18, lineHeight: 23, color: '#000000' },
  scroll: { flex: 1, backgroundColor: '#FFFFFF' },
  content: { paddingBottom: 0 },

  sectionHeader: { height: 55, paddingHorizontal: 20, paddingTop: 13, flexDirection: 'row', alignItems: 'flex-start' },
  sectionHeaderCompact: { height: 45 },
  sectionIcon: { width: 17, height: 18, alignItems: 'center', justifyContent: 'center' },
  sectionTitle: { marginLeft: 6, fontFamily: type.familySemiBold, fontSize: 14, lineHeight: 18, color: '#000000' },
  personIcon: { width: 12, height: 12 },
  mapIcon: { width: 8, height: 11 },

  familySection: { height: 128, backgroundColor: '#FFFFFF' },
  familyField: { height: 61, marginHorizontal: 23, borderRadius: 10, backgroundColor: '#F8F8F8', alignItems: 'center', justifyContent: 'center' },
  familyPicked: { alignItems: 'center' },
  familyName: { fontFamily: type.familySemiBold, fontSize: 16, lineHeight: 21, color: '#3D3D3E' },
  familyHint: { marginTop: 2, fontFamily: type.family, fontSize: 11, lineHeight: 14, color: '#9A9A9B', textAlign: 'center', paddingHorizontal: 16 },
  mapEmpty: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F1F1EF', paddingHorizontal: 24 },
  mapEmptyText: { fontFamily: type.family, fontSize: 12, lineHeight: 17, color: '#9A9A9B', textAlign: 'center' },
  // 웹에서 Alert 가 안 뜨는 자리를 대신한다 — 막힌 이유가 화면에 남아야 한다.
  errorBox: { marginTop: 8, marginHorizontal: 23, borderRadius: 8, backgroundColor: '#FDECEC', paddingHorizontal: 12, paddingVertical: 10 },
  errorText: { fontFamily: type.family, fontSize: 12, lineHeight: 17, color: '#C0392B' },

  locationSection: { height: 286, backgroundColor: '#FFFFFF' },
  searchField: { height: 30, marginHorizontal: 23, borderRadius: 8, backgroundColor: '#F8F8F8', flexDirection: 'row', alignItems: 'center', paddingLeft: 11 },
  searchInput: { flex: 1, height: 30, paddingHorizontal: 10, paddingVertical: 0, fontFamily: type.family, fontSize: 12, lineHeight: 16, color: '#525253', outlineStyle: 'none' } as any,
  mapFrame: { height: 155, marginHorizontal: 23, marginTop: 12, borderRadius: 10, overflow: 'hidden', backgroundColor: '#EEECE6' },
  mapImage: { width: '100%', height: '100%' },
  locationRadius: { position: 'absolute', left: '50%', top: '50%', width: 94, height: 94, marginLeft: -47, marginTop: -47, borderRadius: 47, backgroundColor: 'rgba(0,122,255,0.11)' },
  locationDot: { position: 'absolute', left: '50%', top: '50%', width: 22, height: 22, marginLeft: -11, marginTop: -11, borderRadius: 11, backgroundColor: '#007AFF', borderWidth: 3, borderColor: '#FFFFFF', shadowColor: '#000000', shadowOpacity: 0.22, shadowRadius: 2, shadowOffset: { width: 0, height: 1 } },
  address: { height: 25, marginTop: 8, marginHorizontal: 30, fontFamily: type.familySemiBold, fontSize: 12, lineHeight: 25, color: '#525253' },

  situationSection: { height: 117, backgroundColor: '#FFFFFF' },
  textarea: { height: 61, marginHorizontal: 23, borderRadius: 10, backgroundColor: '#F8F8F8', paddingHorizontal: 12, paddingVertical: 9, fontFamily: type.family, fontSize: 12, lineHeight: 16, color: '#525253', outlineStyle: 'none' } as any,

  appearanceSection: { height: 104, backgroundColor: '#FFFFFF' },
  appearanceTopRow: { height: 21, marginHorizontal: 29, flexDirection: 'row', justifyContent: 'space-between' },
  appearanceField: { width: 103, height: 21, flexDirection: 'row', alignItems: 'center' },
  appearanceLabel: { width: 27, fontFamily: type.familySemiBold, fontSize: 12, lineHeight: 16, color: '#E05454' },
  appearanceInput: { flex: 1, height: 21, borderRadius: 5, backgroundColor: '#F8F8F8', paddingHorizontal: 5, paddingVertical: 0, fontFamily: type.family, fontSize: 11, lineHeight: 14, color: '#525253', outlineStyle: 'none' } as any,
  appearanceBottomRow: { height: 21, marginHorizontal: 29, marginTop: 10, flexDirection: 'row', alignItems: 'center' },
  appearanceEtcLabel: { width: 80, fontFamily: type.familySemiBold, fontSize: 12, lineHeight: 16, color: '#E05454' },
  appearanceEtcInput: { flex: 1, height: 21, borderRadius: 5, backgroundColor: '#F8F8F8', paddingHorizontal: 5, paddingVertical: 0, fontFamily: type.family, fontSize: 11, lineHeight: 14, color: '#525253', outlineStyle: 'none' } as any,

  ctaSection: { height: 77, alignItems: 'center', backgroundColor: '#FFFFFF', paddingTop: 13 },
  submit: { width: 204, height: 49, borderRadius: 30, backgroundColor: '#F14444', alignItems: 'center', justifyContent: 'center', shadowColor: '#F14444', shadowOpacity: 0.63, shadowRadius: 2, shadowOffset: { width: 0, height: 0 } },
  submitText: { fontFamily: type.familySemiBold, fontSize: 20, lineHeight: 25, color: '#FFFFFF' },
  pressed: { opacity: 0.8 },
  disabled: { opacity: 0.5 },

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
