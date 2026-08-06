/**
 * 네비게이션 참조 — React 트리 **밖**에서 화면을 이동시켜야 할 때 쓴다.
 *
 * 푸시 알림 탭 처리가 그 경우다. 알림은 앱이 꺼져 있거나 백그라운드일 때 도착하고,
 * 그 콜백은 어떤 화면의 컴포넌트 안에서 도는 게 아니라 앱 전역에서 돈다.
 */
import { createNavigationContainerRef } from '@react-navigation/native';
import type { RootStackParamList } from './types';

export const navigationRef = createNavigationContainerRef<RootStackParamList>();

/** 네비게이터가 아직 안 떴으면 조용히 무시한다 — 앱 부팅 중 알림을 탭한 경우. */
export function navigateWhenReady<T extends keyof RootStackParamList>(
  ...args: undefined extends RootStackParamList[T]
    ? [name: T, params?: RootStackParamList[T]]
    : [name: T, params: RootStackParamList[T]]
): boolean {
  if (!navigationRef.isReady()) return false;
  // v7 의 navigate 오버로드가 가변 인자를 좁히지 못해 여기서만 단언한다.
  (navigationRef.navigate as (...a: unknown[]) => void)(...args);
  return true;
}
