/**
 * 하단 탭바 치수 — 기기 안전영역을 **더해서** 정한다.
 *
 * ## 왜 85px 를 그대로 쓰면 안 되나
 * 시안의 85 는 아이폰 X 프레임 기준값이라 그 안에 홈 인디케이터 몫(34)이 이미
 * 들어 있다(내용 51 + 인디케이터 34). 기기마다 다른 실제 안전영역을 반영하지
 * 못하는 고정값이다.
 *
 * 게다가 react-navigation 은 `tabBarStyle` 로 height 를 덮어써도
 * `paddingBottom: insets.bottom` 은 **그대로 넣는다** — BottomTabBar.js 에서
 * tabBarStyle 이 배열 마지막이라 height 만 이기고 paddingBottom 은 남는다.
 * 게다가 getTabBarHeight() 는 숫자 height 를 보면 안전영역을 더하지 않고
 * 그 값을 그대로 돌려준다. 그래서 인디케이터 몫이 **두 번** 빠졌다:
 *
 *     85(고정) − 34(insets.bottom) − 7(paddingTop) = 44px
 *     필요한 높이 = 아이콘 28 + 간격 1 + 라벨 13 = 42px
 *
 * 딱 잘리는 값이라 라벨 아래가 반쯤 잘려 보였다(실측 08-12, 아이폰 15 Pro).
 *
 * ## 뒤집는다
 * 내용 높이를 고정하고 안전영역을 **더한다**. 인디케이터가 없는 기기(안드로이드
 * 버튼 내비·데스크톱 브라우저)에서는 그만큼 낮아지고, 인디케이터가 큰 기기에서는
 * 알아서 늘어난다 — 기종별로 값을 따로 둘 필요가 없다.
 */
import { Platform } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

/**
 * 안전영역을 뺀 순수 내용 높이.
 *
 * **react-navigation 이 탭 아이템마다 `padding: 5` 를 넣는다** —
 * BottomTabItem.js 의 `tabVerticalUiKit`(기본 variant 가 'uikit'). 위아래로
 * 10px 이라 이걸 빼먹으면 딱 그만큼 라벨이 잘린다(실측 08-12 2차: 56 으로
 * 잡았더니 3px 모자랐다).
 *
 *     바 paddingTop 7 + 아이템 padding 5 + 아이콘 28 + 간격 1 + 라벨 13
 *       + 아이템 padding 5 = 59
 *
 * 아이콘 위 여백이 7+5=12 가 되는 셈이라, 아이템 패딩이 없는 일반 View 탭바
 * (FigmaFlowTabBar)는 paddingTop 을 12 로 줘야 같은 자리에 온다.
 */
export const TAB_CONTENT_H = 59;

/**
 * 일반 View 로 만든 탭바가 써야 할 paddingTop.
 * 내비게이터 탭바의 `7 + 아이템 padding 5` 와 같은 자리를 만든다.
 */
export const FLOW_TAB_PADDING_TOP = 12;

/**
 * 가짜 인디케이터를 그릴 때 **비워야 하는 아래 여백**.
 *
 * 막대는 `bottom: 8` 에 높이 5 라 아래에서 13px 를 차지한다. 그런데 내용 높이
 * (TAB_CONTENT_H=59)는 그 몫을 안 잡고 있어서, 라벨(41~54)과 막대(46~51)가
 * **겹쳤다** — 홈 인디케이터가 '사전등록'·'알림' 글씨를 가로지른다(제보 08-12).
 *
 * 13 에 숨 쉴 틈 3 을 더한다.
 */
const FAKE_INDICATOR_RESERVE = 16;

export type TabBarMetrics = {
  /** tabBarStyle.height (또는 일반 View 의 height). */
  height: number;
  /** 이 탭바가 **직접** 비워야 할 아래 여백. */
  paddingBottom: number;
  /** 시안의 검은 인디케이터 막대를 우리가 그려야 하는가. */
  showFakeIndicator: boolean;
};

export function useTabBarMetrics(): TabBarMetrics {
  const insets = useSafeAreaInsets();
  /**
   * 웹에서는 pwa.ts 가 이미 `#root { padding-bottom: env(safe-area-inset-bottom) }`
   * 로 앱 전체를 인디케이터 위로 올려 놨다. 여기서 또 빼면 탭바 아래에 34px
   * 흰 띠가 생긴다 — 남은 몫이 0 이라는 뜻이지, 안전영역을 무시하는 게 아니다.
   * (safe-area-context 는 웹에서도 env() 를 읽으므로 insets.bottom 자체는
   * 네이티브와 똑같이 34 로 들어온다.)
   */
  // OS 가 진짜 인디케이터를 그리는 기기에 가짜를 겹쳐 그리지 않는다.
  const showFakeIndicator = insets.bottom === 0;
  const reserve = showFakeIndicator
    // 우리가 막대를 그리면 그 몫을 우리가 비워야 한다.
    ? FAKE_INDICATOR_RESERVE
    : Platform.OS === 'web' ? 0 : insets.bottom;
  return {
    height: TAB_CONTENT_H + reserve,
    paddingBottom: reserve,
    showFakeIndicator,
  };
}
