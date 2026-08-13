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

/**
 * 웹은 **자기가 서빙된 그 출처**로 API 를 부른다(`/api/...`).
 *
 * 전에는 웹도 `https://macmini…:8443` 을 절대 주소로 불렀다. 그 구성은 폰에
 * 두 가지를 요구한다 — **비표준 포트 8443 통과**(학교·사내망이 흔히 막는다)와
 * 화면과 별개인 두 번째 TLS 연결. 배포 호스트가 바뀌면 앱을 다시 빌드해야
 * 한다는 문제도 있었다(08-12, 공개 경로를 Cloudflare 로 옮기며 드러남).
 *
 * 상대 경로면 어느 호스트에 올려도 그대로 동작하고 CORS 도 필요 없다.
 * `/api` → 백엔드로 넘기는 일은 nginx 가 한다(frontend/deploy/nginx.conf).
 *
 * 네이티브에는 "자기 출처"가 없으므로 절대 주소를 그대로 쓴다.
 */
const FALLBACK = Platform.OS === 'web' ? '/api' : 'https://macmini.tail67859f.ts.net:8443';

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

/**
 * 요청 하나가 이보다 오래 걸리면 실패로 본다(ms).
 *
 * 타임아웃이 없으면 응답이 안 오는 요청이 **영원히 매달린다.** 부팅 화면은
 * 토큰 확인·경보 조회가 끝날 때까지 스피너를 띄우므로, 그 요청 하나가 멈추면
 * 앱 전체가 무한 로딩이 되고 아무것도 눌리지 않는다(현장 제보 08-11).
 * 폰 LTE + Funnel 경유를 감안해 넉넉히 잡되, 무한정은 아니게 한다.
 */
const TIMEOUT_MS = 12_000;

/**
 * 오래 걸리는 게 **정상인** 요청의 상한(ms) — 예측·제보 처리.
 *
 * 위 12초는 조회용 값이다. 그런데 AI 예측은 웜 상태에서도 11~13초 걸리고
 * (실측 08-12: 11.3 / 12.3 / 29.5초), 새 지역의 첫 예측은 도로망을 내려받느라
 * **2분을 넘긴다**(신촌 첫 실행 실측). 같은 12초를 적용하면 예측은 구조적으로
 * 반반 실패하고, 화면에는 "AI 분석만 다시 시도해 주세요"만 남는다.
 *
 * 서버는 끊긴 뒤에도 계산을 끝내 캐시를 채우므로, 앱이 일찍 포기하면 **성공한
 * 계산을 실패로 표시하는** 최악의 조합이 된다. 그래서 넉넉히 기다린다.
 * 사용자는 그동안 '2. AI 예상 경로 분석' 단계가 도는 것을 보고 있다.
 */
export const SLOW_TIMEOUT_MS = 240_000;

/** 공통 fetch — 실패를 삼키지 않고 상태코드와 서버 메시지를 그대로 올린다. */
export async function api<T>(
  path: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  let res: Response;
  const { timeoutMs = TIMEOUT_MS, ...rest } = init ?? {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...rest,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(rest.headers ?? {}) },
    });
  } catch (e) {
    if (controller.signal.aborted) {
      throw new ApiError(0, path, `서버 응답이 없어 요청을 중단했습니다 (${timeoutMs / 1000}초).`);
    }
    // 네트워크 자체가 안 되는 경우 — 주소가 틀렸는지 바로 알 수 있게 주소를 담는다.
    throw new ApiError(0, path, `서버에 연결할 수 없습니다 (${API_BASE}). ${String(e)}`);
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new ApiError(res.status, path, detail || `${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
