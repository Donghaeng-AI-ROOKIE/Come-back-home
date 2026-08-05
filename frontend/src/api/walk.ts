/**
 * 안심 산책 API — 백엔드 `/walk` 대응.
 *
 * 레벨·배지 규칙은 서버가 계산한다(backend/app/walk/stats.py). 앱은 그리기만
 * 한다 — 규칙을 앱에 두면 규칙 변경마다 앱 배포가 필요하다.
 */
import { DEMO_USER_ID, api } from './config';

export type WalkSession = {
  id: string;
  user_id: string;
  started_at: string;
  ended_at: string | null;
  distance_km: number;
  duration_min: number;
  area_label: string;
};

export type Badge = {
  id: string;
  label: string;
  icon: string;
  earned: boolean;
  earned_at: string | null;
};

export type WalkStats = {
  user_id: string;
  total_km: number;
  month_km: number;
  walk_count: number;
  tip_count: number;
  level: number;
  level_label: string;
  next_level_km: number;
  badges: Badge[];
  recent: WalkSession[];
};

export function startWalk(areaLabel = '', userId = DEMO_USER_ID) {
  return api<WalkSession>('/walk/sessions', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, area_label: areaLabel }),
  });
}

export function endWalk(sessionId: string, distanceKm: number, durationMin: number) {
  return api<WalkSession>(`/walk/sessions/${sessionId}/end`, {
    method: 'POST',
    body: JSON.stringify({ distance_km: distanceKm, duration_min: durationMin }),
  });
}

/** 앱 재시작 시 진행 중이던 산책 복원. 없으면 null. */
export function getActiveWalk(userId = DEMO_USER_ID) {
  return api<WalkSession | null>(`/walk/sessions/active?user_id=${encodeURIComponent(userId)}`);
}

export function getWalkStats(userId = DEMO_USER_ID) {
  return api<WalkStats>(`/walk/stats?user_id=${encodeURIComponent(userId)}`);
}
