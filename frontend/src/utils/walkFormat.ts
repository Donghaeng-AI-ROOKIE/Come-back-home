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

/**
 * 서버가 준 시각 문자열 → ms. **서버 시각은 UTC 인데 표시는 한국 시간이어야 한다.**
 *
 * 서버 컨테이너 시계가 UTC 라 `2026-08-11T16:41:35` 처럼 **오프셋 없는** 문자열이
 * 온다. 이걸 그대로 `new Date()`·`dayjs()` 에 넣으면 브라우저가 **로컬 시간**으로
 * 읽어서 9시간 과거로 표시된다.
 *
 * 실측(08-12): 새벽 1시 41분에 끝낸 산책이 기록 목록에 "16:41" 로 떴다. 사용자는
 * 방금 한 산책이 안 들어간 줄 알았다 — 실제로는 저장돼 있었고 시각만 틀렸다.
 *
 * 오프셋이 이미 붙어 있으면(`Z` 나 `+09:00`) 손대지 않는다 — 서버가 나중에
 * timezone-aware 로 바뀌어도 이 함수가 값을 두 번 밀지 않게.
 */
export function serverTimeMs(iso: string): number {
  const hasOffset = iso.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(iso);
  return new Date(hasOffset ? iso : `${iso}Z`).getTime();
}
