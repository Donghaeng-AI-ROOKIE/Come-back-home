import React, { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import * as Location from 'expo-location';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import { createReport } from '../api/guardian';
import { useGuardianStore } from '../store/guardianStore';
import BaseMap from '../components/BaseMap';
import MapPin from '../components/MapPin';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import FigmaStatusBar from '../components/FigmaStatusBar';

export default function ReportScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const persona = useGuardianStore((s) => s.persona);
  const setCaseId = useGuardianStore((s) => s.setCaseId);
  const [situation, setSituation] = useState('');
  const [appearance, setAppearance] = useState('');
  const [lkp, setLkp] = useState(persona?.home ?? null);
  const [locating, setLocating] = useState(false);
  const [sending, setSending] = useState(false);

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
        appearance: appearance.trim() ? { etc: appearance.trim() } : null,
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
        <Section icon="◉" title="가족 선택"><View style={styles.field}><Text style={styles.fieldText}>{persona ? `${persona.name} (${persona.age}세)` : '사전 등록 정보 없음'}</Text></View></Section>
        <Section icon="●" title="마지막 목격 장소">
          <Pressable style={styles.search} onPress={useCurrentLocation} disabled={locating}>
            <Text style={styles.placeholder}>{locating ? '⌖  현재 위치 확인 중…' : '⌖  현재 위치 사용'}</Text>
          </Pressable>
          <View style={styles.map}>
            <BaseMap
              key={lkp ? `${lkp.lat}-${lkp.lng}` : 'empty'}
              style={StyleSheet.absoluteFill}
              region={lkp ? { latitude: lkp.lat, longitude: lkp.lng, latitudeDelta: 0.008, longitudeDelta: 0.008 } : undefined}
              accessibilityLabel="마지막 목격 장소 지도"
            >
              {lkp ? <MapPin kind="lastSeen" coordinate={lkp} title="마지막 목격 장소" /> : null}
            </BaseMap>
          </View>
          <Text style={styles.address}>
            {lkp
              ? `${lkp === persona?.home ? '사전등록 위치' : '선택한 현재 위치'} · ${lkp.lat.toFixed(5)}, ${lkp.lng.toFixed(5)}`
              : '마지막 목격 장소를 선택해 주세요'}
          </Text>
        </Section>
        <Section icon="✎" title="실종 당시 상황"><TextInput value={situation} onChangeText={setSituation} multiline style={styles.textarea} /></Section>
        <Section icon="▰" title="인상착의 설명">
          <TextInput value={appearance} onChangeText={setAppearance} placeholder="상의   하의   신발   키/체형/소지품" placeholderTextColor={color.figmaGray} style={styles.appearance} />
        </Section>
        <Pressable onPress={onSubmit} disabled={sending} style={({ pressed }) => [styles.submit, pressed && styles.pressed, sending && styles.disabled]}>
          <Text style={styles.submitText}>{sending ? '접수 중…' : '실종 접수'}</Text>
        </Pressable>
      </ScrollView>
      <FigmaFlowTabBar mode="guardian" active="home" />
    </SafeAreaView>
  );
}

function Section({ icon, title, children }: { icon: string; title: string; children: React.ReactNode }) {
  return <View style={styles.section}><Text style={styles.sectionTitle}><Text style={styles.sectionIcon}>{icon} </Text>{title}</Text>{children}</View>;
}
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  header: { height: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 18 },
  headerSide: { width: 22 }, back: { fontFamily: type.family, fontSize: 36, lineHeight: 38, color: color.figmaGray },
  title: { fontFamily: type.familySemiBold, fontSize: 18, color: '#000000' },
  content: { paddingBottom: 16 }, section: { paddingHorizontal: 23, paddingTop: 18 },
  sectionTitle: { fontFamily: type.familySemiBold, fontSize: 14, color: '#000000', marginBottom: 14 },
  sectionIcon: { color: color.figmaRed },
  field: { height: 61, borderRadius: 10, backgroundColor: color.figmaField, justifyContent: 'center', paddingHorizontal: 16 },
  fieldText: { fontFamily: type.family, fontSize: 12, color: '#525253' },
  search: { height: 30, borderRadius: 8, backgroundColor: color.figmaField, justifyContent: 'center', paddingHorizontal: 12 },
  placeholder: { fontFamily: type.family, fontSize: 12, color: '#9A9A9B' },
  map: { height: 155, borderRadius: 10, overflow: 'hidden', marginTop: 12, backgroundColor: '#EAE8E3' },
  address: { fontFamily: type.familySemiBold, fontSize: 12, color: '#525253', marginTop: 10 },
  textarea: { height: 61, borderRadius: 10, backgroundColor: color.figmaField, padding: 12, fontFamily: type.family, fontSize: 12, textAlignVertical: 'top' },
  appearance: { height: 53, borderRadius: 10, backgroundColor: color.figmaField, paddingHorizontal: 12, fontFamily: type.family, fontSize: 11, color: '#525253' },
  submit: { alignSelf: 'center', width: 204, height: 49, borderRadius: 30, backgroundColor: '#F14444', alignItems: 'center', justifyContent: 'center', marginTop: 20 },
  submitText: { fontFamily: type.familySemiBold, fontSize: 20, color: '#FFFFFF' }, pressed: { opacity: 0.8 }, disabled: { opacity: 0.5 },
});
