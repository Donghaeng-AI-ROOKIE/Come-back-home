/**
 * 사용자에게 한 줄 알리기 — **웹에서도 실제로 보이는** 경로.
 *
 * ## 왜 필요한가
 * React Native Web 은 `Alert.alert` 를 **구현하지 않는다.** 호출해도 아무 일도
 * 일어나지 않고 예외도 없다. 배포본이 웹이라, 앱 곳곳의 오류 안내가 통째로
 * 삼켜지고 있었다.
 *
 * 현장 제보(08-12): 신고 화면에서 "실종 접수"를 눌러도 아무 반응이 없었다.
 * 실제로는 `Alert.alert('마지막 목격 장소가 필요합니다')` 가 불렸는데 웹에서
 * 아무것도 안 뜬 것이다 — 사용자에게는 **버튼이 고장 난 것**으로 보인다.
 * 원인을 말해 주려던 코드가 원인을 감추고 있었다.
 *
 * ## 무엇을 하나
 * 네이티브는 기존 그대로 `Alert.alert`. 웹은 `window.alert` 로 떨어뜨린다.
 * 예쁘지는 않지만 **보이지 않는 것보다 낫다.** 화면 안에 인라인으로 보여줄 수
 * 있는 상황(폼 검증 등)이라면 그쪽이 더 낫고, 이 함수는 그럴 자리가 없는
 * 예외 상황용이다.
 */
import { Alert, Platform } from 'react-native';

export function notify(title: string, message?: string): void {
  if (Platform.OS !== 'web') {
    Alert.alert(title, message);
    return;
  }
  const text = message ? `${title}\n\n${message}` : title;
  if (typeof window !== 'undefined' && typeof window.alert === 'function') {
    window.alert(text);
  } else {
    console.warn('[notify]', text);
  }
}
