/**
 * 알림 수신·탭 처리.
 *
 * 두 가지를 한다.
 *  1. 앱이 떠 있는 동안 도착한 알림을 어떻게 다룰지 (전경 동작)
 *  2. 알림을 탭했을 때 어디로 보낼지 (경보 상세)
 *
 * ## 앱이 꺼진 상태에서 탭한 경우
 * `getLastNotificationResponseAsync()` 로 "앱을 깨운 그 알림"을 한 번 읽는다.
 * 리스너만 달면 앱이 뜨기 전에 발생한 탭을 놓쳐서, 사용자는 알림을 눌렀는데
 * 홈이 뜨는 경험을 하게 된다.
 */
import { useEffect, useRef } from 'react';
import * as Notifications from 'expo-notifications';
import { navigateWhenReady } from '../navigation/navigationRef';
import type { PushPayload } from '../types/domain';

/**
 * 전경(앱이 떠 있을 때) 도착 알림 처리.
 *
 * 배너를 띄운다 — 앱을 보고 있다고 해서 실종 경보를 숨길 이유가 없고, 마침 다른
 * 화면(제보 작성 등)에 있을 수도 있다. 다만 목록에는 남기지 않는다(알림함 중복 방지).
 */
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

function payloadOf(response: Notifications.NotificationResponse): PushPayload | null {
  const data = response.notification.request.content.data as unknown;
  if (!data || typeof data !== 'object') return null;
  const p = data as Partial<PushPayload>;
  return typeof p.case_id === 'string' ? (p as PushPayload) : null;
}

/** 알림 탭 → 경보 상세. 페이로드가 이상하면 아무 데도 안 보낸다(엉뚱한 화면보다 낫다). */
function routeFrom(response: Notifications.NotificationResponse): void {
  const payload = payloadOf(response);
  if (!payload) return;
  navigateWhenReady('AlertDetail', { caseId: payload.case_id });
}

export function useNotificationRouting(): void {
  // 앱을 깨운 알림은 딱 한 번만 처리한다 — 리렌더마다 다시 이동시키면
  // 사용자가 다른 화면으로 빠져나갈 수 없다.
  const handledColdStart = useRef(false);

  useEffect(() => {
    let cancelled = false;
    // 푸시 네이티브 모듈이 없는 환경(웹·Expo Go)에서는 아래 두 호출이 각각
    // UnavailabilityError 를 던진다. 알림 배선 때문에 앱 전체가 깨지면 안 되므로
    // 조용히 물러난다 — 그 환경에서는 애초에 알림이 도착하지 않는다.
    let sub: Notifications.EventSubscription | null = null;

    (async () => {
      try {
        if (handledColdStart.current) return;
        const last = await Notifications.getLastNotificationResponseAsync();
        if (cancelled || !last) return;
        handledColdStart.current = true;
        routeFrom(last);
      } catch {
        /* 푸시 미지원 환경 — 무시 */
      }
    })();

    try {
      sub = Notifications.addNotificationResponseReceivedListener(routeFrom);
    } catch {
      /* 푸시 미지원 환경 — 무시 */
    }

    return () => {
      cancelled = true;
      sub?.remove();
    };
  }, []);
}

export default useNotificationRouting;
