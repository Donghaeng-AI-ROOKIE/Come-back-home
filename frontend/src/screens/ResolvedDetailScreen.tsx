import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { StyleProp, TextStyle, ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';
import FigmaFlowTabBar from '../components/FigmaFlowTabBar';
import { resolvedTitle } from '../utils/alertTitle';
import { resolvedMessage, resolvedThanks } from '../utils/resolvedCopy';
import { formatSearchDuration } from '../utils/searchDuration';
import { serverTimeMs } from '../utils/walkFormat';

/**
 * 상황 종료 상세 — 긴급 수색 알림 목록의 초록 카드를 누르면 열린다(IA 리뷰 10/26).
 *
 * 경보를 받고 주변을 살핀 시민에게 **결말**을 알려 주는 화면이다. 그래서 숫자
 * (수색 시간·시민 제보·종결 시각)와 감사만 둔다.
 *
 * 이름·인상착의·지도·최종 목격 위치는 **그리지 않는다.** 이미 찾은 사람을 찾는 데
 * 쓰던 정보이고, 파기를 기다리는 개인정보다. 종결 응답(describe_resolved)에도
 * 애초에 없다 — 이 화면은 목록 카드가 넘긴 값만 쓰고 서버를 다시 부르지 않는다.
 */
export default function ResolvedDetailScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { params } = useRoute<RouteProp<RootStackParamList, 'ResolvedDetail'>>();
  const tipCount = asNumber(params.tipCount);
  const duration = formatSearchDuration(asNumber(params.searchMinutes));
  // 서버 시각은 오프셋 없이 오므로 walkFormat 의 규칙(serverTimeMs)으로 읽는다.
  const closedMs = params.closedAt ? serverTimeMs(params.closedAt) : Number.NaN;
  const closedLabel = Number.isNaN(closedMs)
    ? null
    : new Date(closedMs).toLocaleString('ko-KR', { month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' });

  // 웹에서 이 화면을 새로고침하면 돌아갈 기록이 없다 — 그때는 긴급알림 탭으로 보낸다.
  const backToList = () => {
    if (navigation.canGoBack()) navigation.goBack();
    else navigation.navigate('CitizenTabs', { screen: 'Alerts' });
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>긴급 수색 알림</Text>
        <Text style={styles.subtitle}>내 주변에서 진행된 실종자 수색의 결과입니다</Text>

        {/* 목록의 초록 카드와 같은 색·배지·제목 — 눌렀던 카드가 펼쳐진 것으로 읽혀야 한다. */}
        <View style={styles.hero}>
          <View style={styles.badge}><Text style={styles.badgeText}>상황 종료</Text></View>
          <Text style={[styles.heroTitle, keepWords]} lineBreakStrategyIOS="hangul-word">{resolvedTitle(params.area || '내 주변', asNumber(params.age))}</Text>
          <Text style={[styles.heroMessage, keepWords]} lineBreakStrategyIOS="hangul-word">{resolvedMessage(tipCount)}</Text>
        </View>

        {/* 종결 시각은 "10월 27일 오후 4:10"처럼 길어서 반쪽 칸에 들어가지 않는다 — 한 줄을 다 쓴다. */}
        <View style={styles.metricRow}>
          <Metric label="수색 시간" value={duration ?? '-'} style={styles.metricHalf} />
          <Metric label="시민 제보" value={tipCount == null ? '-' : `${tipCount}건`} style={styles.metricHalf} />
        </View>
        <Metric label="종결 시각" value={closedLabel ?? '-'} style={styles.metricWide} />

        <Text style={styles.thanks}>{resolvedThanks(tipCount)}</Text>
        <Text style={styles.notice}>이 사건 정보는 종결 5일 뒤 자동으로 파기됩니다.</Text>

        <Pressable
          style={({ pressed }) => [styles.primary, pressed && styles.pressed]}
          onPress={backToList}
          accessibilityRole="button"
        >
          <Text style={styles.primaryText}>목록으로</Text>
        </Pressable>
      </ScrollView>
      <FigmaFlowTabBar mode="citizen" active="alert" />
    </SafeAreaView>
  );
}

/** 웹에서 새로고침하면 params 가 URL 쿼리에서 문자열로 돌아온다 — 숫자로 되돌린다. */
function asNumber(value: unknown): number | undefined {
  if (value == null || value === '') return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

function Metric({ label, value, style }: { label: string; value: string; style?: StyleProp<ViewStyle> }) {
  return (
    <View style={[styles.metric, style]}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

// 한글이 음절 단위로 끊기면 "돌아갔/습니다"처럼 읽힌다 — 어절 단위로 줄을 바꾼다.
// 웹은 CSS word-break(RN 타입에는 없어 캐스팅), iOS 는 lineBreakStrategyIOS 로 맞춘다.
const keepWords = (Platform.OS === 'web' ? { wordBreak: 'keep-all' } : null) as TextStyle | null;

// 목록(CitizenAlertsScreen)의 상황 종료 카드 색.
const greenWash = '#ECFAE5';
const greenBadge = '#BDE6A9';
const greenInk = '#286C45';

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' },
  content: { paddingHorizontal: 23, paddingTop: 27, paddingBottom: 30 },
  title: { marginLeft: -3, fontFamily: type.familyCssExtraBold, fontSize: 18, lineHeight: 22, color: '#000000' },
  subtitle: { marginLeft: -3, marginTop: 14, marginBottom: 28, fontFamily: type.familyCssSemiBold, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: color.figmaGray },
  hero: { borderRadius: 10, paddingHorizontal: 16, paddingTop: 20, paddingBottom: 22, backgroundColor: greenWash, shadowColor: '#000000', shadowOpacity: 0.1, shadowRadius: 7, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  badge: { alignSelf: 'flex-start', height: 16, borderRadius: 8, paddingHorizontal: 11, backgroundColor: greenBadge, alignItems: 'center', justifyContent: 'center' },
  badgeText: { fontFamily: type.familyCssBold, fontSize: 10, lineHeight: 13, letterSpacing: 0.07, color: greenInk },
  heroTitle: { marginTop: 15, fontFamily: type.familyCssBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#525253' },
  heroMessage: { marginTop: 10, fontFamily: type.familyCssSemiBold, fontSize: 14, lineHeight: 20, color: greenInk },
  metricRow: { marginTop: 24, flexDirection: 'row', gap: 15 },
  metric: { height: 64, borderRadius: 10, backgroundColor: color.figmaField, alignItems: 'center', justifyContent: 'center' },
  metricHalf: { flex: 1 },
  metricWide: { marginTop: 12 },
  metricLabel: { fontFamily: type.familyCssSemiBold, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: color.figmaGray },
  metricValue: { marginTop: 6, fontFamily: type.familyCssExtraBold, fontSize: 18, lineHeight: 23, color: '#000000' },
  thanks: { marginTop: 28, textAlign: 'center', fontFamily: type.familyCssBold, fontSize: 15, lineHeight: 20, color: greenInk },
  notice: { marginTop: 8, textAlign: 'center', fontFamily: type.familyCssSemiBold, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: color.figmaGray },
  primary: { marginTop: 28, marginHorizontal: -13, height: 58, borderRadius: 30, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center', shadowColor: '#000000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  primaryText: { fontFamily: type.familyCssBold, fontSize: 20, lineHeight: 25, letterSpacing: 0.38, color: '#FFFFFF' },
  pressed: { opacity: 0.82 },
});
