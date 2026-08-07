/** 보호자 하단 4탭 (피그마 [보호자] 확정): 홈 / 사전등록 / 알림 / 내 정보. */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SvgXml } from 'react-native-svg';
import type { GuardianTabParamList } from './types';
import { color, radius, space, type } from '../theme/tokens';
import { gColor, gTabBar } from '../theme/guardianTokens';
import {
  tabAlertXml,
  tabHomeXml,
  tabMyXml,
  tabRegXml,
  tintXml,
} from '../assets/guardianSvg';
import CTAButton from '../components/CTAButton';
import GuardianHomeScreen from '../screens/GuardianHomeScreen';
import GuardianAlertsScreen from '../screens/GuardianAlertsScreen';
import RegChatScreen from '../screens/RegChatScreen';
import { useAuthStore } from '../store/authStore';
import { useGuardianStore } from '../store/guardianStore';

const Tab = createBottomTabNavigator<GuardianTabParamList>();

function TabIcon({ xml, focused }: { xml: string; focused: boolean }) {
  return <SvgXml xml={tintXml(xml, focused ? gColor.primary : gColor.gray)} width={24} height={25} />;
}

/** 내 정보 — 로그아웃과 등록 현황만. 시민 마이페이지(레벨·배지)와 다르다. */
function GuardianMyScreen() {
  const { user, logout } = useAuthStore();
  const persona = useGuardianStore((s) => s.persona);
  const reset = useGuardianStore((s) => s.reset);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.wrap}>
        <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          내 정보
        </Text>
        <View style={styles.card}>
          <Text style={styles.rowKey} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            보호자
          </Text>
          <Text style={styles.rowVal} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {user ?? '-'}
          </Text>
          <View style={styles.divider} />
          <Text style={styles.rowKey} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            등록된 가족
          </Text>
          <Text style={styles.rowVal} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {persona ? `${persona.name} (${persona.age}세)` : '없음'}
          </Text>
        </View>
        <View style={styles.spacer} />
        <CTAButton
          label="로그아웃"
          onPress={() => {
            reset();   // 역할을 바꿔 다시 로그인할 때 이전 보호자 등록이 남지 않게 한다
            logout();
          }}
          variant="ghost"
        />
      </View>
    </SafeAreaView>
  );
}

export default function GuardianTabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: gColor.primary,
        tabBarInactiveTintColor: gColor.gray,
        tabBarLabelStyle: { fontSize: 12, fontWeight: type.weight.medium, fontFamily: type.family },
        tabBarStyle: {
          backgroundColor: gColor.surface,
          borderTopWidth: 0,
          borderTopLeftRadius: gTabBar.radius,
          borderTopRightRadius: gTabBar.radius,
          height: gTabBar.height,
          paddingTop: 10,
          // 위쪽으로 뜨는 그림자 (피그마 Glassmorphism Background)
          shadowColor: '#000000',
          shadowOffset: { width: 0, height: -2 },
          shadowOpacity: 0.1,
          shadowRadius: 2,
          elevation: 8,
        },
      }}
    >
      <Tab.Screen
        name="GuardianHome"
        component={GuardianHomeScreen}
        options={{ tabBarLabel: '홈', tabBarIcon: ({ focused }) => <TabIcon xml={tabHomeXml} focused={focused} /> }}
      />
      <Tab.Screen
        name="GuardianReg"
        component={RegChatScreen}
        options={{ tabBarLabel: '사전등록', tabBarIcon: ({ focused }) => <TabIcon xml={tabRegXml} focused={focused} /> }}
      />
      <Tab.Screen
        name="GuardianAlerts"
        component={GuardianAlertsScreen}
        options={{ tabBarLabel: '알림', tabBarIcon: ({ focused }) => <TabIcon xml={tabAlertXml} focused={focused} /> }}
      />
      <Tab.Screen
        name="GuardianMy"
        component={GuardianMyScreen}
        options={{ tabBarLabel: '내 정보', tabBarIcon: ({ focused }) => <TabIcon xml={tabMyXml} focused={focused} /> }}
      />
    </Tab.Navigator>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  wrap: { flex: 1, padding: space.xl, gap: space.lg },
  title: { fontSize: type.size.title, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  card: { backgroundColor: color.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: color.border, padding: space.lg, gap: space.xs },
  rowKey: { fontSize: type.size.caption, fontWeight: type.weight.bold, color: color.textCaption, fontFamily: type.family },
  rowVal: { fontSize: type.size.label, fontWeight: type.weight.medium, color: color.text, fontFamily: type.family },
  divider: { height: 1, backgroundColor: color.border, marginVertical: space.md },
  spacer: { flex: 1 },
});
