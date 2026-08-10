import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import FigmaTabIcon, { type FigmaTabIconName } from './FigmaTabIcon';

export default function FigmaFlowTabBar({ mode, active }: {
  mode: 'guardian' | 'citizen';
  active: 'home' | 'register' | 'alert' | 'profile';
}) {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const guardian = mode === 'guardian';
  const accent = guardian ? color.guardian : color.brand;
  const items: { key: typeof active; label: string; icon: FigmaTabIconName }[] = guardian
    ? [
        { key: 'home', label: '홈', icon: 'home' },
        { key: 'register', label: '사전등록', icon: 'register' },
        { key: 'alert', label: '알림', icon: 'alert' },
        { key: 'profile', label: '내 정보', icon: 'profile' },
      ]
    : [
        { key: 'home', label: '안심 홈', icon: 'home' },
        { key: 'register', label: '산책하기', icon: 'walk' },
        { key: 'alert', label: '긴급 알림', icon: 'alert' },
        { key: 'profile', label: '내 정보', icon: 'profile' },
      ];
  const goTo = (key: typeof active) => {
    if (guardian) {
      const screen = key === 'home' ? 'GuardianHome' : key === 'register' ? 'GuardianReg' : key === 'alert' ? 'GuardianAlerts' : 'GuardianMy';
      navigation.navigate('GuardianTabs', { screen });
      return;
    }
    const screen = key === 'home' ? 'Home' : key === 'register' ? 'Walk' : key === 'alert' ? 'Alerts' : 'Records';
    navigation.navigate('CitizenTabs', { screen });
  };
  return (
    <View style={styles.bar}>
      {items.map((item) => (
        <Pressable
          key={item.key}
          style={styles.item}
          onPress={() => goTo(item.key)}
        >
          <FigmaTabIcon name={item.icon} focused={active === item.key} activeColor={accent} />
          <Text style={[styles.label, active === item.key && { color: accent }]}>{item.label}</Text>
        </Pressable>
      ))}
      <View pointerEvents="none" style={styles.homeIndicator} />
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { height: 85, backgroundColor: '#FFFFFF', borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#D8D8D8', flexDirection: 'row', paddingTop: 7 },
  item: { flex: 1, alignItems: 'center' },
  label: { fontFamily: type.family, fontSize: 11, lineHeight: 13, color: color.figmaGray, marginTop: 1 },
  homeIndicator: { position: 'absolute', bottom: 8, left: '32%', right: '32%', height: 5, borderRadius: 100, backgroundColor: '#000000' },
});
