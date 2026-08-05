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
import * as Location from 'expo-location';
import type { GeoPoint } from '../types/domain';

/** GPS 튐 제거 — 이보다 부정확한 측정치는 거리 누적에 쓰지 않는다(m). */
const MAX_ACCURACY_M = 30;
/** 한 번의 갱신으로 이만큼 넘게 뛰면 점프로 본다(m). 도보 5초 간격 상한. */
const MAX_STEP_M = 60;
/** 이보다 작은 이동은 정지 중 GPS 흔들림으로 본다(m). */
const MIN_STEP_M = 2;

export type WalkTracking = {
  /** 'idle' 요청 전 · 'denied' 거부됨 · 'tracking' 추적 중 · 'error' 실패 */
  status: 'idle' | 'denied' | 'tracking' | 'error';
  distanceKm: number;
  current: GeoPoint | null;
  /** 사용자가 거부했을 때 화면이 이유를 보여주도록. */
  message: string;
};

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
  const prev = useRef<GeoPoint | null>(null);

  useEffect(() => {
    if (!active) return;
    let sub: Location.LocationSubscription | null = null;
    let cancelled = false;

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
        sub = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.BestForNavigation,
            timeInterval: 5000,
            distanceInterval: 5,
          },
          (loc) => {
            const acc = loc.coords.accuracy ?? 999;
            const p: GeoPoint = { lat: loc.coords.latitude, lng: loc.coords.longitude };
            setCurrent(p);
            // 부정확한 측정치는 위치 표시에만 쓰고 거리에는 더하지 않는다.
            if (acc > MAX_ACCURACY_M) return;
            const last = prev.current;
            if (last) {
              const d = haversineM(last, p);
              if (d >= MIN_STEP_M && d <= MAX_STEP_M) setDistanceKm((km) => km + d / 1000);
              else if (d > MAX_STEP_M) prev.current = p;  // 점프는 버리되 기준점은 옮긴다
            }
            if (!last || haversineM(last, p) >= MIN_STEP_M) prev.current = p;
          },
        );
      } catch (e) {
        if (!cancelled) {
          setStatus('error');
          setMessage(String(e));
        }
      }
    })();

    return () => {
      cancelled = true;
      sub?.remove();
    };
  }, [active]);

  return { status, distanceKm, current, message };
}
