/**
 * 긴급 실종 신고 — 피그마 [보호자] 실종 신고 (2592:15718) 구현. 보호자 전용.
 *
 * 신고가 접수되면 케이스가 생기고, 다음 화면에서 예측이 돈다. 예측을 여기서
 * 기다리게 하지 않는 이유: 10초 안팎 걸리는데 그동안 "접수됐는지"조차 모른 채
 * 보고 있게 된다. 접수 확인을 먼저 주고 예측은 다음 화면에서 진행을 보여준다.
 *
 * 주소 검색 지오코딩은 아직 서버 계약에 없어 자유 텍스트로 받고, 접수 좌표는
 * DEFAULT_LKP를 쓴다. 사진 파일도 현재 Phase 1 계약이 받지 않으므로 첨부됐다고
 * 가장하지 않고 안내한다. 화면 모양은 Figma 확정 프레임을 그대로 따른다.
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
import { radius, type } from '../theme/tokens';
import { gColor, gFont } from '../theme/guardianTokens';
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
import { GuardianStandaloneTabBar } from '../components/GuardianTabBar';

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
        situation: situation.trim(),
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
    <SafeAreaView style={styles.safe} edges={['top']}>
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

        <SectionTitle icon={icEditXml} label="실종 당시 상황" />
        <TextInput
          style={styles.textarea}
          value={situation}
          onChangeText={setSituation}
          placeholder="비가 오는데 우산 없이 나가셨습니다"
          placeholderTextColor="#8E8E93"
          multiline
          accessibilityLabel="실종 당시 상황 입력"
        />

        <SectionTitle icon={icCameraXml} label="최근 사진 첨부" />
        <Pressable
          onPress={() => Alert.alert('최근 사진 첨부', '현재 신고 API는 사진 파일을 받지 않습니다. 사진 첨부 기능이 연결되면 이 버튼에서 갤러리를 엽니다.')}
          accessibilityRole="button"
          accessibilityLabel="최근 사진 첨부, 갤러리 바로가기"
          style={({ pressed }) => [styles.galleryBtn, pressed && styles.pressed]}
        >
          <SvgXml xml={icPlusXml} width={13} height={13} />
          <Text style={styles.galleryLabel} allowFontScaling
                maxFontSizeMultiplier={type.maxScale}>
            갤러리 바로가기
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
      <GuardianStandaloneTabBar active="GuardianHome" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: gColor.surface },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    height: 48,
    backgroundColor: gColor.surface,
  },
  backBtn: { width: 32 },
  title: {
    fontSize: 18,
    color: '#000000',
    fontFamily: gFont.semiBold,
  },

  scroll: { paddingHorizontal: 24, gap: 8, paddingBottom: 20 },
  sectionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 10,
    paddingHorizontal: 4,
  },
  sectionTitle: {
    fontSize: 14,
    color: '#000000',
    fontFamily: gFont.semiBold,
  },

  bar: {
    backgroundColor: gColor.barBg,
    borderRadius: radius.md,
    padding: 16,
    gap: 4,
  },
  personaName: { fontSize: 13, color: gColor.textValue, fontFamily: gFont.semiBold },
  personaSub: { fontSize: 11, color: gColor.textMuted, fontFamily: gFont.regular, lineHeight: 17 },
  quickRegBtn: { alignSelf: 'flex-start', marginTop: 4, minHeight: 32, justifyContent: 'center' },
  quickRegLabel: { fontSize: 12, color: gColor.quickRed, fontFamily: gFont.semiBold },

  searchField: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: gColor.barBg,
    borderRadius: radius.pill,
    paddingHorizontal: 16,
    minHeight: 40,
  },
  searchInput: {
    flex: 1,
    fontSize: 12,
    color: '#000000',
    fontFamily: gFont.regular,
    paddingVertical: 8,
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
    fontSize: 12,
    color: gColor.textMuted,
    fontFamily: gFont.medium,
  },
  textarea: {
    minHeight: 96,
    backgroundColor: gColor.barBg,
    borderRadius: radius.md,
    padding: 16,
    fontSize: 12,
    color: '#000000',
    fontFamily: gFont.regular,
    textAlignVertical: 'top',
  },

  galleryBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
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
  galleryLabel: { fontSize: 12, color: gColor.textMuted, fontFamily: gFont.medium },

  footer: { paddingHorizontal: 24, paddingVertical: 12, backgroundColor: gColor.surface },
  sos: {
    alignSelf: 'center',
    minWidth: 204,
    minHeight: 49,
    borderRadius: radius.pill,
    backgroundColor: gColor.alertRed,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
    shadowColor: gColor.alertRed,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.63,
    shadowRadius: 2,
    elevation: 4,
  },
  sosLabel: { fontSize: 18, color: '#FFFFFF', fontFamily: gFont.medium },
  pressed: { opacity: 0.85 },
  disabled: { opacity: 0.5 },
});
