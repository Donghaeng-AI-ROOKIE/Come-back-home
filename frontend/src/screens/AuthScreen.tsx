/**
 * 데모 진입 — 역할 선택(시민/보호자/운영자). 실서비스에선 인증 토큰 role 클레임.
 * 역할이 RootNavigator의 마운트 트리를 결정 (spec §2.3).
 */
import React from 'react';
import { SafeAreaView, StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useAuthStore } from '../store/authStore';
import { color, radius, space, type } from '../theme/tokens';
import CTAButton from '../components/CTAButton';

export default function AuthScreen() {
  const login = useAuthStore((s) => s.login);
  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="dark" />
      <View style={styles.body}>
        <View style={styles.brand}>
          <Text style={styles.logo} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            돌아오길
          </Text>
          <Text style={styles.tag} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            평소엔 산책, 실종 땐 온 동네가 함께 찾는 앱
          </Text>
        </View>

        <View style={styles.picker}>
          <Text style={styles.pickerTitle}>어떤 역할로 둘러볼까요?</Text>
          <CTAButton label="시민 (제보자)" onPress={() => login('citizen')} accent={color.walk} />
          <View style={styles.gap} />
          <CTAButton label="보호자 (가족 등록자)" onPress={() => login('guardian')} accent={color.walk} variant="secondary" />
          <View style={styles.gap} />
          <CTAButton label="운영자 (경찰·관제)" onPress={() => login('operator')} accent={color.textBody} variant="ghost" />
        </View>

        <Text style={styles.note} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          데모용 역할 선택 화면입니다. 시민·보호자는 라이트 소비자 앱, 운영자는 다크 지휘 콘솔로 진입합니다.
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.surface },
  body: { flex: 1, paddingHorizontal: space.xl, justifyContent: 'center', gap: space.xxl },
  brand: { alignItems: 'center', gap: space.sm },
  logo: { fontSize: 34, fontWeight: type.weight.black, color: color.walk, fontFamily: type.family },
  tag: { fontSize: type.size.body, color: color.textBody, textAlign: 'center', fontFamily: type.family },
  picker: {
    backgroundColor: color.surfaceAlt,
    borderRadius: radius.xl,
    padding: space.xl,
    borderWidth: 1,
    borderColor: color.border,
  },
  pickerTitle: {
    fontSize: type.size.cardTitle,
    fontWeight: type.weight.black,
    color: color.text,
    marginBottom: space.lg,
    fontFamily: type.family,
  },
  gap: { height: space.md },
  note: { fontSize: type.size.caption, color: color.textCaption, textAlign: 'center', fontFamily: type.family, lineHeight: 20 },
});
