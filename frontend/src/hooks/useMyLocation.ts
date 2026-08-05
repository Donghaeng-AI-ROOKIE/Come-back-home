/**
 * 내 위치 — 앱 전체가 공유하는 단일 구독.
 *
 * ## 🚨 이 좌표는 서버로 가지 않는다
 * 이 훅의 반환값을 API 요청 바디에 **그대로 실으면 안 된다** — presence 하트비트에
 * 좌표 필드가 없는 것도 같은 이유다.
 *
 * 유일한 예외가 푸시 등록인데, 거기서도 좌표가 아니라 **res7 셀 하나**(≈5km²)로
 * 바꿔서 나간다(utils/h3cell.ts). 변환을 폰이 하기 때문에 정밀 좌표는 기기를
 * 떠난 적이 없다 — 서버를 믿을 필요가 없는 구조라는 게 그 설계의 핵심이다.
 * 앱을 완전히 껐을 때도 알림이 가려면 서버가 대상을 골라야 해서 생긴 예외이고,
 * "위치를 보낸다"가 아니라 "어느 동네 칸인지만 보낸다"로 읽어야 한다.
 *
 * ## 왜 모듈 싱글턴인가
 * 진입 관문(RootNavigator)·경보 상세·수색 탭·잠금화면이 모두 위치를 본다. 훅마다
 * `watchPositionAsync` 를 걸면 GPS 워처가 화면 수만큼 생겨 배터리를 갉아먹는다.
 * 구독자를 참조 카운트로 세어 **워처는 하나만** 돌리고, 마지막 구독자가 사라질 때
 * 정리한다.
 *
 * ## 전경(foreground) 권한만 요청한다
 * 앱이 꺼진 동안의 지오펜싱은 백그라운드 권한이 필요하지만, 그건 푸시 인프라와
 * 함께 가야 의미가 있다. 지금 필요한 건 "앱을 보는 동안 내가 대상 구역 안인가"뿐이고,
 * 여기에 상시 위치 권한을 요구하는 건 과한 수집이다.
 *
 * ## 권한 거부는 정상 경로다 — 다만 조용하지 않아야 한다
 * 거부해도 화면은 전부 동작한다(구역 문구가 "알려드리지 못해요"로 물러난다).
 * 하지만 **경보는 못 받는다** — 위치를 모르면 어느 사건이 이 사람에게 해당되는지
 * 고를 수 없어 관문을 세우지 않기 때문이다(alertAppliesToMe 의 fail-closed).
 * 그래서 홈에서 그 사실을 알려야 한다.
 */
import { useEffect, useSyncExternalStore } from 'react';
import * as Location from 'expo-location';
import type { GeoPoint } from '../types/domain';

export type LocationStatus =
  | 'idle'        // 아직 요청 전
  | 'requesting'  // 권한/첫 측위 대기
  | 'granted'     // 사용 가능 (point 가 채워져 있다)
  | 'denied'      // 사용자가 거부
  | 'unavailable'; // 기기 위치서비스 꺼짐 등

export type MyLocation = {
  point: GeoPoint | null;
  /** 수평 정확도(m). 이 값보다 정밀한 거리를 표기하면 안 된다. */
  accuracyM: number | null;
  status: LocationStatus;
};

const INITIAL: MyLocation = { point: null, accuracyM: null, status: 'idle' };

/** 측위가 끝났는가 — 관문은 이 판정이 날 때까지 기다린다. */
export function isLocationSettled(status: LocationStatus): boolean {
  return status === 'granted' || status === 'denied' || status === 'unavailable';
}

// ── 모듈 싱글턴 ──────────────────────────────────────────────
let state: MyLocation = INITIAL;
const listeners = new Set<() => void>();
let subscription: Location.LocationSubscription | null = null;
let refCount = 0;
let starting = false;

function setState(next: MyLocation) {
  state = next;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

async function start(): Promise<void> {
  // 중복 기동 방지 — 여러 화면이 같은 프레임에 마운트될 수 있다.
  if (subscription || starting) return;
  starting = true;
  setState({ ...state, status: 'requesting' });

  try {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') {
      setState({ point: null, accuracyM: null, status: 'denied' });
      return;
    }

    const apply = (loc: Location.LocationObject) => {
      setState({
        point: { lat: loc.coords.latitude, lng: loc.coords.longitude },
        accuracyM: loc.coords.accuracy ?? null,
        status: 'granted',
      });
    };

    // 첫 값은 마지막으로 알려진 위치로 즉시 채운다 — 첫 GPS 픽스는 수 초 걸리는데
    // 그동안 관문이 대기하므로 체감 지연이 그대로 드러난다. (웹에서는 null 을
    // 돌려주므로 아래 watch 의 첫 콜백을 기다리게 된다.)
    const last = await Location.getLastKnownPositionAsync();
    if (last) apply(last);

    // Accuracy.High(GPS): 표기 단위가 50m 라 Balanced(≈100m)로는 정확도 게이트에
    // 걸려 숫자가 아예 안 뜬다. 전경에서만 도는 단일 워처라 비용을 감수한다.
    subscription = await Location.watchPositionAsync(
      {
        accuracy: Location.Accuracy.High,
        distanceInterval: 25, // 25m 이상 움직였을 때만 — 정지 상태 갱신 폭주 방지
        timeInterval: 10_000,
      },
      apply,
    );
  } catch {
    // 위치서비스가 꺼져 있거나 기기가 지원하지 않는 경우.
    // 화면이 이것 때문에 깨지면 안 되므로 조용히 물러난다.
    setState({ point: null, accuracyM: null, status: 'unavailable' });
  } finally {
    starting = false;
  }
}

function stop() {
  subscription?.remove();
  subscription = null;
  setState(INITIAL);
}

/**
 * @param enabled 이 화면이 실제로 위치를 쓸 때만 true. 마지막 구독자가 빠지면
 *   워처가 정리된다 — 안 보는 화면 때문에 GPS 를 켜두지 않기 위해서.
 */
export function useMyLocation(enabled = true): MyLocation {
  const snapshot = useSyncExternalStore(subscribe, () => state, () => state);

  useEffect(() => {
    if (!enabled) return;
    refCount += 1;
    void start();
    return () => {
      refCount -= 1;
      if (refCount <= 0) {
        refCount = 0;
        stop();
      }
    };
  }, [enabled]);

  return enabled ? snapshot : INITIAL;
}

export default useMyLocation;
