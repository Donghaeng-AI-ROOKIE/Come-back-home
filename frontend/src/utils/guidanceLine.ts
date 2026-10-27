/**
 * 시민 수색지도(AlertSyncScreen)의 수색 안내 한 줄 — 무엇을 보여 줄지.
 *
 * 예전에는 `guidance || '…불러오고 있습니다.'` 라서, 안내를 **받았는데 비어 있거나**
 * 조회가 **실패해도** 로딩 문구가 영원히 남았다. 10/27 운영(사건 c93122664ff2):
 * `GET /phase3/cases/{id}/guidance` 가 3초 만에 200 `{guidance: "", pending: false}` 를
 * 돌려줬다(서버 검증이 템플릿을 거절하면 빈 문자열, phase3/storytelling.guidance_for).
 * 화면은 60초 내내 "사건에 맞는 수색 안내를 불러오고 있습니다."였다. 조회는
 * retry:false 이고 빈 결과에는 다시 묻지 않으므로(hooks/queries.useGuidance) 기다려도
 * 바뀌지 않는다.
 *
 * 그래서 로딩 문구는 **첫 조회가 진행 중일 때만** 쓰고, 끝났는데 문구가 없으면 사건과
 * 무관하게 맞는 일반 안내로 물러난다. 같은 화면의 지도가 예측 확률을 색으로 보여
 * 주므로 "색이 진한 곳부터"는 어느 사건에서나 사실이다. 서버 안내의 금지 표현(확정
 * 표현·질환명, storytelling.validate)도 쓰지 않는다.
 */
export const GUIDANCE_LOADING = '사건에 맞는 수색 안내를 불러오고 있습니다.';
export const GUIDANCE_FALLBACK = '지도에서 색이 진한 곳부터 살펴봐 주세요.';

export function guidanceLine({ text, loading }: { text?: string | null; loading: boolean }): string {
  const t = text?.trim();
  if (t) return t;
  return loading ? GUIDANCE_LOADING : GUIDANCE_FALLBACK;
}
