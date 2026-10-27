/**
 * 상황 종료 문구 — 종결 카드와 상세 화면이 같은 말을 하도록 한곳에 둔다.
 *
 * 서버가 주는 수는 **제보 건수**다(한 사람이 두 번 제보하면 2). 그래서 "N명"이
 * 아니라 "N건"으로 쓴다. 0건이면 숫자 없이 관심에 감사한다.
 */
export function resolvedMessage(tipCount?: number | null): string {
  const thanksTo = tipCount && tipCount > 0 ? `여러분의 제보 ${tipCount}건` : '여러분의 관심';
  return `${thanksTo} 덕분에 가족의 품으로 무사히 돌아갔습니다.`;
}

export function resolvedThanks(tipCount?: number | null): string {
  return tipCount && tipCount > 0 ? '제보해 주셔서 감사합니다.' : '함께 지켜봐 주셔서 감사합니다.';
}
