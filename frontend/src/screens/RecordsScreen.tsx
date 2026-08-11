import React, { useState } from 'react';
import { Alert, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import dayjs from 'dayjs';
import { color, type } from '../theme/tokens';
import { useWalkStats } from '../hooks/queries';
import { useAuthStore } from '../store/authStore';
import FigmaStatusBar from '../components/FigmaStatusBar';
import { formatKm, serverTimeMs } from '../utils/walkFormat';

export default function RecordsScreen() {
  const { data, isLoading, refetch, isRefetching } = useWalkStats();
  // 시민 '내 정보'에 계정 영역이 통째로 없었다 — 로그인하면 로그아웃도, 역할
  // 전환도 못 해 빠져나올 방법이 없었다(현장 제보 08-11). 보호자 쪽과 맞춘다.
  const { user, signOut, switchRole } = useAuthStore();
  const [switching, setSwitching] = useState(false);
  return <SafeAreaView style={styles.safe} edges={['top']}><StatusBar style="dark" /><FigmaStatusBar /><ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}>
    <Text style={styles.title}>내 동행 기록</Text>
    <View style={styles.hero} accessibilityLabel={isLoading ? '동행 기록을 불러오는 중' : `${data?.level_label ?? '안심 동행'} 레벨 ${data?.level ?? 1}`} />
    <View style={styles.metrics}><Metric label="총 동행 거리" value={`${formatKm(data?.total_km ?? 0)}km`} color={color.brand} /><Metric label="실종자 제보" value={`${data?.tip_count ?? 0}건`} color={color.figmaRed} /></View>
    <Text style={styles.section}>최근 획득한 배지</Text><View style={styles.badges}>{data?.badges.filter((b) => b.earned).slice(0, 4).map((b) => <View key={b.id} style={styles.badge}><Text style={styles.badgeIcon}>{b.icon}</Text><Text style={styles.badgeLabel}>{b.label}</Text></View>)}</View>
    <Text style={[styles.section, styles.recentSection]}>최근 산책 기록</Text>
    {/* 시각은 **서버 UTC 를 변환해서** 찍는다. 그냥 dayjs(문자열) 로 넣으면 오프셋이
        없어 로컬 시간으로 읽히고 9시간 과거가 된다(실측 08-12: 01:41 에 끝낸
        산책이 "16:41" 로 떠서 기록이 안 들어간 줄 알았다).

        꺾쇠(›)는 뺐다 — 눌러도 아무 일이 없는 표식이었다(현장 제보 08-12).
        지난 산책의 상세 화면이 시안에 없어서 보낼 곳이 없다. 있는 것처럼
        보이게 두느니 없는 편이 낫다. */}
    {(data?.recent.length ? data.recent : [{ id: 'empty1', area_label: '산책 장소 1', distance_km: 0, ended_at: null }, { id: 'empty2', area_label: '산책 장소 2', distance_km: 0, ended_at: null }]).slice(0, 2).map((s) => <View key={s.id} style={styles.recent}><View><Text style={styles.recentTitle}>{s.area_label || '산책'}</Text><Text style={styles.recentDate}>산책 일시: {s.ended_at ? dayjs(serverTimeMs(s.ended_at)).format('YYYY.MM.DD HH:mm') : ''}</Text></View><Text style={styles.km}>{formatKm(s.distance_km)} km</Text></View>)}
    <Text style={[styles.section, styles.recentSection]}>계정</Text>
    <View style={styles.account}>
      <View style={styles.accountRow}>
        <Text style={styles.accountKey}>아이디</Text>
        <Text style={styles.accountVal} numberOfLines={1}>{user ?? '-'}</Text>
      </View>
      <Pressable
        onPress={async () => {
          if (switching) return;
          setSwitching(true);
          try {
            await switchRole('guardian');
          } catch (e) {
            Alert.alert('전환하지 못했습니다', String(e));
          } finally {
            setSwitching(false);
          }
        }}
        accessibilityRole="button"
        style={({ pressed }) => [styles.accountBtn, pressed && styles.accountBtnPressed]}
      >
        <Text style={styles.accountBtnText}>{switching ? '전환 중…' : '보호자 모드로 전환'}</Text>
      </Pressable>
      <Pressable
        onPress={signOut}
        accessibilityRole="button"
        style={({ pressed }) => [styles.accountBtn, pressed && styles.accountBtnPressed]}
      >
        <Text style={[styles.accountBtnText, styles.logoutText]}>로그아웃</Text>
      </Pressable>
    </View>
  </ScrollView></SafeAreaView>;
}
function Metric({ label, value, color: accent }: { label: string; value: string; color: string }) { return <View style={styles.metric}><Text style={styles.metricLabel}>{label}</Text><Text style={[styles.metricValue, { color: accent }]}>{value}</Text></View>; }
const styles = StyleSheet.create({
  account: { marginHorizontal: 16, borderRadius: 10, backgroundColor: '#F8F8F8', paddingHorizontal: 14, paddingVertical: 4 },
  accountRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 11 },
  accountKey: { fontFamily: type.family, fontSize: 12, color: '#909090' },
  accountVal: { flex: 1, textAlign: 'right', fontFamily: type.familySemiBold, fontSize: 13, color: '#4D4D4D', marginLeft: 12 },
  accountBtn: { paddingVertical: 12, borderTopWidth: 1, borderTopColor: '#EDEDED' },
  accountBtnPressed: { opacity: 0.6 },
  accountBtnText: { fontFamily: type.familySemiBold, fontSize: 13, color: color.brand },
  logoutText: { color: '#909090' },
  safe: { flex: 1, backgroundColor: '#FFFFFF' }, content: { paddingHorizontal: 23, paddingTop: 27, paddingBottom: 40 }, title: { fontFamily: type.familyBold, fontSize: 20, color: '#000000' }, hero: { height: 103, borderRadius: 10, backgroundColor: color.figmaField, marginTop: 14 },
  metrics: { flexDirection: 'row', gap: 15, marginTop: 30 }, metric: { flex: 1, height: 50, borderRadius: 10, backgroundColor: color.figmaField, alignItems: 'center', justifyContent: 'center' }, metricLabel: { fontFamily: type.family, fontSize: 10, color: color.figmaGray }, metricValue: { fontFamily: type.familyBold, fontSize: 18, marginTop: 2 },
  section: { fontFamily: type.familySemiBold, fontSize: 18, color: '#000000', marginTop: 40 }, recentSection: { marginTop: 31 }, badges: { height: 103, borderRadius: 10, backgroundColor: color.figmaField, marginTop: 11, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around' }, badge: { alignItems: 'center', width: 70 }, badgeIcon: { fontSize: 28 }, badgeLabel: { fontFamily: type.family, fontSize: 10, color: '#525253', marginTop: 3, textAlign: 'center' },
  recent: { height: 73, borderRadius: 10, backgroundColor: color.figmaField, marginTop: 12, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center' }, recentTitle: { fontFamily: type.familySemiBold, fontSize: 15, color: '#525253' }, recentDate: { fontFamily: type.family, fontSize: 10, color: color.figmaGray, marginTop: 8 }, km: { position: 'absolute', left: 100, top: 17, minWidth: 62, borderRadius: 10, backgroundColor: '#D7D7D7', paddingHorizontal: 10, paddingVertical: 2, fontFamily: type.family, fontSize: 10, color: '#525253' }, chevron: { position: 'absolute', right: 16, fontFamily: type.family, fontSize: 26, color: color.guardian },
});
