/**
 * 알림 카드 제목 — 긴급 수색 알림 목록의 카드와 상황 종료 상세 화면이 같은
 * 제목을 쓰도록 한곳에 둔다.
 *
 * 이 파일은 node 시험이 직접 읽으므로 다른 유틸을 import 하지 않는다.
 */

/** 대괄호와 겹친 공백을 걷어 낸 주소. 남는 글자가 없으면 빈 문자열이다. */
function cleanAddress(area?: string | null): string {
  return (area ?? '').replace(/[\[\]]/g, ' ').replace(/\s+/g, ' ').trim();
}

/**
 * 서버 주소가 `[서울특별시 마포구] 월드컵로`처럼 행정구역만 묶여 와도
 * 화면에서는 주소 전체를 하나의 대괄호 안에 표시한다.
 */
export function bracketAddress(area?: string | null): string {
  return `[${cleanAddress(area)}]`;
}

/**
 * 진행 중 경보 제목 "[지역] N세 실종 어르신" — 긴급 알림 목록 카드의 제목이다.
 * 지역명이 비어 있으면 "최종 목격 위치 기준"으로 쓴다(목록 카드가 원래 쓰던 규칙).
 */
export function activeAlertTitle(area?: string | null, age?: number | null): string {
  return `${bracketAddress(area || '최종 목격 위치 기준')}${age ? ` ${age}세` : ''} 실종 어르신`;
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

type NearbyAlert = { caseId: string; area?: string | null; age?: number | null };

/** 시민 홈 맨 위 경보 카드. `caseId` 가 null 이면 긴급 알림 탭(목록)으로 연다. */
export type NearbyAlertCard = { badge: string; title: string; body: string; caseId: string | null };

/**
 * 시민 홈의 주변 경보 카드 — 주변에 진행 중 경보가 있어도 홈에는 아무 표시가 없었다.
 *
 * 긴급 알림 목록과 같은 경보를 같은 규칙으로 고른다: "이 사건은 그만 볼래요"로 끈
 * 사건은 빼고(CitizenAlertsScreen 과 같은 거름), 맨 위 경보의 제목은 목록 카드와 같다.
 * 한 건이면 그 경보 상세로, 둘 이상이면 배지에 "외 N건"을 붙이고 목록으로 보낸다.
 */
export function nearbyAlertCard(
  alerts: readonly NearbyAlert[] | null | undefined,
  dismissed: Readonly<Record<string, unknown>>,
): NearbyAlertCard | null {
  const visible = (alerts ?? []).filter((a) => dismissed[a.caseId] === undefined);
  const first = visible[0];
  if (!first) return null;
  const others = visible.length - 1;
  return {
    badge: others > 0 ? `내 주변 수색 중 · 외 ${others}건` : '내 주변 수색 중',
    title: activeAlertTitle(first.area, first.age),
    body: '봤다면 바로 제보해 주세요',
    caseId: others > 0 ? null : first.caseId,
  };
}
