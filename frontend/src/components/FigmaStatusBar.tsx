import React from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';
import StatusIcons from '../../assets/figma/status-bar.svg';

/** Native에서는 OS 상태바가, web 목업에서는 Figma 상태바 에셋이 같은 44px을 차지한다. */
export default function FigmaStatusBar() {
  if (Platform.OS !== 'web') return null;
  return (
    <View style={styles.bar}>
      <Text style={styles.time}>9:41</Text>
      <StatusIcons width={67} height={12} style={styles.icons} />
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { width: '100%', height: 44 },
  time: { position: 'absolute', left: 20, top: 12, width: 54, textAlign: 'center', fontSize: 15, lineHeight: 18, fontWeight: '600', color: '#000000' },
  icons: { position: 'absolute', right: 14, top: 16 },
});
