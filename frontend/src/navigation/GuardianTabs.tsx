/** 보호자 하단 3탭 (와이어프레임): 홈 / 사전등록 / 내 정보. */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import type { GuardianTabParamList } from './types';
import { color, radius, space, type } from '../theme/tokens';
import CTAButton from '../components/CTAButton';
import GuardianHomeScreen from '../screens/GuardianHomeScreen';
import RegChatScreen from '../screens/RegChatScreen';
import { useAuthStore } from '../store/authStore';
import { useGuardianStore } from '../store/guardianStore';

const Tab = createBottomTabNavigator<GuardianTabParamList>();

function TabIcon({ label, focused }: { label: string; focused: boolean }) {
  return (
    <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.5, color: focused ? color.text : color.textCaption }}>
      {label}
    </Text>
  );
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
        tabBarActiveTintColor: color.text,
        tabBarInactiveTintColor: color.textCaption,
        tabBarLabelStyle: { fontSize: 12, fontWeight: type.weight.bold, fontFamily: type.family },
        tabBarStyle: { backgroundColor: color.surface, borderTopColor: color.border, height: 88, paddingTop: 6 },
      }}
    >
      <Tab.Screen
        name="GuardianHome"
        component={GuardianHomeScreen}
        options={{ tabBarLabel: '홈', tabBarIcon: ({ focused }) => <TabIcon label="🏠" focused={focused} /> }}
      />
      <Tab.Screen
        name="GuardianReg"
        component={RegChatScreen}
        options={{ tabBarLabel: '사전등록', tabBarIcon: ({ focused }) => <TabIcon label="💬" focused={focused} /> }}
      />
      <Tab.Screen
        name="GuardianMy"
        component={GuardianMyScreen}
        options={{ tabBarLabel: '내 정보', tabBarIcon: ({ focused }) => <TabIcon label="👤" focused={focused} /> }}
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
