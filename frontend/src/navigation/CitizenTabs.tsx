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
import type { CitizenTabParamList } from './types';
import { color, type } from '../theme/tokens';
import { useModeTheme } from '../theme/theme';
import CitizenHomeScreen from '../screens/CitizenHomeScreen';
import CitizenAlertsScreen from '../screens/CitizenAlertsScreen';
import RecordsScreen from '../screens/RecordsScreen';
import FigmaTabIcon from '../components/FigmaTabIcon';

const Tab = createBottomTabNavigator<CitizenTabParamList>();

export default function CitizenTabs() {
  const t = useModeTheme();
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: t.accent,
        tabBarInactiveTintColor: color.textCaption,
        tabBarLabelStyle: { fontSize: 11, lineHeight: 13, fontFamily: type.family, marginTop: 1 },
        tabBarStyle: { backgroundColor: color.surface, borderTopColor: color.border, height: 85, paddingTop: 7 },
        tabBarBackground: () => <View style={styles.tabBackground}><View style={styles.homeIndicator} /></View>,
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
      <Tab.Screen
        name="Walk"
        component={CitizenHomeScreen}
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
          tabBarIcon: ({ focused }) => (
            <FigmaTabIcon name="alert" focused={focused || t.mode === 'search'} activeColor={t.accent} />
          ),
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
  homeIndicator: { position: 'absolute', bottom: 8, left: '32%', right: '32%', height: 5, borderRadius: 100, backgroundColor: '#000000' },
});
