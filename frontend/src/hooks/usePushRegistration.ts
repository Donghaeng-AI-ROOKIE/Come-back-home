/**
 * 푸시 등록 — 권한 요청 → Expo 푸시 토큰 발급 → 서버 등록.
 *
 * ## 개발 빌드가 필요하다
 * Expo Go 는 푸시 기능을 담고 있지 않다(공식 문서: "You must use a development
 * build to use push notifications since the capability is not built into Expo Go").
 * 푸시 토큰은 앱 하나하나에 발급되는 "주소"인데, 전 세계 개발자가 공유하는
 * Expo Go 껍데기로는 우리 앱의 주소를 만들 수 없기 때문이다.
 * 따라서 이 훅은 **개발 빌드 이전까지 조용히 아무 일도 하지 않는다.**
 *
 * ## 실패는 전부 조용히 넘긴다
 * 권한 거부·에뮬레이터·projectId 미설정 어느 쪽이든 앱은 정상 동작해야 한다.
 * 푸시는 부가 경로이고, 앱을 직접 열어서 보는 경로가 이미 살아 있다.
 *
 * ## 서버에 올라가는 것: 토큰 + 서버 해상도의 현재 H3 칸 + 참여도 등급, 그게 전부
 * 좌표는 여기서 셀로 바꿔서 나간다(utils/h3cell.ts). 참여도도 등급만 나가고
 * 원본 이력은 폰에 남는다(store/engagementStore.ts). 자세한 경계는 api/client.ts
 * 의 registerDevice 주석과 백엔드 schemas/device.py 참고.
 */
import { useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { registerDevice } from '../api/client';
import { useEngagementLevel } from '../store/engagementStore';
import { cellOf } from '../utils/h3cell';
import { useMyLocation } from './useMyLocation';
import { useTargetingPolicy } from './useTargetingPolicy';

export type PushStatus =
  | 'idle'
  | 'unsupported'   // 시뮬레이터·웹 등 실기기가 아님
  | 'unavailable'   // Expo Go 등 푸시 기능 자체가 없음 (projectId 미설정 포함)
  | 'denied'        // 사용자가 알림 권한 거부
  | 'registered'    // 서버 등록까지 완료
  | 'error';

/**
 * 안드로이드 알림 채널 id. 서버가 보내는 `channelId` 와 **반드시 같아야** 한다 —
 * 다르면 기본 채널로 떨어져 소리·중요도 설정이 무시된다.
 */
export const ALERT_CHANNEL_ID = 'alerts';

async function ensureAndroidChannel(): Promise<void> {
  if (Platform.OS !== 'android') return;
  await Notifications.setNotificationChannelAsync(ALERT_CHANNEL_ID, {
    name: '실종 경보',
    // MAX: 실종 경보는 화면 상단에 떠야 한다(헤드업). 안드로이드는 채널 생성 후
    // 사용자가 낮출 수 있고 코드로는 되돌릴 수 없다 — 처음 값이 사실상 최종값이다.
    importance: Notifications.AndroidImportance.MAX,
    vibrationPattern: [0, 250, 250, 250],
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
    sound: 'default',
  });
}

/** EAS 프로젝트 id — 토큰 발급에 필요. 개발 빌드 설정 전에는 없다. */
function easProjectId(): string | null {
  const extra = Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined;
  return extra?.eas?.projectId ?? null;
}

export function usePushRegistration(enabled = true): PushStatus {
  const [status, setStatus] = useState<PushStatus>('idle');
  const [token, setToken] = useState<string | null>(null);
  const { point, observedAt, status: locationStatus } = useMyLocation(enabled);
  const policy = useTargetingPolicy(enabled);
  const level = useEngagementLevel();

  // 서버 해상도로 변환하고 관측 시각이 신선한 위치만 등록한다.
  const fresh = locationStatus === 'granted' && observedAt != null && Date.now() >= observedAt && Date.now()-observedAt <= 60_000;
  const cell = policy.resolution == null || !fresh ? null : cellOf(point, policy.resolution);
  const lastSent = useRef<string | null>(null);

  // ── 1) 토큰 발급 (한 번) ────────────────────────────────
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const settle = (s: PushStatus) => {
      if (!cancelled) setStatus(s);
    };

    (async () => {
      try {
        // 시뮬레이터·웹에는 푸시 토큰이 없다. 여기서 끊지 않으면 아래에서 던진다.
        if (!Device.isDevice) return settle('unsupported');

        const projectId = easProjectId();
        if (!projectId) {
          // Expo Go 이거나 아직 EAS 프로젝트가 없는 상태. 정상 경로다.
          return settle('unavailable');
        }

        await ensureAndroidChannel();

        const existing = await Notifications.getPermissionsAsync();
        let granted = existing.granted;
        if (!granted && existing.canAskAgain) {
          granted = (await Notifications.requestPermissionsAsync()).granted;
        }
        if (!granted) return settle('denied');

        const { data } = await Notifications.getExpoPushTokenAsync({ projectId });
        if (!cancelled) setToken(data);
      } catch {
        // Expo Go 에서 토큰 발급을 시도하면 여기로 떨어진다. 앱은 계속 동작해야 한다.
        settle('error');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [enabled]);

  // ── 2) 등록·갱신 (칸이나 등급이 바뀔 때마다) ────────────
  useEffect(() => {
    if (!enabled || token == null || policy.resolution == null) return;
    // 같은 관측의 중복 전송을 막고, 실제 새 관측으로만 TTL을 갱신한다.
    // A stationary phone must refresh the current cell before its server TTL.
    const key = `${cell ?? ''}|${level}|${policy.resolution}|${Math.floor((observedAt ?? 0)/60_000)}`;
    if (lastSent.current === key) return;

    let cancelled = false;
    (async () => {
      try {
        // 위치를 아직 못 받았으면 cell=null 로 보낸다. 서버는 이걸 "지웠다"가 아니라
        // "이번엔 못 구했다"로 읽고 마지막 칸을 유지한다(백엔드 devices.register).
        await registerDevice(token, Platform.OS === 'ios' ? 'ios' : 'android', cell, level);
        if (cancelled) return;
        lastSent.current = key;
        setStatus('registered');
      } catch {
        if (!cancelled) setStatus('error');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [enabled, token, cell, level, policy.resolution, observedAt]);

  return status;
}

export default usePushRegistration;
