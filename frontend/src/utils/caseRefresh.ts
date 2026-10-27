/**
 * 사건 종결·삭제 직후 캐시 정리 — 보호자 사건 카드(components/LifecycleControls)가 쓴다.
 *
 * ## 왜 `clear()` 만으로는 부족했나
 * 예전에는 `cancelQueries()` 뒤 `clear()` 로 캐시를 통째로 비웠다. 지운 사건의
 * 정보가 다른 화면 캐시에 남지 않게 하려는 것이다. 그런데 `clear()` 는 조회를 캐시에서
 * **떼어 낼 뿐** 다시 묻지 않는다. 화면에 붙어 있던 사건 목록 조회는 떨어져 나간 채
 * 옛 결과를 계속 보여 주다가, 다음 주기 조회(15초)가 돌아서야 바뀌었다.
 * 10/27 운영: 종결 작업 1.3~3.9초, 카드가 "종결된 수색"으로 바뀌기까지 15.45~19.66초.
 *
 * ## 지금
 * - 화면에 붙어 있지 않은 조회는 그대로 데이터째 버린다(종결 사건의 지도, 시민
 *   경보 목록 등). 지운 정보가 남지 않게 하는 이유는 그대로다.
 * - 화면에 붙은 사건 목록은 버리지 않고 **곧바로 다시 받는다.** 새 결과가 옛 결과를
 *   덮으므로 지운 사건도 그 순간 목록에서 빠진다.
 * - 사건과 무관한 화면(가족 목록 등)은 건드리지 않는다. 종결로 바뀌는 값이 없다.
 */
import type { QueryClient } from '@tanstack/react-query';

/** 사건 목록 조회 키의 머리(hooks/queries.ts 의 useGuardianCases). */
const CASE_LIST_KEY = ['guardianCases'];

export async function refreshAfterCaseChange(qc: QueryClient): Promise<void> {
  await qc.cancelQueries({ type: 'inactive' });
  qc.removeQueries({ type: 'inactive' });
  // 진행 중이던 같은 조회는 취소하고 새로 묻는다(cancelRefetch 기본값). 실패해도
  // 던지지 않는다 — 종결은 이미 끝났고, 주기 조회가 다음에 다시 묻는다.
  await qc.refetchQueries({ queryKey: CASE_LIST_KEY, type: 'active' });
  // 그사이 화면이 다른 조회로 옮겨 갔으면 떨어져 나간 조회도 버린다. 삭제는 기기의
  // 사건 ID 목록을 바꿔 목록 조회 키 자체가 바뀌고(useGuardianCases), 종결은 지도
  // 조회를 끊는다. 그대로 두면 지운 사건이 든 옛 결과가 캐시에 5분(gcTime) 남는다.
  qc.removeQueries({ type: 'inactive' });
}
