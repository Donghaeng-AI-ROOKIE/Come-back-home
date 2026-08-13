/**
 * 알림 켜기 카드 — 홈 상단.
 *
 * 지금까지 시민은 앱을 켜 두고 있을 때만 경보를 봤다. 이 카드가 그 사실을 알리고
 * 한 번의 탭으로 실제 OS 알림을 켠다. **이미 켜져 있으면 아무것도 그리지 않는다** —
 * 할 일이 없는 안내는 화면만 차지한다.
 *
 * 아이폰은 홈 화면에 추가해야 알림을 받을 수 있다(iOS 16.4+). 그 경우 "켜기"를
 * 눌러도 소용이 없으므로 버튼 대신 방법을 적는다 — 눌러도 안 되는 버튼이 제일 나쁘다.
 */
import React from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { color, type } from '../theme/tokens';
import { useWebPush } from '../hooks/useWebPush';

export default function PushEnableCard() {
  const { status, enable, error } = useWebPush();

  if (Platform.OS !== 'web') return null;
  if (status === 'subscribed' || status === 'unsupported' || status === 'disabled') return null;

  if (status === 'needs-install') {
    return (
      <View style={styles.card}>
        <Text style={styles.title}>알림을 받으려면 홈 화면에 추가해 주세요</Text>
        <Text style={styles.body}>
          공유 버튼 → &quot;홈 화면에 추가&quot; 를 누르면 앱처럼 설치됩니다.{'\n'}
          설치한 아이콘으로 열어야 실종 경보 알림이 옵니다.
        </Text>
      </View>
    );
  }

  if (status === 'denied') {
    return (
      <View style={styles.card}>
        <Text style={styles.title}>알림이 차단돼 있습니다</Text>
        <Text style={styles.body}>
          브라우저 설정에서 이 사이트의 알림을 허용해 주세요. 차단 상태에서는 앱을
          열어 둔 동안에만 경보를 볼 수 있습니다.
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>실종 경보 알림 받기</Text>
      <Text style={styles.body}>
        켜 두면 앱을 꺼 둬도 주변 실종 경보가 도착합니다. 지금은 앱을 열고 있을 때만
        보입니다.
      </Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Pressable
        accessibilityRole="button"
        onPress={enable}
        disabled={status === 'working'}
        style={({ pressed }) => [styles.button, (pressed || status === 'working') && styles.pressed]}
      >
        <Text style={styles.buttonText}>{status === 'working' ? '켜는 중…' : '알림 켜기'}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 16,
    marginTop: 12,
    padding: 14,
    borderRadius: 12,
    backgroundColor: '#ECFAE5',
    gap: 6,
  },
  title: { fontFamily: type.familyCssExtraBold, fontSize: 14, color: '#316837' },
  body: { fontFamily: type.family, fontSize: 12, lineHeight: 18, color: '#525253' },
  error: { fontFamily: type.family, fontSize: 11, color: color.criticalInk },
  button: {
    marginTop: 4,
    height: 40,
    borderRadius: 10,
    backgroundColor: color.brand,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: { fontFamily: type.familyCssExtraBold, fontSize: 14, color: '#FFFFFF' },
  pressed: { opacity: 0.85 },
});
