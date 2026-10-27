/**
 * 수색 시간(분) → "N시간 M분" — 상황 종료 상세 화면의 수치.
 *
 * 0 인 자리는 말하지 않는다("2시간", "45분"). "0시간 45분"은 읽는 사람이 한 번
 * 더 계산하게 만든다. 1분이 안 되면 "1분 미만"이라고 쓴다 — "0분"은 기록이
 * 없다는 뜻으로 읽힌다.
 *
 * 모르면 null 이다. 서버가 계산하지 못한 값을 0 으로 지어내지 않는다.
 */
export function formatSearchDuration(minutes?: number | null): string | null {
  if (minutes == null || !Number.isFinite(minutes) || minutes < 0) return null;
  const total = Math.floor(minutes);
  if (total === 0) return '1분 미만';
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (hours === 0) return `${rest}분`;
  return rest === 0 ? `${hours}시간` : `${hours}시간 ${rest}분`;
}
