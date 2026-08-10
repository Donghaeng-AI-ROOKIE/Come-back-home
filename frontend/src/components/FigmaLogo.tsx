import React from 'react';
import { Image, StyleSheet } from 'react-native';

const guardian = require('../../assets/figma/logo-guardian.png');
const citizen = require('../../assets/figma/logo-citizen.png');

export default function FigmaLogo({ mode }: { mode: 'guardian' | 'citizen' }) {
  const isGuardian = mode === 'guardian';
  return (
    <Image
      source={isGuardian ? guardian : citizen}
      resizeMode="contain"
      accessibilityLabel={isGuardian ? '돌아오길 보호자 안심 모드' : '돌아오길'}
      style={isGuardian ? styles.guardian : styles.citizen}
    />
  );
}

const styles = StyleSheet.create({
  guardian: { width: 77, height: 42 },
  citizen: { width: 57, height: 31 },
});
