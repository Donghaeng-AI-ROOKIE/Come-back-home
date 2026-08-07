/**
 * 긴급 실종 신고 — 피그마 [보호자] 실종 신고 (2592:15718) 구현. 보호자 전용.
 *
 * 신고가 접수되면 케이스가 생기고, 다음 화면에서 예측이 돈다. 예측을 여기서
 * 기다리게 하지 않는 이유: 10초 안팎 걸리는데 그동안 "접수됐는지"조차 모른 채
 * 보고 있게 된다. 접수 확인을 먼저 주고 예측은 다음 화면에서 진행을 보여준다.
 *
 * 피그마 대비 의도적 차이:
 * - 주소 검색 필드는 지오코딩이 아직 없어 자유 텍스트만 받는다(접수에는
 *   DEFAULT_LKP 좌표가 나간다 — 위치 권한·검색 연동 전까지의 한계를 지도
 *   아래 캡션으로 알린다).
 * - 경찰 제출 문서 토글은 피그마에 없지만 기능을 유지한다(백엔드 신뢰도 가점).
 */
import React, { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { SvgXml } from 'react-native-svg';
import { Circle, Marker } from 'react-native-maps';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import { gColor } from '../theme/guardianTokens';
import {
  icBackXml,
  icCameraXml,
  icEditXml,
  icMappinRedXml,
  icPersonRedXml,
  icPlusXml,
  icSearchXml,
} from '../assets/guardianSvg';
import { BaseMap } from '../components/BaseMap';
import { createReport } from '../api/guardian';
import { useGuardianStore } from '../store/guardianStore';

/** 시연 기본 위치 — 위치 권한이 붙기 전까지 LKP 를 이 값으로 둔다. */
const DEFAULT_LKP = { lat: 37.6061, lng: 127.0106 };

function SectionTitle({ icon, label }: { icon: string; label: string }) {
  return (
    <View style={styles.sectionRow}>
      <SvgXml xml={icon} width={14} height={14} />
      <Text style={styles.sectionTitle} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
        {label}
      </Text>
    </View>
  );
}

export default function ReportScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const persona = useGuardianStore((s) => s.persona);
  const setCaseId = useGuardianStore((s) => s.setCaseId);

  const [address, setAddress] = useState('');
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
      <View style={styles.header}>
        <Pressable
          onPress={() => navigation.goBack()}
          accessibilityRole="button"
          accessibilityLabel="뒤로"
          hitSlop={8}
          style={styles.backBtn}
        >
          <SvgXml xml={icBackXml} width={10} height={18} />
        </Pressable>
        <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          긴급 실종 신고
        </Text>
        <View style={styles.backBtn} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <SectionTitle icon={icPersonRedXml} label="가족 선택" />
        <View style={styles.bar}>
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
              <Pressable
                onPress={() => navigation.navigate('RegChat', { quick: true })}
                accessibilityRole="button"
                accessibilityLabel="빠른 등록 진행하기"
                accessibilityHint="필수 정보만 짧게 등록해 예측을 개인화합니다"
                style={({ pressed }) => [styles.quickRegBtn, pressed && styles.pressed]}
              >
                <Text style={styles.quickRegLabel} allowFontScaling
                      maxFontSizeMultiplier={type.maxScale}>
                  빠른 등록 진행하기 →
                </Text>
              </Pressable>
            </>
          )}
        </View>

        <SectionTitle icon={icMappinRedXml} label="마지막 목격 장소" />
        <View style={styles.searchField}>
          <SvgXml xml={icSearchXml} width={14} height={14} />
          <TextInput
            style={styles.searchInput}
            value={address}
            onChangeText={setAddress}
            placeholder="주소 검색"
            placeholderTextColor="#9A9A9B"
            accessibilityLabel="마지막 목격 장소 주소 검색"
          />
        </View>
        <View style={styles.mapWrap}>
          <BaseMap
            region={{
              latitude: DEFAULT_LKP.lat,
              longitude: DEFAULT_LKP.lng,
              latitudeDelta: 0.008,
              longitudeDelta: 0.008,
            }}
            style={styles.map}
            scrollEnabled={false}
            liteMode
            accessibilityLabel="마지막 목격 장소 지도"
          >
            <Circle
              center={{ latitude: DEFAULT_LKP.lat, longitude: DEFAULT_LKP.lng }}
              radius={180}
              fillColor="rgba(0,122,255,0.15)"
              strokeColor="rgba(0,122,255,0.3)"
            />
            <Marker
              coordinate={{ latitude: DEFAULT_LKP.lat, longitude: DEFAULT_LKP.lng }}
              anchor={{ x: 0.5, y: 0.5 }}
            >
              <View style={styles.blueDot} />
            </Marker>
          </BaseMap>
        </View>
        <Text style={styles.locCaption} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          {address.trim() || '정릉동 일대 (기본 위치)'}
        </Text>
        <Text style={styles.locNote} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          위치 권한·주소 검색 연동 전이라 기본 좌표로 접수됩니다.
        </Text>

        <SectionTitle icon={icEditXml} label="실종 당시 상황" />
        <TextInput
          style={styles.textarea}
          value={situation}
          onChangeText={setSituation}
          placeholder="비가 오는데 우산 없이 나가셨습니다"
          placeholderTextColor={color.textCaption}
          multiline
          accessibilityLabel="실종 당시 상황 입력"
        />

        <SectionTitle icon={icCameraXml} label="최근 사진 첨부" />
        <Pressable
          onPress={() => setWithPhoto((v) => !v)}
          accessibilityRole="checkbox"
          accessibilityState={{ checked: withPhoto }}
          accessibilityLabel="최근 사진 첨부, 갤러리 바로가기"
          style={({ pressed }) => [styles.galleryBtn, withPhoto && styles.galleryBtnOn, pressed && styles.pressed]}
        >
          <SvgXml xml={icPlusXml} width={13} height={13} />
          <Text style={[styles.galleryLabel, withPhoto && styles.galleryLabelOn]} allowFontScaling
                maxFontSizeMultiplier={type.maxScale}>
            {withPhoto ? '최근 사진 첨부됨 ✓' : '갤러리 바로가기'}
          </Text>
        </Pressable>

        <Pressable
          onPress={() => setWithDocument((v) => !v)}
          accessibilityRole="checkbox"
          accessibilityState={{ checked: withDocument }}
          accessibilityLabel="경찰 제출 문서 첨부, 실종신고서·진술서"
          style={({ pressed }) => [styles.docRow, pressed && styles.pressed]}
        >
          <Text style={[styles.docMark, withDocument && styles.docMarkOn]}>{withDocument ? '✓' : '+'}</Text>
          <Text style={styles.docLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            경찰 제출 문서 첨부 (실종신고서 · 진술서)
          </Text>
        </Pressable>
      </ScrollView>

      <View style={styles.footer}>
        <Pressable
          onPress={onSubmit}
          disabled={sending}
          accessibilityRole="button"
          accessibilityLabel="실종 접수 및 AI 탐색 시작"
          style={({ pressed }) => [styles.sos, pressed && styles.pressed, sending && styles.disabled]}
        >
          <Text style={styles.sosLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {sending ? '전송 중…' : '실종 접수'}
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: gColor.surface },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    backgroundColor: gColor.surface,
  },
  backBtn: { width: 32 },
  title: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.medium,
    color: color.text,
    fontFamily: type.family,
  },

  scroll: { padding: space.lg, gap: space.sm, paddingBottom: space.xl },
  sectionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    marginTop: space.md,
    paddingHorizontal: space.xs,
  },
  sectionTitle: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: color.text,
    fontFamily: type.family,
  },

  bar: {
    backgroundColor: gColor.barBg,
    borderRadius: radius.md,
    padding: space.lg,
    gap: space.xs,
  },
  personaName: { fontSize: type.size.body, fontWeight: type.weight.bold, color: gColor.textValue, fontFamily: type.family },
  personaSub: { fontSize: type.size.caption, color: color.textBody, fontFamily: type.family, lineHeight: 20 },
  quickRegBtn: { alignSelf: 'flex-start', marginTop: space.xs, minHeight: 32, justifyContent: 'center' },
  quickRegLabel: { fontSize: type.size.label, fontWeight: type.weight.bold, color: gColor.quickRed, fontFamily: type.family },

  searchField: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: gColor.barBg,
    borderRadius: radius.pill,
    paddingHorizontal: space.lg,
    minHeight: 40,
  },
  searchInput: {
    flex: 1,
    fontSize: type.size.label,
    color: color.text,
    fontFamily: type.family,
    paddingVertical: space.sm,
  },

  mapWrap: { borderRadius: 20, overflow: 'hidden' },
  map: { height: 190, borderRadius: 20 },
  blueDot: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: '#007AFF',
    borderWidth: 3,
    borderColor: '#FFFFFF',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.3,
    shadowRadius: 2,
    elevation: 3,
  },
  locCaption: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    color: gColor.textMuted,
    fontFamily: type.family,
  },
  locNote: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family },

  textarea: {
    minHeight: 96,
    backgroundColor: gColor.barBg,
    borderRadius: radius.md,
    padding: space.lg,
    fontSize: type.size.label,
    color: color.text,
    fontFamily: type.family,
    textAlignVertical: 'top',
  },

  galleryBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    alignSelf: 'center',
    minWidth: 255,
    minHeight: 44,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(248,248,248,0.8)',
    shadowColor: '#000000',
    shadowOffset: { width: 1, height: 1 },
    shadowOpacity: 0.25,
    shadowRadius: 2,
    elevation: 2,
  },
  galleryBtnOn: { backgroundColor: color.walkWash },
  galleryLabel: { fontSize: type.size.label, fontWeight: type.weight.medium, color: gColor.textMuted, fontFamily: type.family },
  galleryLabelOn: { color: gColor.inkGreen },

  docRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.sm,
    minHeight: 40,
  },
  docMark: { fontSize: 18, fontWeight: type.weight.black, color: color.textCaption },
  docMarkOn: { color: gColor.inkGreen },
  docLabel: { fontSize: type.size.caption, color: color.textBody, fontFamily: type.family },

  footer: { padding: space.lg, backgroundColor: gColor.surface },
  sos: {
    alignSelf: 'center',
    minWidth: 204,
    minHeight: 49,
    borderRadius: radius.pill,
    backgroundColor: gColor.alertRed,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xl,
    shadowColor: gColor.alertRed,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.63,
    shadowRadius: 2,
    elevation: 4,
  },
  sosLabel: { fontSize: type.size.title, fontWeight: type.weight.medium, color: '#FFFFFF', fontFamily: type.family },
  pressed: { opacity: 0.85 },
  disabled: { opacity: 0.5 },
});
