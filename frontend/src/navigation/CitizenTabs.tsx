/**
 * 시민/보호자 소비자 앱 (라이트). 하단 3탭 홈/수색/등록 (spec §2.2).
 * 탭 활성색 = 현재 AppMode 토큰(walk=green / search=amber).
 */
import React from 'react';
import { Text } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import type { CitizenTabParamList } from './types';
import { color, type } from '../theme/tokens';
import { useModeTheme } from '../theme/theme';
import HomeScreen from '../screens/HomeScreen';
import SearchScreen from '../screens/SearchScreen';
import RegChatScreen from '../screens/RegChatScreen';

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
        component={HomeScreen}
        options={{
          tabBarLabel: '홈',
          tabBarIcon: ({ focused }) => <TabIcon label="🏠" focused={focused} activeColor={t.accent} />,
        }}
      />
      <Tab.Screen
        name="Search"
        component={SearchScreen}
        options={{
          tabBarLabel: '수색',
          tabBarIcon: ({ focused }) => <TabIcon label="🔍" focused={focused || t.mode === 'search'} activeColor={t.accent} />,
        }}
      />
      <Tab.Screen
        name="Reg"
        component={RegChatScreen}
        options={{
          tabBarLabel: '등록',
          tabBarIcon: ({ focused }) => <TabIcon label="👪" focused={focused} activeColor={t.accent} />,
        }}
      />
    </Tab.Navigator>
  );
}
