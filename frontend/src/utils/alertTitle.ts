/**
 * 알림 카드 제목 — 긴급 수색 알림 목록의 카드와 상황 종료 상세 화면이 같은
 * 제목을 쓰도록 한곳에 둔다.
 */

/**
 * 서버 주소가 `[서울특별시 마포구] 월드컵로`처럼 행정구역만 묶여 와도
 * 화면에서는 주소 전체를 하나의 대괄호 안에 표시한다.
 */
export function bracketAddress(area: string): string {
  const address = area.replace(/[\[\]]/g, ' ').replace(/\s+/g, ' ').trim();
  return `[${address}]`;
}

/** 상황 종료 제목 "[지역] N세 어르신". 나이를 모르면 나이 없이 쓴다. */
export function resolvedTitle(area: string, age?: number | null): string {
  return `${bracketAddress(area)}${age ? ` ${age}세` : ''} 어르신`;
}
