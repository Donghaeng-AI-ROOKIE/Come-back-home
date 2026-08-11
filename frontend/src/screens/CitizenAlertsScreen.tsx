import React from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useActiveAlerts, useResolvedAlerts } from '../hooks/queries';
import { color, type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';

export default function CitizenAlertsScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data, isLoading, isError, refetch } = useActiveAlerts();
  const alerts = data ?? [];
  // 상황 종료 카드(시안) — 활성 경보와 **같은 칸**으로 물어 온 최근 발견 사건.
  // 실패해도 화면을 막지 않는다: 이건 결과 알림이지 골든타임 정보가 아니다.
  const resolved = useResolvedAlerts().data ?? [];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>긴급 수색 알림</Text>
        <Text style={styles.subtitle}>현재 내 주변 반경과 AI 예상 동선이 겹치는 실종 사건 목록입니다</Text>
        {isLoading ? <ActivityIndicator color={color.figmaRed} style={styles.loading} /> : null}
        {isError ? <Pressable style={styles.empty} onPress={() => refetch()}><Text style={styles.emptyText}>경보를 불러오지 못했습니다.{`\n`}눌러서 다시 시도해 주세요.</Text></Pressable> : null}
        {/* 빈 안내는 **양쪽 다 없을 때만** 띄운다 — 종결 카드만 있는 상태에서
            "알림이 없습니다"가 그 위에 뜨면 화면이 스스로 모순된다. */}
        {!isLoading && !isError && alerts.length === 0 && resolved.length === 0 ? <View style={styles.empty}><Text style={styles.emptyText}>현재 내 주변에 진행 중인 수색 알림이 없습니다.</Text></View> : null}
        {alerts.map((alert) => (
          <AlertCard
            key={alert.caseId}
            tone="red"
            badge={`수색 중(${alert.targetCells.length}개 대상 구역)`}
            title={`${alert.age ? `${alert.age}세 ` : ''}실종 어르신 · ${alert.area || '최종 목격 위치 기준'}`}
            body={`${alert.summary || '인상착의 정보 확인 중'}\n터치하여 예상 구역을 확인해 주세요.`}
            onPress={() => navigation.navigate('AlertDetail', { caseId: alert.caseId })}
          />
        ))}
        {/* 상황 종료 — 시안의 초록 카드. 진행 중 사건 **아래**에 둔다:
            지금 찾아야 할 것이 먼저고, 결과는 그다음이다.
            누를 곳이 없다(수색 화면으로 보낼 이유가 없는 끝난 사건이다). */}
        {resolved.map((r) => (
          <AlertCard
            key={r.caseId}
            tone="green"
            badge="상황 종료"
            title={`${r.area}${r.age ? ` ${r.age}세` : ''} 어르신`}
            body={'시민 제보를 통해 가족의 품으로 무사히 돌아갔습니다.\n제보해 주셔서 감사합니다.'}
          />
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

/**
 * 시안의 알림 카드. tone 이 색과 배지를 가른다(빨강=수색 중, 초록=상황 종료).
 *
 * `onPress` 가 없으면 **꺾쇠(›)도 그리지 않는다.** 종결 카드는 열 곳이 없는데
 * (끝난 사건을 수색 화면으로 보낼 수는 없다) 꺾쇠만 남기면 눌러도 아무 일이
 * 없는 표식이 된다 — 시안의 꺾쇠를 지킨 대가로 "눌리지 않는다"는 제보를 받게 된다.
 */
function AlertCard({ tone, badge, title, body, onPress }: { tone: 'red' | 'green'; badge: string; title: string; body: string; onPress?: () => void }) {
  const red = tone === 'red';
  const inner = (
    <>
      <View style={[styles.badge, red ? styles.redBadge : styles.greenBadge]}><Text style={[styles.badgeText, red ? styles.redBadgeText : styles.greenBadgeText]}>{badge}</Text></View>
      <Text style={styles.cardTitle}>{title}</Text>
      <Text style={styles.cardBody}>{body}</Text>
      {onPress ? <Text style={[styles.chevron, { color: red ? color.figmaRed : '#286C45' }]}>›</Text> : null}
    </>
  );
  if (!onPress) {
    return <View style={[styles.card, red ? styles.redCard : styles.greenCard]}>{inner}</View>;
  }
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.card, red ? styles.redCard : styles.greenCard, pressed && styles.pressed]}>
      {inner}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  content: { paddingHorizontal: 23, paddingTop: 27, paddingBottom: 30 },
  title: { marginLeft: -3, fontFamily: type.familySemiBold, fontSize: 18, lineHeight: 22, color: '#000000' },
  subtitle: { marginLeft: -3, marginTop: 14, marginBottom: 39, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: color.figmaGray },
  card: { height: 139, borderRadius: 10, paddingHorizontal: 16, paddingTop: 20, marginBottom: 28, position: 'relative', shadowColor: '#000000', shadowOpacity: 0.1, shadowRadius: 7, shadowOffset: { width: 0, height: 2 } },
  redCard: { backgroundColor: '#FFF0F1' },
  greenCard: { backgroundColor: '#ECFAE5' },
  badge: { alignSelf: 'flex-start', height: 16, borderRadius: 8, paddingHorizontal: 11, alignItems: 'center', justifyContent: 'center' },
  redBadge: { backgroundColor: '#FFC9CB' },
  greenBadge: { backgroundColor: '#BDE6A9' },
  badgeText: { fontFamily: type.familyMedium, fontSize: 10, lineHeight: 13 },
  redBadgeText: { color: color.figmaRed },
  greenBadgeText: { color: '#286C45' },
  cardTitle: { marginTop: 15, fontFamily: type.familySemiBold, fontSize: 17, lineHeight: 22, color: '#525253' },
  cardBody: { marginTop: 7, fontFamily: type.family, fontSize: 11, lineHeight: 14, color: '#525253' },
  chevron: { position: 'absolute', right: 17, top: 17, fontFamily: type.family, fontSize: 28, lineHeight: 30 },
  pressed: { opacity: 0.82 },
  loading: { marginTop: 70 },
  empty: { minHeight: 120, borderRadius: 10, backgroundColor: '#F7F7F7', alignItems: 'center', justifyContent: 'center', padding: 20 },
  emptyText: { fontFamily: type.family, fontSize: 12, lineHeight: 18, color: color.figmaGray, textAlign: 'center' },
});
