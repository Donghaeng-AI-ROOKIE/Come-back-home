import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { color, type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';
import { useGuardianCases } from '../hooks/queries';
import type { Case } from '../api/guardian';

function locationLabel(item: Case) {
  return `[최종 목격 위치] ${item.lkp.lat.toFixed(4)}, ${item.lkp.lng.toFixed(4)}`;
}

function trustLabel(item: Case) {
  const scores = item.tips.map((tip) => tip.p).filter((p): p is number => typeof p === 'number');
  if (!scores.length) return '검토 중';
  const best = Math.max(...scores);
  return best >= 0.8 ? '신뢰도 상' : best >= 0.5 ? '신뢰도 중' : '신뢰도 낮음';
}

export default function GuardianAlertsScreen() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data, isLoading, isError, refetch } = useGuardianCases();
  const cases = data ?? [];
  const selected = cases.find((item) => item.id === selectedId) ?? null;

  return (
    <View style={styles.root}>
      <FigmaStatusBar />
      <View style={styles.canvas}>
        {selected == null ? (
          <>
            <Text style={styles.title}>제보 알림</Text>
            <Text style={styles.subtitle}>주변 시민들의 실제 제보입니다.</Text>
            {isLoading ? <ActivityIndicator color={color.guardian} style={styles.loading} /> : null}
            {isError ? <Pressable style={styles.empty} onPress={() => refetch()}><Text style={styles.emptyText}>제보를 불러오지 못했습니다.{`\n`}눌러서 다시 시도해 주세요.</Text></Pressable> : null}
            {!isLoading && !isError && cases.length === 0 ? <View style={styles.empty}><Text style={styles.emptyText}>진행 중인 사건 또는 접수된 제보가 없습니다.</Text></View> : null}
            {cases.map((item, index) => (
              <Pressable key={item.id} style={[styles.alertCard, { top: 115 + index * 143 }]} onPress={() => setSelectedId(item.id)}>
                <View style={styles.trust}><Text style={styles.trustText}>{trustLabel(item)}</Text></View>
                <Text style={styles.cardTitle} numberOfLines={1}>{locationLabel(item)}</Text>
                <Text style={styles.cardBody}>해당 사건에 총 {item.tips.length}건의 제보가 있습니다.</Text>
                <Text style={styles.chevron}>›</Text>
              </Pressable>
            ))}
          </>
        ) : (
          <>
            <View style={styles.header}>
              <Pressable style={styles.back} onPress={() => setSelectedId(null)}><Text style={styles.backText}>‹</Text></Pressable>
              <Text style={styles.headerTitle}>상세 제보</Text>
            </View>
            <View style={styles.locationCard}><Text style={styles.locationText} numberOfLines={2}>{locationLabel(selected)}</Text></View>
            <Text style={styles.reportCount}>제보 {selected.tips.length}건</Text>
            {selected.tips.length === 0 ? <View style={[styles.empty, styles.detailEmpty]}><Text style={styles.emptyText}>아직 접수된 시민 제보가 없습니다.</Text></View> : null}
            {selected.tips.map((tip, index) => (
              <View key={tip.id} style={[styles.reportCard, { top: 158 + index * 81 }]}>
                <Text style={styles.reportDate}>{new Date(tip.seen_at || tip.created_at).toLocaleString('ko-KR')}</Text>
                <Text style={styles.reportText} numberOfLines={2}>{tip.text}</Text>
              </View>
            ))}
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  canvas: { flex: 1, position: 'relative' },
  title: { position: 'absolute', left: 20, top: 27, fontFamily: type.family, fontSize: 18, lineHeight: 23, fontWeight: '800', color: '#000000' },
  subtitle: { position: 'absolute', left: 20, top: 63, fontFamily: type.family, fontSize: 11, lineHeight: 13, fontWeight: '500', color: '#8E8E93' },
  loading: { position: 'absolute', top: 150, left: 0, right: 0 },
  empty: { position: 'absolute', left: 23, right: 22, top: 115, minHeight: 100, borderRadius: 10, backgroundColor: '#F7F7F7', alignItems: 'center', justifyContent: 'center', padding: 16 },
  detailEmpty: { top: 158 },
  emptyText: { fontFamily: type.family, fontSize: 12, lineHeight: 18, color: '#8E8E93', textAlign: 'center' },
  alertCard: { position: 'absolute', left: 23, right: 22, height: 115, borderRadius: 10, backgroundColor: '#F7F7F7', shadowColor: '#000', shadowOpacity: 0.1, shadowRadius: 10, shadowOffset: { width: 1, height: 1 } },
  trust: { position: 'absolute', left: 16, top: 15, height: 16, minWidth: 59, paddingHorizontal: 10, borderRadius: 20, backgroundColor: '#B0DB9C', alignItems: 'center', justifyContent: 'center' },
  trustText: { fontFamily: type.family, fontSize: 10, lineHeight: 13, fontWeight: '700', color: '#316837' },
  cardTitle: { position: 'absolute', left: 16, right: 28, top: 41, fontFamily: type.family, fontSize: 17, lineHeight: 22, fontWeight: '700', color: '#525253' },
  cardBody: { position: 'absolute', left: 16, top: 70, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#525253' },
  chevron: { position: 'absolute', right: 14, top: 19, fontSize: 24, color: '#67AE6E' },
  header: { position: 'absolute', left: 0, right: 0, top: 0, height: 48, backgroundColor: '#FFFFFF', justifyContent: 'center', alignItems: 'center' },
  headerTitle: { fontFamily: type.family, fontSize: 18, lineHeight: 23, fontWeight: '600', color: '#000000' },
  back: { position: 'absolute', left: 12, top: 10, width: 24, height: 28, justifyContent: 'center' },
  backText: { fontSize: 34, lineHeight: 28, color: '#8E8E93', fontWeight: '300' },
  locationCard: { position: 'absolute', left: 23, right: 22, top: 59, height: 51, borderRadius: 10, backgroundColor: '#F7F7F7', justifyContent: 'center', paddingHorizontal: 16 },
  locationText: { fontFamily: type.family, fontSize: 15, lineHeight: 19, fontWeight: '700', color: '#525253' },
  reportCount: { position: 'absolute', left: 26, top: 131, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#525253' },
  reportCard: { position: 'absolute', left: 23, right: 22, height: 66, borderRadius: 8, backgroundColor: '#F8F8F8', paddingHorizontal: 16, paddingTop: 12 },
  reportDate: { fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#4D4D4D' },
  reportText: { fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#4D4D4D', marginTop: 9 },
});
