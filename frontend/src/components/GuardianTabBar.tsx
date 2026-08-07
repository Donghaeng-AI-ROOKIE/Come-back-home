import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { SvgXml } from 'react-native-svg';

import type { GuardianTabParamList, RootStackParamList } from '../navigation/types';
import { gColor, gFont, gTabBar } from '../theme/guardianTokens';
import { tabAlertXml, tabHomeXml, tabMyXml, tabRegXml, tintXml } from '../assets/guardianSvg';

type TabName = keyof GuardianTabParamList;

const tabs: { name: TabName; label: string; xml: string }[] = [
  { name: 'GuardianHome', label: '홈', xml: tabHomeXml },
  { name: 'GuardianReg', label: '사전등록', xml: tabRegXml },
  { name: 'GuardianAlerts', label: '알림', xml: tabAlertXml },
  { name: 'GuardianMy', label: '내 정보', xml: tabMyXml },
];

function TabItem({
  label,
  xml,
  focused,
  accent,
  onPress,
}: {
  label: string;
  xml: string;
  focused: boolean;
  accent: string;
  onPress: () => void;
}) {
  const tint = focused ? accent : gColor.gray;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="tab"
      accessibilityState={{ selected: focused }}
      accessibilityLabel={label}
      style={({ pressed }) => [styles.item, pressed && styles.pressed]}
    >
      <SvgXml xml={tintXml(xml, tint)} width={24} height={25} />
      <Text style={[styles.label, { color: tint }]}>{label}</Text>
    </Pressable>
  );
}

/** BottomTabNavigator 안에서 쓰는 Figma 동일 탭바. */
export function GuardianNavigatorTabBar({ state, navigation }: BottomTabBarProps) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.bar, { height: gTabBar.height + insets.bottom, paddingBottom: insets.bottom }]}>
      {tabs.map((tab) => {
        const index = state.routes.findIndex((route) => route.name === tab.name);
        const focused = index === state.index;
        return (
          <TabItem
            key={tab.name}
            {...tab}
            focused={focused}
            accent={gColor.primary}
            onPress={() => {
              const event = navigation.emit({ type: 'tabPress', target: state.routes[index]?.key, canPreventDefault: true });
              if (!focused && !event.defaultPrevented) navigation.navigate(tab.name);
            }}
          />
        );
      })}
    </View>
  );
}

/** 루트 스택의 보호자 상세/완료 화면에도 같은 탭바를 유지한다. */
export function GuardianStandaloneTabBar({
  active,
  accent = gColor.primary,
}: {
  active: TabName;
  accent?: string;
}) {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  return (
    <View style={[styles.bar, { height: gTabBar.height + insets.bottom, paddingBottom: insets.bottom }]}>
      {tabs.map((tab) => (
        <TabItem
          key={tab.name}
          {...tab}
          focused={tab.name === active}
          accent={accent}
          onPress={() => navigation.popTo('GuardianTabs', { screen: tab.name })}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: gColor.surface,
    borderTopLeftRadius: gTabBar.radius,
    borderTopRightRadius: gTabBar.radius,
    paddingTop: 12,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 8,
  },
  item: { flex: 1, alignItems: 'center', justifyContent: 'flex-start', gap: 5, minHeight: 54 },
  label: { fontFamily: gFont.regular, fontSize: 11, lineHeight: 14 },
  pressed: { opacity: 0.65 },
});
