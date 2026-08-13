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
import { isLocationSettled, retryLocation, useMyLocation } from '../hooks/useMyLocation';
import { useAppModeStore } from '../store/appModeStore';

/**
 * 서버 주소가 `[서울특별시 마포구] 월드컵로`처럼 행정구역만 묶여 와도
 * 화면에서는 주소 전체를 하나의 대괄호 안에 표시한다.
 */
function bracketAddress(area: string): string {
  const address = area.replace(/[\[\]]/g, ' ').replace(/\s+/g, ' ').trim();
  return `[${address}]`;
}

export default function CitizenAlertsScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data, isLoading, isError, refetch } = useActiveAlerts();
  // AlertDetailScreen의 "이 사건은 그만 볼래요"(dismissCase)는 재촉 UI(넛지)만
  // 끄려던 의도였지만(appModeStore 주석 참고), 실제 화면 흐름상 사용자는 이 버튼을
  // "목록에서 지우기"로 이해한다 — 눌러도 카드가 그대로 남으면 안 먹힌 것처럼
  // 보인다(현장 제보). 여기서 dismissedCases 를 반영해 목록에서도 제거한다.
  const dismissedCases = useAppModeStore((s) => s.dismissedCases);
  const alerts = (data ?? []).filter((alert) => dismissedCases[alert.caseId] === undefined);
  // 상황 종료 카드(시안) — 활성 경보와 **같은 칸**으로 물어 온 최근 발견 사건.
  // 실패해도 화면을 막지 않는다: 이건 결과 알림이지 골든타임 정보가 아니다.
  const resolved = useResolvedAlerts().data ?? [];
  /**
   * 위치를 못 잡은 상태 — "주변에 사건이 없다"와 **반드시 구분해야 한다.**
   *
   * 목록 조회는 내 res7 칸을 서버에 보내고 서버가 고르는 구조라, 위치가 없으면
   * 아예 묻지 않고 빈 배열이 된다(fail-closed). 그런데 화면은 그걸 "진행 중인
   * 수색 알림이 없습니다"로 보여줬다 — **거짓말이다.** 실제로는 알 수 없는 것이다.
   *
   * 현장 제보(08-12): 푸시는 잠금화면까지 잘 왔는데 앱 목록만 비어 있었다.
   * 푸시는 구독할 때 저장해 둔 칸으로 나가고 목록은 실시간 위치를 쓰기 때문에,
   * 위치가 끊긴 순간 둘이 갈린다. 그때 "없습니다"가 뜨면 아무도 원인을 못 찾는다.
   */
  const { point, status: locStatus, message: locMessage } = useMyLocation(true);
  const locationBlocked = point == null && isLocationSettled(locStatus);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>긴급 수색 알림</Text>
        <Text style={styles.subtitle}>현재 내 주변 반경과 AI 예상 동선이 겹치는 실종 사건 목록입니다</Text>
        {isLoading ? <ActivityIndicator color={color.figmaRed} style={styles.loading} /> : null}
        {isError ? <Pressable style={styles.empty} onPress={() => refetch()}><Text style={styles.emptyText}>경보를 불러오지 못했습니다.{`\n`}눌러서 다시 시도해 주세요.</Text></Pressable> : null}
        {/* 위치가 없으면 **"없다"가 아니라 "모른다"** 라고 말한다. 이 화면은 내 칸을
            서버에 보내고 서버가 고르는 구조라, 위치가 없으면 판단 자체가 불가능하다. */}
        {locationBlocked ? (
          /* 누를 수 있어야 한다. 첫 시도가 실패하면 앱은 다시 묻지 않는데
             (useMyLocation.retryLocation 주석), 사용자가 팝업을 놓치는 일은
             흔하다 — 손가락으로 다시 부를 길을 준다. iOS 는 사용자 조작 직후에
             권한 팝업이 가장 잘 뜨기도 한다. */
          <Pressable style={styles.empty} onPress={retryLocation} accessibilityRole="button">
            <Text style={styles.emptyText}>
              위치를 확인할 수 없어 주변 사건을 불러오지 못했습니다.{`\n\n`}
              <Text style={styles.emptyAction}>눌러서 위치 권한 다시 요청하기</Text>
              {/* 눌렀는데 왜 안 되는지를 **화면이 말해야 한다.** 권한 거부·기기
                  위치서비스 꺼짐·실내 시간초과는 해야 할 일이 각각 다르다. */}
              {locMessage ? `\n\n${locMessage}` : ''}
            </Text>
          </Pressable>
        ) : null}
        {/* 빈 안내는 **양쪽 다 없을 때만** 띄운다 — 종결 카드만 있는 상태에서
            "알림이 없습니다"가 그 위에 뜨면 화면이 스스로 모순된다. */}
        {!isLoading && !isError && !locationBlocked && alerts.length === 0 && resolved.length === 0 ? <View style={styles.empty}><Text style={styles.emptyText}>현재 내 주변에 진행 중인 수색 알림이 없습니다.</Text></View> : null}
        {alerts.map((alert) => (
          <AlertCard
            key={alert.caseId}
            tone="red"
            badge={`수색 중(${alert.targetCells.length}개 대상 구역)`}
            title={`${bracketAddress(alert.area || '최종 목격 위치 기준')}${alert.age ? ` ${alert.age}세` : ''} 실종 어르신`}
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
            title={`${bracketAddress(r.area)}${r.age ? ` ${r.age}세` : ''} 어르신`}
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
  title: { marginLeft: -3, fontFamily: type.familyCssExtraBold, fontSize: 18, lineHeight: 22, color: '#000000' },
  subtitle: { marginLeft: -3, marginTop: 14, marginBottom: 39, fontFamily: type.familyCssSemiBold, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: color.figmaGray },
  card: { height: 139, borderRadius: 10, paddingHorizontal: 16, paddingTop: 20, marginBottom: 28, position: 'relative', shadowColor: '#000000', shadowOpacity: 0.1, shadowRadius: 7, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  redCard: { backgroundColor: '#FFF0F1' },
  greenCard: { backgroundColor: '#ECFAE5' },
  badge: { alignSelf: 'flex-start', height: 16, borderRadius: 8, paddingHorizontal: 11, alignItems: 'center', justifyContent: 'center' },
  redBadge: { backgroundColor: '#FFC9CB' },
  greenBadge: { backgroundColor: '#BDE6A9' },
  badgeText: { fontFamily: type.familyCssBold, fontSize: 10, lineHeight: 13, letterSpacing: 0.07 },
  redBadgeText: { color: color.figmaRed },
  greenBadgeText: { color: '#286C45' },
  cardTitle: { marginTop: 15, fontFamily: type.familyCssBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#525253' },
  cardBody: { marginTop: 7, fontFamily: type.familyCss, fontSize: 11, lineHeight: 13, letterSpacing: 0.07, color: '#525253' },
  chevron: { position: 'absolute', right: 17, top: 17, fontFamily: type.familyCss, fontSize: 28, lineHeight: 30 },
  pressed: { opacity: 0.82 },
  loading: { marginTop: 70 },
  empty: { minHeight: 120, borderRadius: 10, backgroundColor: '#F7F7F7', alignItems: 'center', justifyContent: 'center', padding: 20 },
  emptyText: { fontFamily: type.familyCss, fontSize: 12, lineHeight: 18, color: color.figmaGray, textAlign: 'center' },
  emptyAction: { color: color.brand, textDecorationLine: 'underline', fontFamily: type.familyCssSemiBold },
});
