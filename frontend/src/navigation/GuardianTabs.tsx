/** 보호자 하단 4탭 (Figma): 홈 / 사전등록 / 알림 / 내 정보. */
import React, { useState } from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { PlatformPressable } from '@react-navigation/elements';
import type { GuardianTabParamList } from './types';
import { color, radius, space, type } from '../theme/tokens';
import CTAButton from '../components/CTAButton';
import GuardianHomeScreen from '../screens/GuardianHomeScreen';
import RegChatScreen from '../screens/RegChatScreen';
import { useAuthStore } from '../store/authStore';
import { useGuardianStore } from '../store/guardianStore';
import GuardianAlertsScreen from '../screens/GuardianAlertsScreen';
import FigmaTabIcon from '../components/FigmaTabIcon';
import { usePersonas } from '../hooks/queries';

const Tab = createBottomTabNavigator<GuardianTabParamList>();

/** 내 정보 — 로그아웃과 등록 현황만. 시민 마이페이지(레벨·배지)와 다르다. */
function GuardianMyScreen() {
  const { user, signOut, switchRole } = useAuthStore();
  const [switching, setSwitching] = useState(false);
  const cachedPersona = useGuardianStore((s) => s.persona);
  const reset = useGuardianStore((s) => s.reset);
  const { data: personas, isLoading } = usePersonas();
  const registered = personas?.length
    ? personas.map((persona) => `${persona.name} (${persona.age}세)`).join(', ')
    : cachedPersona ? `${cachedPersona.name} (${cachedPersona.age}세)` : '없음';

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
            {isLoading && !cachedPersona ? '불러오는 중…' : registered}
          </Text>
        </View>
        <View style={styles.spacer} />
        {/* 역할을 바꿔야 하는 경우가 실제로 있다 — 가입할 때 잘못 고르면 보호자
            계정으로는 산책·제보 화면에 갈 수 없고, 계정을 새로 만드는 수밖에
            없었다(현장 실측 08-11). 기록은 계정에 붙어 있어 그대로 남는다. */}
        <CTAButton
          label={switching ? '전환 중…' : '시민 모드로 전환'}
          onPress={async () => {
            if (switching) return;
            setSwitching(true);
            try {
              await switchRole('citizen');
            } catch (e) {
              Alert.alert('전환하지 못했습니다', String(e));
            } finally {
              setSwitching(false);
            }
          }}
          variant="ghost"
        />
        <View style={styles.switchGap} />
        <CTAButton
          label="로그아웃"
          onPress={() => {
            reset();   // 역할을 바꿔 다시 로그인할 때 이전 보호자 등록이 남지 않게 한다
            signOut();
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
        tabBarActiveTintColor: color.guardian,
        tabBarInactiveTintColor: color.figmaGray,
        tabBarLabelStyle: { fontSize: 11, lineHeight: 13, fontFamily: type.family, marginTop: 1 },
        tabBarStyle: { backgroundColor: color.surface, borderTopColor: color.border, height: 85, paddingTop: 7, borderTopLeftRadius: 42, borderTopRightRadius: 42, overflow: 'hidden' },
        tabBarItemStyle: styles.tabItem,
        tabBarButton: (props) => <PlatformPressable {...props} style={[props.style, styles.tabButton]} />,
        tabBarBackground: () => <View style={styles.tabBackground}><View style={styles.homeIndicator} /></View>,
      }}
    >
      <Tab.Screen
        name="GuardianHome"
        component={GuardianHomeScreen}
        options={{ tabBarLabel: '홈', tabBarIcon: ({ focused }) => <FigmaTabIcon name="home" focused={focused} activeColor={color.guardian} /> }}
      />
      <Tab.Screen
        name="GuardianReg"
        component={RegChatScreen}
        options={{ tabBarLabel: '사전등록', tabBarIcon: ({ focused }) => <FigmaTabIcon name="register" focused={focused} activeColor={color.guardian} /> }}
      />
      <Tab.Screen
        name="GuardianAlerts"
        component={GuardianAlertsScreen}
        options={{ tabBarLabel: '알림', tabBarIcon: ({ focused }) => <FigmaTabIcon name="alert" focused={focused} activeColor={color.guardian} /> }}
      />
      <Tab.Screen
        name="GuardianMy"
        component={GuardianMyScreen}
        options={{ tabBarLabel: '내 정보', tabBarIcon: ({ focused }) => <FigmaTabIcon name="profile" focused={focused} activeColor={color.guardian} /> }}
      />
    </Tab.Navigator>
  );
}

const styles = StyleSheet.create({
  tabBackground: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, backgroundColor: '#FFFFFF', borderTopLeftRadius: 42, borderTopRightRadius: 42 },
  tabItem: { outlineStyle: 'none' } as any,
  tabButton: { flex: 1, outlineStyle: 'none' } as any,
  homeIndicator: { position: 'absolute', bottom: 8, left: '32%', right: '32%', height: 5, borderRadius: 100, backgroundColor: '#000000' },
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  wrap: { flex: 1, padding: space.xl, gap: space.lg },
  title: { fontSize: type.size.title, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  card: { backgroundColor: color.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: color.border, padding: space.lg, gap: space.xs },
  rowKey: { fontSize: type.size.caption, fontWeight: type.weight.bold, color: color.textCaption, fontFamily: type.family },
  rowVal: { fontSize: type.size.label, fontWeight: type.weight.medium, color: color.text, fontFamily: type.family },
  divider: { height: 1, backgroundColor: color.border, marginVertical: space.md },
  switchGap: { height: 10 },
  spacer: { flex: 1 },
});
