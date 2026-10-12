export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * 사건이 끝나 다시 물어도 소용없는 응답인가 — 폴링을 멈출 근거.
 *
 *  - 404: 삭제된 사건(cloud_bridge/policy 가 "사건을 찾을 수 없습니다"로 막는다).
 *  - 409 중 종결·삭제: lifecycle.ensure_not_closed 의 "종결된 케이스"/"삭제된 사건".
 *
 * 같은 409 라도 "POA 없음"(예측 전)은 곧 풀리는 상태라 여기서 빼야 한다 — 그래서
 * 상태코드만으로 가르지 않고 문구를 본다. 2026-10-12 운영에서 지워진 사건 하나를
 * 시민 앱이 5분간 21회(전부 404) 물으며 단일 계산 줄을 점유했다.
 */
export function isCaseEnded(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  if (error.status === 404) return true;
  return error.status === 409 && /종결된 케이스|삭제된 사건/.test(error.message);
}

