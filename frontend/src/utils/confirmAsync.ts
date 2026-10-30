import { Alert, Platform } from 'react-native';

/** 확인 창 — 웹(부스 폰은 Pages 웹앱)은 Alert 버튼이 안 떠서 window.confirm 을 쓴다. */
export function confirmAsync(title: string, message: string): Promise<boolean> {
  if (Platform.OS === 'web') return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  return new Promise((resolve) => Alert.alert(title, message, [
    { text: '취소', style: 'cancel', onPress: () => resolve(false) },
    { text: '확인', style: 'destructive', onPress: () => resolve(true) },
  ], { cancelable: true, onDismiss: () => resolve(false) }));
}
