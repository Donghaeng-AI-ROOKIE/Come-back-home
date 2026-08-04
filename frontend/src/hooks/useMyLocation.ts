/**
 * 내 위치 (알림 개인화 #2·#7 대체안).
 *
 * ## 이 좌표는 서버로 가지 않는다
 * 온디바이스 지오펜싱 원칙: 서버는 알림 대상 H3 셀 목록만 뿌리고, "내가 그 안에
 * 있나 / 얼마나 가깝나"는 폰이 계산한다. 이 훅의 반환값을 API 요청 바디에 실으면
 * 그 전제가 통째로 무너진다 — presence 하트비트에 좌표 필드가 없는 것도 같은 이유다.
 *
 * ## 전경(foreground) 권한만 요청한다
 * 앱이 꺼진 동안의 지오펜싱은 백그라운드 권한이 필요하지만, 그건 푸시 인프라와
 * 함께 가야 의미가 있다(별도 작업). 지금 필요한 건 "경보 화면을 보는 동안 내가
 * 얼마나 가까운가"뿐이고, 여기에 상시 위치 권한을 요구하는 건 과한 수집이다.
 *
 * ## 권한 거부는 정상 경로다
 * 거부해도 화면은 전부 동작해야 한다. 거리 문구만 숫자 없는 표현으로 물러난다.
 */
import { useEffect, useRef, useState } from 'react';
import * as Location from 'expo-location';
import type { GeoPoint } from '../types/domain';

export type LocationStatus =
  | 'idle'        // 아직 요청 전
  | 'requesting'  // 권한/첫 측위 대기
  | 'granted'     // 사용 가능 (point 가 채워졌거나 곧 채워짐)
  | 'denied'      // 사용자가 거부 — 숫자 없는 문구로 물러난다
  | 'unavailable'; // 기기 위치서비스 꺼짐 등

export type MyLocation = {
  point: GeoPoint | null;
  /** 수평 정확도(m). 이 값보다 정밀한 거리를 표기하면 안 된다. */
  accuracyM: number | null;
  status: LocationStatus;
};

const INITIAL: MyLocation = { point: null, accuracyM: null, status: 'idle' };

/**
 * @param enabled 화면이 실제로 위치를 쓸 때만 true. false 면 측위를 시작조차
 *   하지 않는다 — 안 보는 화면 때문에 GPS 를 켜두면 배터리만 먹는다.
 */
export function useMyLocation(enabled = true): MyLocation {
  const [state, setState] = useState<MyLocation>(INITIAL);
  // 언마운트 후 setState 경고 방지 + 구독 정리용.
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    if (!enabled) {
      setState(INITIAL);
      return;
    }

    let subscription: Location.LocationSubscription | null = null;

    (async () => {
      setState((s) => ({ ...s, status: 'requesting' }));
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (!mounted.current) return;
        if (status !== 'granted') {
          setState({ point: null, accuracyM: null, status: 'denied' });
          return;
        }

        const apply = (loc: Location.LocationObject) => {
          if (!mounted.current) return;
          setState({
            point: { lat: loc.coords.latitude, lng: loc.coords.longitude },
            accuracyM: loc.coords.accuracy ?? null,
            status: 'granted',
          });
        };

        // 첫 값은 마지막으로 알려진 위치로 즉시 채운다 — 첫 GPS 픽스는 수 초
        // 걸리는데, 긴급 경보 화면에서 거리 칸이 비어 있는 시간을 만들지 않는다.
        const last = await Location.getLastKnownPositionAsync();
        if (last) apply(last);

        // Accuracy.High(GPS): 표기 단위가 50m 라 Balanced(≈100m)로는
        // 정확도 게이트에 걸려 숫자가 아예 안 뜬다. 전경에서 잠깐만 쓰므로 감수.
        subscription = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.High,
            distanceInterval: 25, // 25m 이상 움직였을 때만 — 정지 상태 갱신 폭주 방지
            timeInterval: 10_000,
          },
          apply,
        );
      } catch {
        // 위치서비스 자체가 꺼져 있거나 기기가 지원하지 않는 경우.
        // 경보 화면이 이것 때문에 깨지면 안 되므로 조용히 물러난다.
        if (mounted.current) setState({ point: null, accuracyM: null, status: 'unavailable' });
      }
    })();

    return () => {
      mounted.current = false;
      subscription?.remove();
    };
  }, [enabled]);

  return state;
}

export default useMyLocation;
