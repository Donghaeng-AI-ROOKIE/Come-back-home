/**
 * 산책 중 위치 추적 — 거리 누적과 현재 위치, 그리고 지도에 그릴 경로.
 *
 * **경로는 진행 중인 산책 하나에 대해서만 들고 있다.** 지도에 지금까지 걸은 길을
 * 그려 주려면 좌표를 이어 둘 수밖에 없다. 대신 경계를 좁게 잡는다: 서버로는
 * 거리·시간만 보내고(backend/app/schemas/walk.py), 기기에 맡겨 두는 진행분도
 * 산책을 끝내는 순간 지운다(utils/walkProgress).
 *
 * **진행분은 화면 메모리에만 두지 않는다.** 화면이 다시 마운트되면(경보 관문·
 * 페이지 재로드) 거리와 경로가 통째로 0 이 됐다 — 실측 08-12. 그래서 세션 id 로
 * 저장해 두고 마운트할 때 이어받는다. 시간(started_at)은 이미 그렇게 살아남고
 * 있었고, 거리만 기억을 잃던 비대칭을 없앤 것이다.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';
import * as Location from 'expo-location';
import type { GeoPoint } from '../types/domain';
import { loadWalkProgress, saveWalkProgress } from '../utils/walkProgress';

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
/**
 * `maximumAge: 0` 이었다 — **브라우저가 좌표를 거의 안 줬다.**
 *
 * 0 은 "캐시된 값은 절대 쓰지 말고 매번 새로 측위하라"는 뜻이다. 고정확도와
 * 겹치면 iOS 사파리는 콜백 간격이 크게 벌어지고, 실내에서는 아예 침묵한다.
 * 같은 화면의 지도 훅(useMyLocation)은 30초 캐시를 허용해서 잘 받고 있었다 —
 * "내 위치는 잡히는데 산책 거리만 0" 의 정체가 이 차이다(현장 제보 08-12).
 *
 * 5초는 도보 속도에서 약 6m 다. 아래 minStep(≥5m·정확도 비례)이 그보다 큰
 * 이동만 인정하므로, 캐시를 조금 허용해도 거리가 부풀지 않는다.
 */
const WEB_GEO_OPTIONS = { enableHighAccuracy: true, maximumAge: 5_000 };

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
 * 좌표는 오는데 **오차가 커서 거리에 못 쓰는** 상황의 문구.
 *
 * 위 문구와 반드시 구분해야 한다. 실측(08-12): 지도에는 내 위치가 떠 있는데
 * "GPS 신호를 잡지 못해"가 같이 떠 있었다 — 화면이 스스로 모순돼서 사용자는
 * 무엇을 해야 할지 알 수 없다. 실제 오차를 숫자로 보여 주면 실내인지 기기
 * 문제인지 본인이 판단할 수 있다.
 */
const impreciseMessage = (accuracyM: number) =>
  `위치 오차가 커서(약 ${Math.round(accuracyM)}m) 거리를 아직 재지 않습니다. `
  + '실외로 나가면 재기 시작합니다.';

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
  /**
   * 지금 즉시 새 측위를 받는다 — 지도 위 '내 위치' 버튼이 부른다.
   *
   * 워처는 브라우저가 주는 대로 받을 뿐이라, 실내에서 나왔거나 한참 서 있다가
   * 다시 걷기 시작한 순간에는 낡은 좌표에 머물 수 있다. 그때 사용자가 직접
   * 한 번 당길 수 있어야 한다(네이버 지도의 현위치 버튼과 같은 역할).
   */
  refresh: () => void;
  /** refresh 진행 중 — 버튼이 도는 표시를 낼 수 있게. */
  refreshing: boolean;
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

/**
 * @param sessionId 진행 중인 산책의 id. null 이면 추적하지 않는다.
 *   **불리언이 아니라 id 를 받는 이유**: 리마운트 뒤에 이어받을 진행분이
 *   어느 산책의 것인지 알아야 지난 산책의 거리를 되살리지 않는다.
 */
export function useWalkTracking(sessionId: string | null): WalkTracking {
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
  /** 거리에 **쓸 만한** 좌표를 한 번이라도 받았는가 — 오차 안내를 걷는 기준. */
  const gotUsableFix = useRef(false);
  /**
   * 워처가 쓰는 좌표 처리기를 밖에서도 부를 수 있게 담아 둔다.
   *
   * '내 위치' 버튼이 받아 온 좌표도 **워처와 똑같은 판정**(정확도 게이트·최소
   * 이동·점프 판정)을 지나야 한다. 버튼만 다른 규칙을 쓰면 눌렀다는 이유로
   * 거리가 늘거나 튄 점이 경로에 남는다.
   */
  const handleFix = useRef<((loc: Location.LocationObject) => void) | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  /**
   * 저장해 둔 진행분을 읽기 전에는 저장하지 않는다 — 비어 있는 초기 상태로
   * 덮어쓰면 이어받으려던 거리를 우리 손으로 지우게 된다.
   */
  const restored = useRef(false);

  useEffect(() => {
    if (!sessionId) return;
    // 이어받기 전까지는 저장을 막는다. 특히 **산책이 바뀌는 순간**이 중요하다 —
    // 아래 저장 효과가 먼저 돌면 앞 산책의 거리가 새 산책 id 로 적힌다.
    // (효과는 선언 순서대로 도므로 여기서 내려 두면 그쪽이 건너뛴다.)
    restored.current = false;
    let sub: Location.LocationSubscription | null = null;
    let cancelled = false;
    let watchdog: ReturnType<typeof setTimeout> | null = null;

    (async () => {
      try {
        // 진행분 이어받기는 **권한보다 먼저** 한다. 권한이 거부돼 아래에서 바로
        // 빠져나가더라도, 지금까지 걸은 거리는 화면에 남아 있어야 한다.
        const saved = await loadWalkProgress(sessionId);
        if (cancelled) return;
        if (saved) {
          setDistanceKm(saved.distanceKm);
          setPath(saved.path);
          prev.current = saved.anchor;
          prevAt.current = saved.anchorAt;
          // 이미 거리를 재고 있던 산책이다 — 오차 안내를 처음부터 다시 띄우지 않는다.
          if (saved.anchor) gotUsableFix.current = true;
        } else {
          // 이어받을 것이 없는 산책이다. 화면이 그대로 남은 채 산책만 바뀌는
          // 경우(끝내고 곧바로 새로 시작)에 앞 산책의 숫자가 남지 않게 한다.
          setDistanceKm(0);
          setPath([]);
          prev.current = null;
          prevAt.current = null;
          gotUsableFix.current = false;
        }
        restored.current = true;

        // **웹에서는 권한 래퍼를 거치지 않는다.**
        //
        // expo 의 웹 구현은 `navigator.permissions.query` 가 'denied' 면
        // 브라우저에 묻지도 않고 거부를 돌려준다. 그러면 여기서 바로 빠져나가
        // **워처를 아예 시작하지 않는다** — 산책 거리가 통째로 0 이 되는 경로다.
        // (같은 함정을 useMyLocation.retryLocation 에서 이미 겪었다.)
        //
        // 브라우저에서는 측위를 호출하는 것 자체가 권한 요청이다. 바로 워처를
        // 걸고, 거부면 아래 감시견과 오차 안내가 사용자에게 이유를 말한다.
        if (Platform.OS !== 'web') {
          const { status: perm } = await Location.requestForegroundPermissionsAsync();
          if (cancelled) return;
          if (perm !== 'granted') {
            setStatus('denied');
            setMessage('위치 권한이 없어 거리를 잴 수 없습니다. 설정에서 허용해 주세요.');
            return;
          }
        }
        setStatus('tracking');
        watchdog = setTimeout(() => {
          if (cancelled || gotFix.current) return;
          setStatus('error');
          setMessage(NO_FIX_MESSAGE);
        }, FIX_WATCHDOG_MS);

        // 웹 초벌 측위 — 고정확도 워처는 실내에서 **수 분까지 침묵한다.**
        //
        // 실측(08-12): 산책 4분 동안 워처가 좌표를 0건 줬는데, 같은 화면의
        // 지도에는 내 위치가 멀쩡히 떠 있었다. 지도 훅(useMyLocation)에는
        // 이 한 번짜리 폴백이 있고 여기에는 없었던 것이 차이의 전부다.
        // 거친 값이라도 먼저 받아 두면 "신호 못 잡음" 오진을 막고 지도가
        // 출발 지점을 바로 잡는다. **거리에는 쓰지 않는다** — 아래 워처와
        // 똑같이 정확도 게이트를 지나야 한다.
        if (Platform.OS === 'web') {
          void Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced })
            .then((loc) => {
              if (cancelled || gotFix.current) return;
              gotFix.current = true;
              const acc = loc.coords.accuracy ?? 999;
              setCurrent({ lat: loc.coords.latitude, lng: loc.coords.longitude });
              setStatus('tracking');
              // 거친 값이라 대개 게이트를 못 넘는다. 그 사실을 숨기지 않는다.
              if (acc > MAX_ACCURACY_M) setMessage(impreciseMessage(acc));
            })
            .catch(() => { /* 워처가 곧 채운다 — 여기 실패로 상태를 깎지 않는다. */ });
        }

        sub = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.BestForNavigation,
            timeInterval: 5000,
            distanceInterval: 5,
            ...(Platform.OS === 'web' ? WEB_GEO_OPTIONS : null),
          } as Location.LocationOptions,
          (handleFix.current = (loc: Location.LocationObject) => {
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
            if (acc > MAX_ACCURACY_M) {
              // 아직 한 번도 거리를 못 쟀다면 **왜 0.00km 인지** 알려 준다.
              // 이미 재고 있었다면 잠깐 나빠진 것이라 조용히 넘긴다.
              if (!gotUsableFix.current) setMessage(impreciseMessage(acc));
              return;
            }
            if (!gotUsableFix.current) {
              gotUsableFix.current = true;
              setMessage('');   // 오차 안내를 걷는다 — 이제 실제로 재고 있다.
            }

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
          }),
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
  }, [sessionId]);

  /**
   * 진행분을 기기에 맡겨 둔다 — 다음 마운트가 여기서 이어받는다.
   *
   * 거리·경로가 바뀔 때만 쓴다(= 실제로 인정된 이동이 있을 때만, 최소 5m 마다).
   * 기준점(prev/prevAt)은 ref 라 렌더를 일으키지 않으므로 같은 순간에 함께 담는다 —
   * 거리와 기준점이 갈리면 이어 잴 때 한 구간이 두 번 세어진다.
   */
  useEffect(() => {
    if (!sessionId || !restored.current) return;
    void saveWalkProgress({
      sessionId,
      distanceKm,
      path,
      anchor: prev.current,
      anchorAt: prevAt.current,
    });
  }, [sessionId, distanceKm, path]);

  /**
   * '내 위치' 버튼 — 지금 즉시 새 좌표를 받아 워처와 **같은 판정**에 흘려 넣는다.
   *
   * 웹은 `navigator.geolocation` 을 직접 부른다. expo 래퍼는 권한 상태가
   * 'denied' 면 브라우저에 묻지도 않고 돌아와, 눌러도 아무 일이 없는 버튼이
   * 된다(useMyLocation.retryLocation 에서 겪은 것과 같은 함정).
   *
   * `maximumAge: 0` 을 여기서만 쓴다 — 워처는 캐시를 조금 허용해야 콜백이
   * 끊기지 않지만(WEB_GEO_OPTIONS 주석), **사용자가 직접 누른 이 순간**에는
   * 낡은 좌표를 주면 안 된다. 그게 이 버튼의 존재 이유다.
   */
  const refresh = useCallback(() => {
    if (refreshing) return;
    setRefreshing(true);
    const done = (loc: Location.LocationObject) => {
      handleFix.current?.(loc);
      setRefreshing(false);
    };
    const fail = () => setRefreshing(false);

    if (Platform.OS === 'web') {
      if (!navigator?.geolocation) return fail();
      navigator.geolocation.getCurrentPosition(
        (pos) => done({
          coords: {
            latitude: pos.coords.latitude, longitude: pos.coords.longitude,
            accuracy: pos.coords.accuracy, altitude: pos.coords.altitude,
            altitudeAccuracy: pos.coords.altitudeAccuracy,
            heading: pos.coords.heading, speed: pos.coords.speed,
          },
          timestamp: pos.timestamp,
        } as Location.LocationObject),
        fail,
        { enableHighAccuracy: true, timeout: 20_000, maximumAge: 0 },
      );
      return;
    }
    Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.BestForNavigation })
      .then(done)
      .catch(fail);
  }, [refreshing]);

  return { status, distanceKm, current, path, message, refresh, refreshing };
}
