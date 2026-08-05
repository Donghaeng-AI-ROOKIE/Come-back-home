/**
 * 백엔드 접속 설정.
 *
 * `localhost` 는 앱에서 기기 자신을 가리킨다 — 안드로이드 에뮬레이터에서는
 * 호스트 PC 가 10.0.2.2 이고, **실기기에서는 localhost 로 백엔드에 절대 닿지
 * 않는다.** 실기기 시연에서는 호스트의 LAN IP 를 넣어야 한다.
 *
 * 우선순위: EXPO_PUBLIC_API_BASE 환경변수 > 플랫폼별 기본값.
 * 값을 바꾸려면 frontend/.env 에 아래처럼 쓰고 Expo 를 재시작한다.
 *
 *     EXPO_PUBLIC_API_BASE=http://192.168.0.12:8000
 *
 * (EXPO_PUBLIC_ 접두어가 붙은 것만 앱 번들에 주입된다 — Expo 규약.)
 */
import { Platform } from 'react-native';

const FALLBACK = Platform.select({
  android: 'http://10.0.2.2:8000',   // 안드로이드 에뮬레이터 → 호스트
  default: 'http://localhost:8000',  // iOS 시뮬레이터·웹
});

export const API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? FALLBACK!;

/**
 * 목 데이터로 되돌리는 스위치. 시연장 네트워크가 죽었을 때의 퇴로다.
 * 기본은 꺼짐 — 켜 두면 "연결됐다"고 착각한 채 목업을 보여주게 된다.
 */
export const USE_MOCK = process.env.EXPO_PUBLIC_USE_MOCK === 'true';

/** 인증 도입 전 임시 사용자 식별자 (백엔드 walk API 의 기본값과 같아야 한다). */
export const DEMO_USER_ID = 'demo-citizen';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** 공통 fetch — 실패를 삼키지 않고 상태코드와 서버 메시지를 그대로 올린다. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch (e) {
    // 네트워크 자체가 안 되는 경우 — 주소가 틀렸는지 바로 알 수 있게 주소를 담는다.
    throw new ApiError(0, path, `서버에 연결할 수 없습니다 (${API_BASE}). ${String(e)}`);
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new ApiError(res.status, path, detail || `${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
