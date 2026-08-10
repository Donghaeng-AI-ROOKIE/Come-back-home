import React from 'react';
import { StyleSheet, View } from 'react-native';
import { color } from '../theme/tokens';
import HomeIcon from '../../assets/figma/tab-home.svg';
import WalkIcon from '../../assets/figma/tab-walk.svg';
import AlertIcon from '../../assets/figma/tab-alert.svg';
import ProfileIcon from '../../assets/figma/tab-profile.svg';
import RegisterIcon from '../../assets/figma/tab-register.svg';

const icons = { home: HomeIcon, walk: WalkIcon, alert: AlertIcon, profile: ProfileIcon, register: RegisterIcon } as const;

export type FigmaTabIconName = keyof typeof icons;

export default function FigmaTabIcon({ name, focused, activeColor = color.brand }: {
  name: FigmaTabIconName;
  focused: boolean;
  activeColor?: string;
}) {
  const Icon = icons[name];
  const iconColor = focused ? activeColor : color.figmaGray;
  return <View style={[styles.icon, { opacity: focused ? 1 : 0.82 }]}><Icon width={24} height={24} color={iconColor} fill={iconColor} /></View>;
}

const styles = StyleSheet.create({ icon: { width: 30, height: 28, alignItems: 'center', justifyContent: 'center' } });
