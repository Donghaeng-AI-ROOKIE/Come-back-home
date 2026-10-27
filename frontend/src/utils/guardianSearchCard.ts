/**
 * 보호자 홈의 "수색 중" 카드 — 어느 사건을, 어떤 문구로 보여 주는가.
 *
 * 신고 뒤에도 홈 화면이 신고 전과 같았다. 지도와 제보는 "알림" 탭을 알아서 눌러야
 * 보였고, "실종 신고" 버튼도 그대로라 같은 가족을 두 번 신고할 수 있었다. 진행 중
 * 사건이 있으면 홈 맨 위에 카드 한 장을 두고, 그 사건의 경과 시간과 새 제보 수를
 * 보여 준다.
 *
 * ## 시각
 * `created_at` 은 서버가 자기 시계로 찍은 오프셋 없는 시각이고, 배포 컨테이너 시계가
 * UTC 다. 기기 로컬로 읽으면 9시간 어긋난다(utils/guardianTips 와 같은 사정).
 * 경과 시간의 기준은 신고(사건 생성) 시각이다 — 서버가 종결 카드의 "수색 시간"을
 * 같은 기준으로 센다(phase3/alerts._search_minutes).
 *
 * ## 새 제보
 * 이 기기에서 보호자 알림 탭을 열어 둔 동안 화면에 있던 제보는 "본 제보"로 적어
 * 둔다(store/guardianCaseStore 의 seenTips). 그 밖의 제보가 새 제보다. 개수가 아니라
 * ID 로 비교한다 — 접수 대기 중 제보가 취소돼 빠지면 개수 비교는 그다음 제보를
 * 놓친다.
 *
 * 이 파일은 node 시험이 직접 읽으므로 다른 유틸을 import 하지 않는다.
 */

/** 진행 중 상태 — 서버 CaseStatus 의 intake·predicted·searching. */
const ACTIVE = new Set(['intake', 'predicted', 'searching']);

type CardCase = {
  id: string;
  status: string;
  created_at: string;
  area_label?: string | null;
  report?: { persona_id?: string | null } | null;
  tips?: readonly { id: string }[] | null;
};

type CardPersona = { id: string; name?: string | null };

export type SearchCard = {
  caseId: string;
  badge: string;
  title: string;
  body: string;
};

/** 오프셋 없는 서버 시각 → UTC 로 읽은 ms(utils/walkFormat 의 serverTimeMs 와 같은 규칙). */
function serverTimeMs(iso: string): number {
  const hasOffset = iso.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(iso);
  return new Date(hasOffset ? iso : `${iso}Z`).getTime();
}

/** 진행 중 사건만, 신고가 최근인 순으로. */
export function activeCases<C extends CardCase>(cases: readonly C[]): C[] {
  return cases
    .filter((c) => ACTIVE.has(c.status))
    .sort((a, b) => serverTimeMs(b.created_at) - serverTimeMs(a.created_at));
}

/**
 * 신고부터 지금까지 — "N시간 M분", 한 시간이 안 되면 "M분".
 * 기기 시계가 서버보다 늦어 음수가 나오면 0분으로 쓴다.
 */
export function formatElapsed(createdAt: string, nowMs: number): string {
  const start = serverTimeMs(createdAt);
  if (Number.isNaN(start)) return '';
  const minutes = Math.max(0, Math.floor((nowMs - start) / 60_000));
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h > 0 ? `${h}시간 ${m}분` : `${m}분`;
}

/** 이 기기에서 아직 보지 않은 제보 수. */
export function newTipCount(tips: readonly { id: string }[] | null | undefined, seen: readonly string[] | undefined): number {
  const known = new Set(seen ?? []);
  return (tips ?? []).filter((t) => !known.has(t.id)).length;
}

/** 대괄호와 겹친 공백을 걷어 낸 지역명을 한 쌍의 대괄호로(utils/alertTitle 의 bracketAddress 와 같은 규칙). */
function areaName(area?: string | null): string {
  const clean = (area ?? '').replace(/[\[\]]/g, ' ').replace(/\s+/g, ' ').trim();
  return clean ? `[${clean}]` : '';
}

/** 카드가 부르는 이름 — 등록한 가족 이름, 없으면 지역명, 둘 다 없으면 "가족". */
function whoOf(c: CardCase, personas: readonly CardPersona[]): string {
  const personaId = c.report?.persona_id;
  const name = personaId ? personas.find((p) => p.id === personaId)?.name?.trim() : '';
  if (name) return `${name} 님`;
  return areaName(c.area_label) || '가족';
}

/**
 * 홈 카드 한 장. 진행 중 사건이 없으면 null.
 * 둘 이상이면 가장 최근 사건으로 그리고 배지에 "외 N건"을 붙인다.
 */
export function guardianSearchCard(
  cases: readonly CardCase[],
  personas: readonly CardPersona[],
  seenTips: Readonly<Record<string, readonly string[]>>,
  nowMs: number,
): SearchCard | null {
  const active = activeCases(cases);
  const latest = active[0];
  if (!latest) return null;
  const others = active.length - 1;
  const elapsed = formatElapsed(latest.created_at, nowMs);
  return {
    caseId: latest.id,
    badge: others > 0 ? `수색 중 · 외 ${others}건` : '수색 중',
    title: `${whoOf(latest, personas)} 수색 중${elapsed ? ` · 경과 ${elapsed}` : ''}`,
    body: `새 제보 ${newTipCount(latest.tips, seenTips[latest.id])}건 · 지도는 15초마다 갱신돼요`,
  };
}
