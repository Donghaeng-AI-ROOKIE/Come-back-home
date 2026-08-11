/**
 * 웹 푸시 — 홈 화면에 설치한 웹앱으로 실제 OS 알림을 받는다.
 *
 * ## 왜 이게 필요한가
 * 지금까지 시민은 **앱을 켜 두고 있을 때만**(15초 폴링) 경보를 볼 수 있었다.
 * 주머니 속 폰은 울리지 않는다. 스토어 배포는 iOS 유료 계정이 필요하고 안드로이드
 * APK 는 FCM 등록이 선행돼야 해서, 그 사이를 웹 푸시가 메운다.
 *
 * ## 제약 — 그대로 사용자에게 말해야 하는 것들
 * - **아이폰은 홈 화면에 추가해야** 알림을 받을 수 있다(iOS 16.4+ 규칙). 사파리
 *   탭에서는 권한 요청 자체가 막힌다. 그래서 상태를 'needs-install' 로 구분한다.
 * - 권한 요청은 **사용자 제스처 안에서만** 뜬다 — 자동으로 부르지 않고 버튼을 둔다.
 * - 서버에 VAPID 키가 없으면 시도하지 않는다. 허용을 눌렀는데 알림이 안 오는
 *   상태가 제일 나쁘다.
 *
 * ## 위치
 * 구독을 등록할 때도 좌표가 아니라 **res7 셀 하나**만 보낸다(usePushRegistration
 * 과 같은 경계). 정밀 좌표는 기기를 떠나지 않는다.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';
import { API_BASE } from '../api/config';
import { useMyLocation } from './useMyLocation';
import { cellOf } from '../utils/h3cell';
import { useEngagementLevel } from '../store/engagementStore';

export type WebPushStatus =
  | 'unsupported'    // 이 브라우저·플랫폼에서는 불가
  | 'needs-install'  // 아이폰: 홈 화면에 추가해야 함
  | 'disabled'       // 서버에 VAPID 키 없음
  | 'idle'           // 켤 수 있음 (아직 권한 안 물음)
  | 'denied'         // 사용자가 거부
  | 'subscribed'     // 켜짐
  | 'working';

/** iOS 사파리는 홈 화면에 추가된 상태(standalone)에서만 푸시를 허용한다. */
function isStandalone(): boolean {
  if (typeof window === 'undefined') return false;
  const mm = window.matchMedia?.('(display-mode: standalone)')?.matches;
  // iOS 사파리는 display-mode 대신 navigator.standalone 을 쓴다.
  const ios = (window.navigator as unknown as { standalone?: boolean }).standalone;
  return Boolean(mm || ios);
}

function isIos(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /iPad|iPhone|iPod/.test(navigator.userAgent);
}

/** VAPID 공개키(base64url) → 구독 API 가 받는 바이트 배열. */
function urlBase64ToBytes(base64: string): ArrayBuffer {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, '+').replace(/_/g, '/'));
  const buf = new ArrayBuffer(raw.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i);
  return buf;
}

export function useWebPush() {
  const [status, setStatus] = useState<WebPushStatus>('unsupported');
  const [error, setError] = useState('');
  const { point } = useMyLocation(true);
  const level = useEngagementLevel();
  /** 마지막으로 서버에 올린 셀 — 같은 칸에서 반복 등록하지 않는다. */
  const lastCell = useRef<string | null>(null);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      // 아이폰인데 홈 화면에 추가하지 않았으면 PushManager 자체가 없다.
      setStatus(isIos() && !isStandalone() ? 'needs-install' : 'unsupported');
      return;
    }
    if (isIos() && !isStandalone()) {
      setStatus('needs-install');
      return;
    }
    if (Notification.permission === 'denied') {
      setStatus('denied');
      return;
    }

    (async () => {
      try {
        const res = await fetch(`${API_BASE}/phase3/webpush/public-key`);
        const { enabled } = (await res.json()) as { key: string; enabled: boolean };
        if (!enabled) return setStatus('disabled');
        const reg = await navigator.serviceWorker.getRegistration();
        const sub = await reg?.pushManager.getSubscription();
        setStatus(sub ? 'subscribed' : 'idle');
      } catch {
        setStatus('disabled');
      }
    })();
  }, []);

  /**
   * 구독을 서버에 올린다(upsert). **셀이 바뀔 때마다 다시 부른다.**
   *
   * 처음 이걸 한 번만 했더니 실제 아이폰 3대가 구독을 마쳤는데도 `cell_res7=None`
   * 으로 남아 **발송 대상에서 전부 빠졌다**(실측 08-11). 알림을 켜는 순간에는 아직
   * 측위가 안 끝난 경우가 많고, 사람은 그 뒤로 계속 움직인다.
   */
  const push = useCallback(async (sub: PushSubscription, cell: string | null) => {
    const json = sub.toJSON() as { endpoint?: string; keys?: Record<string, string> };
    await fetch(`${API_BASE}/phase3/devices`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        // 토큰 자리에는 endpoint 를 넣는다 — 그것이 이 브라우저의 주소다.
        token: json.endpoint,
        platform: 'web',
        cell_res7: cell,
        engagement: level,
        web_subscription: json,
      }),
    });
  }, [level]);

  // 이미 구독한 기기의 위치 칸을 따라 올린다. 서버는 upsert 라 발송 이력·피로도
  // 예산이 초기화되지 않는다(backend devices.register).
  const cell = point ? cellOf(point) : null;
  useEffect(() => {
    if (Platform.OS !== 'web' || status !== 'subscribed' || cell == null) return;
    if (lastCell.current === cell) return;
    lastCell.current = cell;
    (async () => {
      try {
        const reg = await navigator.serviceWorker.getRegistration();
        const sub = await reg?.pushManager.getSubscription();
        if (sub) await push(sub, cell);
      } catch {
        // 다음 위치 갱신에서 다시 시도한다 — 조용히 넘어간다.
        lastCell.current = null;
      }
    })();
  }, [status, cell, push]);

  /** 사용자가 버튼을 눌렀을 때만 부른다 — 권한 팝업은 제스처 안에서만 뜬다. */
  const enable = useCallback(async () => {
    if (Platform.OS !== 'web') return;
    setError('');
    setStatus('working');
    try {
      const keyRes = await fetch(`${API_BASE}/phase3/webpush/public-key`);
      const { key, enabled } = (await keyRes.json()) as { key: string; enabled: boolean };
      if (!enabled || !key) {
        setStatus('disabled');
        return;
      }

      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setStatus('denied');
        return;
      }

      const reg =
        (await navigator.serviceWorker.getRegistration()) ??
        (await navigator.serviceWorker.register('/sw.js'));
      await navigator.serviceWorker.ready;

      const sub =
        (await reg.pushManager.getSubscription()) ??
        (await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToBytes(key),
        }));

      const cellNow = point ? cellOf(point) : null;
      await push(sub, cellNow);
      lastCell.current = cellNow;
      setStatus('subscribed');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus('idle');
    }
  }, [point, push]);

  return { status, error, enable, isIos: isIos(), isStandalone: isStandalone() };
}
