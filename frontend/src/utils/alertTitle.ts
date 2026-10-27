/**
 * 알림 카드 제목 — 긴급 수색 알림 목록의 카드와 상황 종료 상세 화면이 같은
 * 제목을 쓰도록 한곳에 둔다.
 */

/** 대괄호와 겹친 공백을 걷어 낸 주소. 남는 글자가 없으면 빈 문자열이다. */
function cleanAddress(area?: string | null): string {
  return (area ?? '').replace(/[\[\]]/g, ' ').replace(/\s+/g, ' ').trim();
}

/**
 * 서버 주소가 `[서울특별시 마포구] 월드컵로`처럼 행정구역만 묶여 와도
 * 화면에서는 주소 전체를 하나의 대괄호 안에 표시한다.
 */
export function bracketAddress(area: string): string {
  return `[${cleanAddress(area)}]`;
}

/**
 * 상황 종료 제목 "[지역] N세 어르신". 나이를 모르면 나이 없이 쓴다.
 *
 * 지역명은 서버 워커의 메모리 캐시에서 오므로 재시작 뒤에는 빈 값으로 온다
 * (10/27 운영: 카드 제목이 "[] 어르신"으로 깨졌다). 그때는 대괄호 없이 "내 주변"
 * 으로 쓴다. 시민은 자기 주변 구역의 종결 사건만 받으므로 사실과 어긋나지 않는다.
 */
export function resolvedTitle(area?: string | null, age?: number | null): string {
  const address = cleanAddress(area);
  const place = address ? `[${address}]` : '내 주변';
  return `${place}${age ? ` ${age}세` : ''} 어르신`;
}
