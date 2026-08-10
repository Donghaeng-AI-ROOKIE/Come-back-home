import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';

const reports = [
  { place: '[서울시 마포구] 대흥역 4번 출구 근처', count: 4, trust: '신뢰도 상' },
  { place: '[서울시 마포구] 경의선 숲길', count: 1, trust: '신뢰도 중' },
];

export default function GuardianAlertsScreen() {
  const [selected, setSelected] = useState<number | null>(null);
  return (
    <View style={styles.root}>
      <FigmaStatusBar />
      <View style={styles.canvas}>
        {selected == null ? (
          <>
            <Text style={styles.title}>제보 알림</Text>
            <Text style={styles.subtitle}>주변 시민들의 제보입니다.</Text>
            {reports.map((item, index) => (
              <Pressable key={item.place} style={[styles.alertCard, { top: 115 + index * 143 }]} onPress={() => setSelected(index)}>
                <View style={styles.trust}><Text style={styles.trustText}>{item.trust}</Text></View>
                <Text style={styles.cardTitle}>{item.place}</Text>
                <Text style={styles.cardBody}>해당 위치에서 총 {item.count}건의 제보가 있습니다.</Text>
                <Text style={styles.chevron}>›</Text>
              </Pressable>
            ))}
          </>
        ) : (
          <>
            <View style={styles.header}>
              <Pressable style={styles.back} onPress={() => setSelected(null)}><Text style={styles.backText}>‹</Text></Pressable>
              <Text style={styles.headerTitle}>상세 제보</Text>
            </View>
            <View style={styles.locationCard}><Text style={styles.locationText}>{reports[selected].place}</Text></View>
            <Text style={styles.reportCount}>제보 {reports[selected].count}건</Text>
            {Array.from({ length: reports[selected].count }).map((_, index) => (
              <View key={index} style={[styles.reportCard, { top: 158 + index * 81 }]}>
                <Text style={styles.reportDate}>2026/8/10 15:37</Text>
                <Text style={styles.reportText}>제보 텍스트</Text>
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
  locationText: { fontFamily: type.family, fontSize: 17, lineHeight: 22, fontWeight: '700', color: '#525253' },
  reportCount: { position: 'absolute', left: 26, top: 131, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#525253' },
  reportCard: { position: 'absolute', left: 23, right: 22, height: 66, borderRadius: 8, backgroundColor: '#F8F8F8', paddingHorizontal: 16, paddingTop: 12 },
  reportDate: { fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#4D4D4D' },
  reportText: { fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#4D4D4D', marginTop: 9 },
});
