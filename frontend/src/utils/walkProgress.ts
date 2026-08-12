/**
 * 진행 중인 산책의 거리·경로를 기기에 **잠깐** 맡겨 둔다.
 *
 * ## 왜 필요한가
 * 거리와 경로는 화면 컴포넌트의 메모리(useWalkTracking 의 state)에만 있었다.
 * 그래서 화면이 다시 마운트되는 순간 **0.00km 로 돌아가고 지도의 선이 사라졌다**
 * (실측 08-12: 걷는 중에 실종 신고가 접수되자 0.37km → 0.00km).
 *
 * 리마운트는 예외 상황이 아니라 흔한 일이다.
 *  - 경보 관문이 서면 RootNavigator 의 key 가 바뀌어 화면 트리가 새로 마운트된다
 *  - 아이폰 홈 화면 웹앱은 잠깐 백그라운드로 갔다 오면 페이지째 다시 로드된다
 *  - 새로고침·역할 전환 등
 * 시간은 서버가 준 `started_at` 에서 매번 다시 계산되므로 이런 일이 있어도
 * 멀쩡했다 — **거리와 경로만 기억을 잃고 있었다.** 그 비대칭을 없앤다.
 *
 * ## 개인정보 경계
 * 여기 남는 것은 **지금 진행 중인 산책 하나**뿐이다. 산책을 끝내면 즉시 지운다
 * (WalkActiveScreen.onEnd). 세션 id 가 다르면 읽지 않는다 — 지난 산책의 경로가
 * 다음 산책에 되살아나지 않는다. 서버로는 여전히 거리·시간만 가고 경로는 가지
 * 않는다(backend/app/schemas/walk.py 의 경계 그대로).
 *
 * 좌표는 소수점 5자리(약 1m)로 줄여 담는다 — 지도에 그리는 데 그 이상은 필요
 * 없고, 저장소에 남기는 정밀도는 낮을수록 좋다.
 */
import { safeStorage } from '../store/safeStorage';
import type { GeoPoint } from '../types/domain';

const KEY = 'walk-progress-v1';

/**
 * 기준점이 이보다 오래됐으면 **거리를 이어 재지 않는다**(ms).
 *
 * 앱이 죽어 있던 동안의 이동은 잰 것이 아니라 모르는 것이다. 그 사이를 직선으로
 * 이어 붙이면 차를 타고 이동한 거리까지 산책 거리에 들어간다. 거리는 지금까지
 * 쌓인 값을 그대로 살리고, **다음 좌표부터 새 기준점으로 다시 잰다.**
 * 2분은 화면 전환·리마운트(수백 ms~수 초)는 넉넉히 이어 주고, 앱이 실제로
 * 꺼져 있던 구간은 이어 주지 않는 선이다.
 */
const STALE_ANCHOR_MS = 120_000;

export type WalkProgress = {
  /** 이 진행분이 어느 산책의 것인지 — 다르면 통째로 버린다. */
  sessionId: string;
  distanceKm: number;
  path: GeoPoint[];
  /** 마지막으로 거리에 반영한 좌표와 그 시각 = 이어서 잴 기준점. */
  anchor: GeoPoint | null;
  anchorAt: number | null;
};

const round5 = (n: number) => Math.round(n * 1e5) / 1e5;
const trim = (p: GeoPoint): GeoPoint => ({ lat: round5(p.lat), lng: round5(p.lng) });

function isPoint(v: unknown): v is GeoPoint {
  const p = v as GeoPoint | null;
  return !!p && Number.isFinite(p.lat) && Number.isFinite(p.lng);
}

/**
 * 저장해 둔 진행분을 읽는다. 세션이 다르거나 형식이 깨졌으면 null —
 * **되살릴 수 없으면 0 부터 시작하는 편이 틀린 거리를 보여주는 것보다 낫다.**
 */
export async function loadWalkProgress(sessionId: string): Promise<WalkProgress | null> {
  try {
    const raw = await safeStorage.getItem(KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as Partial<WalkProgress>;
    if (saved.sessionId !== sessionId) return null;
    if (!Number.isFinite(saved.distanceKm)) return null;

    const path = Array.isArray(saved.path) ? saved.path.filter(isPoint) : [];
    const anchorAt = typeof saved.anchorAt === 'number' ? saved.anchorAt : null;
    const fresh = anchorAt != null && Date.now() - anchorAt < STALE_ANCHOR_MS;
    return {
      sessionId,
      distanceKm: saved.distanceKm as number,
      path,
      // 오래된 기준점은 버린다(위 STALE_ANCHOR_MS). 거리는 살리고 기준만 다시 잡는다.
      anchor: fresh && isPoint(saved.anchor) ? saved.anchor : null,
      anchorAt: fresh ? anchorAt : null,
    };
  } catch {
    return null;
  }
}

/** 진행분을 덮어쓴다. 실패해도 조용히 넘어간다 — 산책 자체는 계속돼야 한다. */
export async function saveWalkProgress(p: WalkProgress): Promise<void> {
  try {
    await safeStorage.setItem(KEY, JSON.stringify({
      sessionId: p.sessionId,
      distanceKm: p.distanceKm,
      path: p.path.map(trim),
      anchor: p.anchor ? trim(p.anchor) : null,
      anchorAt: p.anchorAt,
    }));
  } catch {
    /* 저장소가 막힌 환경 — safeStorage 가 이미 메모리로 대체한다. */
  }
}

/** 산책이 끝났다 — 경로를 기기에 남겨 둘 이유가 사라졌다. */
export async function clearWalkProgress(): Promise<void> {
  try {
    await safeStorage.removeItem(KEY);
  } catch {
    /* 무시 */
  }
}
