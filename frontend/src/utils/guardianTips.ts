/**
 * 보호자 알림 탭(GuardianAlertsScreen)의 제보 목록 규칙 — 어느 사건의 제보를,
 * 어느 시각으로 보여 주는가.
 *
 * ## 시각: 목격 시각도 서버 시각이다
 * `seen_at` 은 시민이 직접 입력한 값이 아니다. 제보 화면은 시각을 글로 보내고
 * ("목격 시각: 10분 전"), 서버가 자기 시계로 절대시각을 계산해 naive 로 저장한다
 * (phase3/time_resolve.py, schemas/common.LocalNaiveDT). 배포 컨테이너 시계가 UTC 라
 * `created_at` 과 똑같이 오프셋 없는 UTC 다. 이걸 기기 로컬로 읽으면 9시간 과거가
 * 된다 — 10/27 운영: 11:38 에 본 제보가 "02:38" 로 보였다.
 *
 * ## 사건: 지도에 보이는 사건의 제보만
 * 서버 목록(`/phase1/cases`)에는 종결 뒤 파기 전(최대 5일)인 사건도 제보와 함께
 * 들어 있다. 그 제보를 진행 중 사건 제보와 한 목록에 섞으면, 지도에 없는 장소의
 * 묶음이 "주변 시민들의 실제 제보"로 보인다(10/27 운영: 종결 사건의 "[테스트] 배포
 * 확인용 합성 제보"가 섞임). 이 탭은 지도와 목록이 한 화면이라, 목록도 지도와 같은
 * 사건 하나만 본다. 종결 사건은 위쪽 사건 카드에 "종결된 수색"으로 따로 남는다.
 */

type TipTime = { seen_at?: string | null; created_at: string };
type MapCase = { status: string; lkp?: { lat: number; lng: number } | null };

/**
 * 오프셋 없는 서버 시각 → UTC 로 읽은 ms. 오프셋이 이미 있으면 그대로 둔다.
 * utils/walkFormat 의 serverTimeMs 와 같은 규칙이다(이 파일은 node 시험이 직접
 * 읽으므로 다른 유틸을 import 하지 않는다).
 */
function serverTimeMs(iso: string): number {
  const hasOffset = iso.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(iso);
  return new Date(hasOffset ? iso : `${iso}Z`).getTime();
}

/** 목격 시각이 있으면 그것을, 없으면 접수 시각을 쓴다. 둘 다 서버 시각(UTC)이다. */
export function tipTimeMs(tip: TipTime): number {
  if (tip.seen_at) {
    const t = serverTimeMs(tip.seen_at);
    if (!Number.isNaN(t)) return t;
  }
  return serverTimeMs(tip.created_at);
}

/** 카드에 쓰는 표기 — 기기 시간대 기준 `YYYY/M/D HH:mm`. */
export function formatTipTime(tip: TipTime): string {
  const t = tipTimeMs(tip);
  if (Number.isNaN(t)) return '';
  const d = new Date(t);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 지도에 그릴 사건 — 최종 목격 좌표가 있는 것 중 가장 최근(스토어가 최신순). */
export function mapCaseOf<C extends MapCase>(cases: readonly C[]): C | null {
  return cases.find((c) => !['found', 'closed'].includes(c.status) && c.lkp && Number.isFinite(c.lkp.lat) && Number.isFinite(c.lkp.lng)) ?? null;
}

/** 제보 목록에 올릴 사건 — 지도에 보이는 사건 하나(위 주석 참고). 없으면 빈 목록. */
export function listedCases<C extends MapCase>(cases: readonly C[]): C[] {
  const c = mapCaseOf(cases);
  return c ? [c] : [];
}
