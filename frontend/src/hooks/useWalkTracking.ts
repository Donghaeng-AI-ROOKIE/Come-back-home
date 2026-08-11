/**
 * 산책 중 위치 추적 — 거리 누적과 현재 위치.
 *
 * **경로를 배열로 쌓지 않는다.** 직전 좌표 하나만 들고 있다가 새 좌표가 오면
 * 거리를 더하고 버린다. 경로를 모으면 그게 곧 시민의 상시 이동 이력이 되고,
 * 서버로 보내지 않더라도 기기에 남아 유출 표면이 된다
 * (backend/app/schemas/walk.py 의 개인정보 경계와 같은 원칙).
 *
 * 지도에 그릴 현재 위치는 마지막 좌표 하나뿐이라 궤적선은 그리지 않는다.
 */
import { useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';
import * as Location from 'expo-location';
import type { GeoPoint } from '../types/domain';

/**
 * 웹에서 GPS 를 켜는 **유일한** 스위치.
 *
 * expo-location 웹 구현은 `watchPositionAsync` 의 옵션을 브라우저
 * `navigator.geolocation.watchPosition` 에 **그대로 넘긴다**. 우리가 주는
 * `accuracy: BestForNavigation` 은 브라우저가 모르는 키라 조용히 무시되고,
 * 정작 필요한 `enableHighAccuracy` 는 아무도 채워 주지 않아 false 로 떨어진다
 * (같은 파일의 `getCurrentPositionAsync` 는 채워 주는데 watch 만 빠져 있다).
 *
 * 그 결과가 **거리 0.0km** 다. 고정확도가 꺼진 브라우저는 GPS 대신 와이파이·기지국
 * 측위를 쓰는데, 이 좌표는 걸어도 같은 지점에 붙박여 있다가 가끔 수십 m 씩
 * 순간이동한다. 붙박인 동안은 MIN_STEP 아래라 안 쌓이고, 순간이동은 점프로
 * 버려진다 — 그래서 시간만 늘고 거리는 0 인 채로 끝났다(실측 08-11).
 *
 * `maximumAge: 0` 은 캐시된 옛 좌표로 첫 기준점을 잡지 않기 위해서다 — 산책을
 * 시작한 지점이 아니라 몇 분 전 위치에서 거리를 재기 시작하면 첫 구간이
 * 통째로 틀린다.
 *
 * `timeout` 은 일부러 넣지 않았다. 웹 구현이 브라우저 에러 콜백 자리에
 * `undefined` 를 넘기기 때문에(아래 FIX_WATCHDOG_MS 주석) 타임아웃이 나도
 * 아무도 듣지 못한다. 관측할 수 없는 옵션을 넣으면 실내 콜드 스타트에서
 * 측위를 끊기만 한다.
 */
const WEB_GEO_OPTIONS = { enableHighAccuracy: true, maximumAge: 0 };

/**
 * 이 시간 안에 좌표가 하나도 안 오면 실패로 보고 사용자에게 알린다.
 *
 * 웹에서는 `watchPositionAsync` 의 errorHandler 가 **영영 불리지 않는다** —
 * expo 웹 구현이 `navigator.geolocation.watchPosition` 의 에러 콜백 자리에
 * `undefined` 를 넘기기 때문이다(ExpoLocation.web.js). 권한 거부 외의 실패는
 * (GPS 못 잡음·기기 위치서비스 꺼짐) 전부 조용히 사라지고, 화면에는 '0.0km'
 * 로만 나타난다 — 사용자가 원인을 알 방법이 없는 게 이번 버그의 절반이었다.
 * 그래서 이벤트 대신 시간으로 지켜본다.
 *
 * 45초는 고정확도 콜드 스타트(실내·지하 주차장 출발)를 실패로 몰지 않을 만큼
 * 넉넉하게 잡은 값이다.
 */
const FIX_WATCHDOG_MS = 45_000;

/**
 * 좌표를 못 받는 상황의 사용자 문구. 감시견(웹)과 errorHandler(네이티브)가
 * 같은 상황을 서로 다른 경로로 잡아내므로 문구는 하나로 둔다.
 */
const NO_FIX_MESSAGE = 'GPS 신호를 잡지 못해 거리를 재지 못하고 있습니다. 실외로 나가면 다시 잡힙니다.';

/**
 * GPS 튐 제거 — 이보다 부정확한 측정치는 거리 누적에 쓰지 않는다(m).
 *
 * 30m 로 잡았더니 **거리가 아예 안 쌓였다**(실측 08-11). 폰 브라우저의 측위
 * 정확도는 도심에서 흔히 30~60m 이고, 신촌처럼 건물이 빽빽한 곳은 더 나쁘다.
 * 네이티브 앱 기준으로 잡은 값이라 웹에서는 모든 측정치가 걸러졌다.
 */
const MAX_ACCURACY_M = 65;
/**
 * 도보 속도 상한(m/s). 점프 판정을 **고정 거리가 아니라 경과 시간**으로 한다 —
 * 브라우저는 콜백 간격이 들쭉날쭉해서(5초일 때도, 40초일 때도 있다) 고정 60m 로
 * 자르면 정상 보행도 점프로 버려진다.
 */
const MAX_SPEED_MPS = 3.0;
/** 이보다 작은 이동은 정지 중 GPS 흔들림으로 본다(m). */
const MIN_STEP_M = 5;

export type WalkTracking = {
  /** 'idle' 요청 전 · 'denied' 거부됨 · 'tracking' 추적 중 · 'error' 실패 */
  status: 'idle' | 'denied' | 'tracking' | 'error';
  distanceKm: number;
  current: GeoPoint | null;
  /**
   * 지금까지 걸은 경로. 거리에 반영된 점만 담는다 — 튄 측정치를 그리면 지도에
   * 실제로 가지 않은 선이 생긴다.
   */
  path: GeoPoint[];
  /** 사용자가 거부했을 때 화면이 이유를 보여주도록. */
  message: string;
};

/** 경로 보관 상한 — 5초·5m 간격이면 몇 시간치다. 메모리가 무한정 늘지 않게. */
const MAX_PATH = 3000;

function haversineM(a: GeoPoint, b: GeoPoint): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

export function useWalkTracking(active: boolean): WalkTracking {
  const [status, setStatus] = useState<WalkTracking['status']>('idle');
  const [message, setMessage] = useState('');
  const [distanceKm, setDistanceKm] = useState(0);
  const [current, setCurrent] = useState<GeoPoint | null>(null);
  const [path, setPath] = useState<GeoPoint[]>([]);
  const prev = useRef<GeoPoint | null>(null);
  /** 직전 측정 시각 — 점프 판정을 시간 기준으로 하기 위해 함께 들고 있는다. */
  const prevAt = useRef<number | null>(null);
  /** 좌표를 한 번이라도 받았는가 — 에러가 첫 픽스 실패인지 일시적 끊김인지 가른다. */
  const gotFix = useRef(false);

  useEffect(() => {
    if (!active) return;
    let sub: Location.LocationSubscription | null = null;
    let cancelled = false;
    let watchdog: ReturnType<typeof setTimeout> | null = null;

    (async () => {
      try {
        const { status: perm } = await Location.requestForegroundPermissionsAsync();
        if (cancelled) return;
        if (perm !== 'granted') {
          setStatus('denied');
          setMessage('위치 권한이 없어 거리를 잴 수 없습니다. 설정에서 허용해 주세요.');
          return;
        }
        setStatus('tracking');
        watchdog = setTimeout(() => {
          if (cancelled || gotFix.current) return;
          setStatus('error');
          setMessage(NO_FIX_MESSAGE);
        }, FIX_WATCHDOG_MS);
        sub = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.BestForNavigation,
            timeInterval: 5000,
            distanceInterval: 5,
            ...(Platform.OS === 'web' ? WEB_GEO_OPTIONS : null),
          } as Location.LocationOptions,
          (loc) => {
            const acc = loc.coords.accuracy ?? 999;
            const p: GeoPoint = { lat: loc.coords.latitude, lng: loc.coords.longitude };
            if (!gotFix.current) {
              gotFix.current = true;
              // 감시견이 먼저 울고 나서 뒤늦게 픽스가 오는 경우 — 경고를 걷는다.
              setStatus('tracking');
              setMessage('');
            }
            setCurrent(p);
            // 부정확한 측정치는 위치 표시에만 쓰고 거리에는 더하지 않는다.
            if (acc > MAX_ACCURACY_M) return;

            const now = loc.timestamp ?? Date.now();
            const last = prev.current;
            const lastAt = prevAt.current;
            if (!last || lastAt == null) {
              setPath((prevPath) => (prevPath.length ? prevPath : [p]));
              prev.current = p;
              prevAt.current = now;
              return;
            }

            const d = haversineM(last, p);
            const dtSec = Math.max((now - lastAt) / 1000, 1);
            // 측정 오차 안의 흔들림은 이동이 아니다 — 정확도가 나쁠수록 더 크게
            // 움직여야 인정한다. 안 그러면 서 있어도 거리가 늘어난다.
            const minStep = Math.max(MIN_STEP_M, acc * 0.5);
            // 점프 판정: 그 시간 동안 도보로 갈 수 있는 거리 + 측정 오차.
            const maxStep = MAX_SPEED_MPS * dtSec + acc;

            if (d >= minStep && d <= maxStep) {
              setDistanceKm((km) => km + d / 1000);
              // 거리에 더한 이동만 경로로 남긴다 — 판정 기준을 하나로 유지한다.
              setPath((prevPath) => [...prevPath, p].slice(-MAX_PATH));
              prev.current = p;
              prevAt.current = now;
            } else if (d > maxStep) {
              prev.current = p;   // 점프는 버리되 기준점은 옮긴다
              prevAt.current = now;
            }
            // d < minStep 이면 기준점을 그대로 둔다 — 천천히 걸을 때 조금씩
            // 쌓인 이동이 다음 측정에서 합쳐져 인정되게 한다.
          },
          // **네이티브 전용 경로다.** 웹은 에러를 전달하지 않으므로(위 감시견 주석)
          // 여기가 불리지 않는다. 좌표를 받던 중의 일시적 끊김은 흔하므로(터널·지하)
          // 추적 상태를 깨지 않고, 첫 픽스조차 못 잡은 경우만 알린다.
          () => {
            if (cancelled || gotFix.current) return;
            setStatus('error');
            setMessage(NO_FIX_MESSAGE);
          },
        );
      } catch (e) {
        if (!cancelled) {
          setStatus('error');
          // 예외 문자열을 그대로 띄우면 안 된다 — 이 메시지는 이제 산책 화면에
          // 실제로 그려지고, 내용은 대개 영문 스택이라 시민에게 아무 의미가 없다.
          // 원문은 콘솔로 보내 개발자만 본다.
          console.warn('[walk] 위치 추적을 시작하지 못했습니다:', e);
          setMessage('위치 서비스를 사용할 수 없어 거리를 재지 못합니다. 기기의 위치 설정을 확인해 주세요.');
        }
      }
    })();

    return () => {
      cancelled = true;
      if (watchdog) clearTimeout(watchdog);
      sub?.remove();
    };
  }, [active]);

  return { status, distanceKm, current, path, message };
}
