/**
 * 산책 수치 표기 — 진행 화면·요약 화면·기록 목록이 같은 규칙을 쓴다.
 *
 * 화면마다 따로 포맷하던 시절, 산책 중에는 '0.04km' 로 보이던 거리가 종료 직후
 * 요약과 공유 문구에서는 '0.0km' 가 됐다(실측 08-11). 소수 한 자리로 자르면
 * **1km 미만 산책이 통째로 0 으로 보인다** — 동네 한 바퀴가 대부분인 앱에서
 * 그 구간이 정확히 사용자가 확인하고 싶어 하는 구간이다.
 */

/** 1km 미만은 둘째 자리까지 — 0.0km 로만 보이면 거리가 안 잡히는 줄 안다. */
export function formatKm(km: number): string {
  return km < 1 ? km.toFixed(2) : km.toFixed(1);
}

/**
 * 초 → mm:ss.
 *
 * 한 시간을 넘겨도 분으로 이어 센다(65:00). 산책은 그보다 짧은 게 보통이라
 * 시:분:초로 자리를 늘리면 짧은 산책의 가독성만 나빠진다.
 */
export function formatClock(totalSec: number): string {
  const sec = Math.max(0, Math.round(totalSec));
  return `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`;
}
