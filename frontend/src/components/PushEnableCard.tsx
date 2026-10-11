import React from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { color, type } from '../theme/tokens';
import { useWebPush } from '../hooks/useWebPush';
import { retryLocation } from '../hooks/useMyLocation';

export default function PushEnableCard({ compact = false }: { compact?: boolean }) {
  const { status, enable, test, disable, error, message, location } = useWebPush();
  if (Platform.OS !== 'web') return null;
  const subscribed = status === 'subscribed';
  const title = {
    'needs-install': '아이폰 알림 · 홈 화면에 추가',
    denied: '알림 권한을 허용해 주세요',
    unsupported: '이 브라우저는 웹 알림을 지원하지 않아요',
    disabled: '알림 서버 연결을 준비 중이에요',
    subscribed: '주변 실종자 알림 연결됨',
    working: '알림 연결 확인 중…',
    idle: '주변 실종자 알림 받기',
  }[status];
  return (
    <View style={[styles.card, compact && styles.compact]}>
      <Text style={styles.title}>{title}</Text>
      {status === 'needs-install' ? <Text style={styles.body}>
        Safari 공유 → 홈 화면에 추가 후, 설치된 돌아오길 아이콘에서 알림을 켜 주세요.
      </Text> : status === 'denied' ? <Text style={styles.body}>
        아이폰 설정 → 알림 → 돌아오길에서 알림을 허용해 주세요.
      </Text> : <Text style={styles.body}>
        화면을 열고 이동하면 알림 대상 구역 진입을 확인해요. 화면을 닫으면 위치 갱신이 멈출 수 있어요.
      </Text>}
      {!compact ? <Text style={styles.body}>
        주변 알림을 고르기 위해 현재 위치를 작은 구역 번호로 바꿔 보내요. 좌표와 이동 경로는 보내지 않으며 이전 구역 번호는 덮어써요.
      </Text> : null}
      {!compact && subscribed ? <Text style={styles.body}>
        화면을 닫은 뒤에는 5분 이내 확인한 위치를 기준으로 새 실종 경보를 받아요.
      </Text> : null}
      <View style={styles.actions}>
        {status === 'idle' ? <Pressable accessibilityRole="button" onPress={enable} style={styles.button}>
          <Text style={styles.buttonText}>알림 켜기</Text>
        </Pressable> : null}
        {subscribed ? <>
          <Pressable accessibilityRole="button" onPress={test} style={styles.button}><Text style={styles.buttonText}>시험 알림</Text></Pressable>
          <Pressable accessibilityRole="button" onPress={disable} style={styles.secondary}><Text style={styles.body}>알림 끄기</Text></Pressable>
        </> : null}
        {location.status !== 'granted' ? <Pressable accessibilityRole="button" onPress={retryLocation} style={styles.secondary}>
          <Text style={styles.body}>위치 확인하기</Text>
        </Pressable> : null}
      </View>
      {location.status === 'granted' && location.accuracyM != null && location.accuracyM > 80 ?
        <Text style={styles.body}>위치 오차가 커서 구역 진입 확인을 기다리고 있어요. 실외에서 다시 확인해 주세요.</Text> : null}
      {message ? <Text accessibilityLiveRegion="polite" style={styles.body}>{message}</Text> : null}
      {error ? <Text accessibilityLiveRegion="polite" style={styles.error}>{error}</Text> : null}
    </View>
  );
}
const styles = StyleSheet.create({
  card: { marginHorizontal: 16, marginTop: 12, padding: 14, borderRadius: 12, backgroundColor: '#ECFAE5', gap: 6 },
  compact: { marginTop: 4, marginBottom: 6, paddingVertical: 8 },
  title: { fontFamily: type.familyCssExtraBold, fontSize: 14, color: '#316837' },
  body: { fontFamily: type.family, fontSize: 12, lineHeight: 18, color: '#525253' },
  error: { fontFamily: type.family, fontSize: 11, color: color.criticalInk },
  actions: { flexDirection: 'row', gap: 12, alignItems: 'center', flexWrap: 'wrap' },
  button: { minHeight: 40, paddingHorizontal: 16, borderRadius: 10, backgroundColor: color.brand, justifyContent: 'center' },
  secondary: { minHeight: 40, justifyContent: 'center' },
  buttonText: { fontFamily: type.familyCssExtraBold, fontSize: 13, color: '#FFFFFF' },
});
