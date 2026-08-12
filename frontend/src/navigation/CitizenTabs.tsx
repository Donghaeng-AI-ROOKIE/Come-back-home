/**
 * 시민 하단 4탭 (와이어프레임): 안심 홈 / 산책하기 / 긴급알림 / 내 기록.
 * 탭 활성색 = 현재 AppMode 토큰(walk=green / search=amber).
 *
 * 산책 탭은 화면을 갖지 않고 홈으로 되돌린다 — 산책은 "시작"이라는 동작이지
 * 상시 열어 두는 탭이 아니다. 진행 중이면 홈이 이어가기 버튼을 띄운다.
 */
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { PlatformPressable } from '@react-navigation/elements';
import type { CitizenTabParamList } from './types';
import { color, type } from '../theme/tokens';
import { useTabBarMetrics } from '../theme/tabBar';
import { useKeyboardVisible } from '../hooks/useKeyboardVisible';
import CitizenHomeScreen from '../screens/CitizenHomeScreen';
import WalkActiveScreen from '../screens/WalkActiveScreen';
import CitizenAlertsScreen from '../screens/CitizenAlertsScreen';
import RecordsScreen from '../screens/RecordsScreen';
import FigmaTabIcon from '../components/FigmaTabIcon';

const Tab = createBottomTabNavigator<CitizenTabParamList>();

export default function CitizenTabs() {
  // 높이를 85 로 박아 두면 기기 안전영역이 이중으로 빠져 라벨이 잘린다 —
  // 사유는 theme/tabBar.ts 참고.
  const tabBar = useTabBarMetrics();
  // 키보드가 떠 있으면 탭바를 감춘다 — 앱이 보이는 높이로 줄어들면서 탭바가
  // 키보드 바로 위로 올라와 대화 영역을 잡아먹는다(hooks/useKeyboardVisible).
  const keyboardOpen = useKeyboardVisible();
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: color.brand,
        tabBarInactiveTintColor: color.textCaption,
        tabBarLabelStyle: { fontSize: 10, lineHeight: 13, letterSpacing: 0.16, fontFamily: type.familyCssBold, marginTop: 1 },
        tabBarStyle: {
          backgroundColor: color.surface,
          borderTopColor: color.border,
          height: tabBar.height,
          paddingTop: 7,
          paddingBottom: tabBar.paddingBottom,
          display: keyboardOpen ? 'none' : 'flex',
        },
        tabBarItemStyle: styles.tabItem,
        tabBarButton: (props) => <PlatformPressable {...props} style={[props.style, styles.tabButton]} />,
        tabBarBackground: () => (
          <View style={styles.tabBackground}>
            {tabBar.showFakeIndicator ? <View style={styles.homeIndicator} /> : null}
          </View>
        ),
      }}
    >
      <Tab.Screen
        name="Home"
        component={CitizenHomeScreen}
        options={{
          tabBarLabel: '안심 홈',
          tabBarIcon: ({ focused }) => <FigmaTabIcon name="home" focused={focused} activeColor={color.brand} />,
        }}
      />
      {/* 시안: 산책하기 탭 = '산책하기-이동 중' 화면. 홈을 다시 띄우면
          탭을 눌러도 아무 일이 없는 것처럼 보인다(현장 제보 08-11). */}
      <Tab.Screen
        name="Walk"
        component={WalkActiveScreen}
        options={{
          tabBarLabel: '산책하기',
          tabBarIcon: ({ focused }) => <FigmaTabIcon name="walk" focused={focused} activeColor={color.brand} />,
        }}
      />
      <Tab.Screen
        name="Alerts"
        component={CitizenAlertsScreen}
        options={{
          tabBarLabel: '긴급 알림',
          tabBarActiveTintColor: color.figmaRed,
          tabBarIcon: ({ focused }) => <FigmaTabIcon name="alert" focused={focused} activeColor={color.figmaRed} />,
        }}
      />
      <Tab.Screen
        name="Records"
        component={RecordsScreen}
        options={{
          tabBarLabel: '내 정보',
          tabBarIcon: ({ focused }) => <FigmaTabIcon name="profile" focused={focused} activeColor={color.brand} />,
        }}
      />
    </Tab.Navigator>
  );
}

const styles = StyleSheet.create({
  tabBackground: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, backgroundColor: '#FFFFFF' },
  tabItem: { outlineStyle: 'none' } as any,
  tabButton: { flex: 1, outlineStyle: 'none' } as any,
  homeIndicator: { position: 'absolute', bottom: 8, left: '32%', right: '32%', height: 5, borderRadius: 100, backgroundColor: '#000000' },
});
