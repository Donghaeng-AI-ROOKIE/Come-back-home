/**
 * 하단 탭의 강조색 — 실종이 발생해 긴급 모드가 켜진 동안은 빨강.
 *
 * 보호자 하단 탭은 언제나 보호자 초록이었다. 실종 신고를 하는 중에도, 신고 뒤 수색이
 * 진행 중일 때도 같아서, 지금이 평소인지 긴급 상황인지 탭바로는 알 수 없었다(10/27
 * 화면흐름 보드 의견). 시민의 긴급 알림 흐름처럼 빨강으로 강조한다.
 *
 * ## 보호자 — 다음 중 하나면 긴급 모드
 * - 실종 신고 흐름 화면(Report·ReportSent)에 있다. 접수 직후에는 새 사건이 목록에 아직
 *   없을 수 있지만, 신고하는 중이면 긴급이다.
 * - 진행 중 사건이 1건 이상이다. 진행 중의 정의는 홈 "수색 중" 카드와 같다(utils/guardianSearchCard
 *   의 activeCases — intake·predicted·searching). 건수는 부르는 쪽이 그 함수로 센다 — 규칙을
 *   여기 다시 적으면 홈 카드와 탭 색이 서로 다른 사건을 진행 중으로 볼 수 있다.
 *
 * 종결·철회로 진행 중 사건이 0건이 되면 보호자 초록으로 돌아온다.
 *
 * ## 시민 — 긴급 알림 탭과 그 흐름만 빨강
 * 경보 상세·수색지도·인상착의·제보·제보 완료·상황 종료 상세는 "긴급 알림" 탭을 켜고, 그 탭의
 * 강조색이 빨강이다. 안심 홈·산책하기·내 정보는 brand 색 그대로다.
 *
 * 수색 모드(store/appModeStore 의 mode === 'search')로는 바꾸지 않는다. 켜는 곳은 경보 상세와
 * 수색지도 두 곳인데, 끄는 곳은 열려 있는 수색지도가 사건 종결을 알아챘을 때 하나뿐이다. 경보
 * 상세만 보고 나오거나 "안볼래요"를 누른 뒤 사건이 끝나면 앱을 다시 켤 때까지 'search' 로
 * 남는다 — 그 값으로 칠하면 끝난 사건에도 탭이 빨강으로 남는다.
 *
 * 색 값이 아니라 토큰 이름(theme/tokens 의 color 키)을 돌려준다.
 * 이 파일은 node 시험이 직접 읽으므로 다른 파일을 import 하지 않는다.
 */

export type TabAccent = 'guardian' | 'brand' | 'figmaRed';

/** 탭 내비게이터 밖 화면의 탭바(components/FigmaFlowTabBar)가 쓰는 탭 이름. */
export type FlowTabKey = 'home' | 'register' | 'alert' | 'profile';

/** 보호자 긴급 모드인가 — 신고 흐름 화면이거나, 진행 중 사건이 1건 이상. */
export function guardianEmergency(inReportFlow: boolean, activeCaseCount: number): boolean {
  return inReportFlow || activeCaseCount > 0;
}

/** 보호자 탭의 강조색. 긴급 모드면 네 탭 모두 빨강이다. */
export function guardianTabAccent(emergency: boolean): TabAccent {
  return emergency ? 'figmaRed' : 'guardian';
}

/** 시민 탭의 강조색 — 긴급 알림 탭만 빨강. */
export function citizenTabAccent(tab: FlowTabKey | null): TabAccent {
  return tab === 'alert' ? 'figmaRed' : 'brand';
}
