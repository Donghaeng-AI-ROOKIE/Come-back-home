/**
 * 시민 하단 4탭 (와이어프레임): 안심 홈 / 산책하기 / 긴급알림 / 내 기록.
 * 탭 활성색 = 현재 AppMode 토큰(walk=green / search=amber).
 *
 * 산책 탭은 화면을 갖지 않고 홈으로 되돌린다 — 산책은 "시작"이라는 동작이지
 * 상시 열어 두는 탭이 아니다. 진행 중이면 홈이 이어가기 버튼을 띄운다.
 */
import React from 'react';
import { Text } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import type { CitizenTabParamList } from './types';
import { color, type } from '../theme/tokens';
import { useModeTheme } from '../theme/theme';
import CitizenHomeScreen from '../screens/CitizenHomeScreen';
import SearchScreen from '../screens/SearchScreen';
import RecordsScreen from '../screens/RecordsScreen';

const Tab = createBottomTabNavigator<CitizenTabParamList>();

function TabIcon({ label, focused, activeColor }: { label: string; focused: boolean; activeColor: string }) {
  return (
    <Text
      style={{
        fontSize: 20,
        opacity: focused ? 1 : 0.5,
        // 색+투명도 이중부호화 (색만으로 상태 전달 금지)
        color: focused ? activeColor : color.textCaption,
      }}
    >
      {label}
    </Text>
  );
}

export default function CitizenTabs() {
  const t = useModeTheme();
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: t.accent,
        tabBarInactiveTintColor: color.textCaption,
        tabBarLabelStyle: { fontSize: 12, fontWeight: type.weight.bold, fontFamily: type.family },
        tabBarStyle: { backgroundColor: color.surface, borderTopColor: color.border, height: 88, paddingTop: 6 },
      }}
    >
      <Tab.Screen
        name="Home"
        component={CitizenHomeScreen}
        options={{
          tabBarLabel: '안심 홈',
          tabBarIcon: ({ focused }) => <TabIcon label="🏠" focused={focused} activeColor={t.accent} />,
        }}
      />
      <Tab.Screen
        name="Walk"
        component={CitizenHomeScreen}
        options={{
          tabBarLabel: '산책하기',
          tabBarIcon: ({ focused }) => <TabIcon label="🚶" focused={focused} activeColor={t.accent} />,
        }}
      />
      <Tab.Screen
        name="Alerts"
        component={SearchScreen}
        options={{
          tabBarLabel: '긴급알림',
          tabBarIcon: ({ focused }) => (
            <TabIcon label="🔔" focused={focused || t.mode === 'search'} activeColor={t.accent} />
          ),
        }}
      />
      <Tab.Screen
        name="Records"
        component={RecordsScreen}
        options={{
          tabBarLabel: '내 기록',
          tabBarIcon: ({ focused }) => <TabIcon label="👤" focused={focused} activeColor={t.accent} />,
        }}
      />
    </Tab.Navigator>
  );
}
