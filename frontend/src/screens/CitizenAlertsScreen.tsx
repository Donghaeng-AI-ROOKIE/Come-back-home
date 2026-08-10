import React from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useActiveAlerts } from '../hooks/queries';
import { color, type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';

export default function CitizenAlertsScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data, isLoading, isError, refetch } = useActiveAlerts();
  const alerts = data ?? [];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>긴급 수색 알림</Text>
        <Text style={styles.subtitle}>현재 내 주변 반경과 AI 예상 동선이 겹치는 실종 사건 목록입니다</Text>
        {isLoading ? <ActivityIndicator color={color.figmaRed} style={styles.loading} /> : null}
        {isError ? <Pressable style={styles.empty} onPress={() => refetch()}><Text style={styles.emptyText}>경보를 불러오지 못했습니다.{`\n`}눌러서 다시 시도해 주세요.</Text></Pressable> : null}
        {!isLoading && !isError && alerts.length === 0 ? <View style={styles.empty}><Text style={styles.emptyText}>현재 내 주변에 진행 중인 수색 알림이 없습니다.</Text></View> : null}
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
      </ScrollView>
    </SafeAreaView>
  );
}

function AlertCard({ tone, badge, title, body, onPress }: { tone: 'red' | 'green'; badge: string; title: string; body: string; onPress: () => void }) {
  const red = tone === 'red';
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.card, red ? styles.redCard : styles.greenCard, pressed && styles.pressed]}>
      <View style={[styles.badge, red ? styles.redBadge : styles.greenBadge]}><Text style={[styles.badgeText, red ? styles.redBadgeText : styles.greenBadgeText]}>{badge}</Text></View>
      <Text style={styles.cardTitle}>{title}</Text>
      <Text style={styles.cardBody}>{body}</Text>
      <Text style={[styles.chevron, { color: red ? color.figmaRed : '#286C45' }]}>›</Text>
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
