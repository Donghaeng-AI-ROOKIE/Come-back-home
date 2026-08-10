import React, { useState } from 'react';
import { Image, Pressable, SafeAreaView, StyleSheet, Text, TextInput, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useAuthStore } from '../store/authStore';
import { color, type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';

const authLogo = require('../../assets/figma/auth-logo.png');
const startMascot = require('../../assets/figma/mascot-start.png');
type AuthStep = 'start' | 'login' | 'roles';

export default function AuthScreen() {
  const login = useAuthStore((s) => s.login);
  const [step, setStep] = useState<AuthStep>('start');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <View style={styles.body}>
        <View style={styles.mascotHalo} />
        <Text style={styles.tagline}>우리가 만드는 안심 귀가 네트워크</Text>
        <Image source={authLogo} resizeMode="contain" style={styles.logo} accessibilityLabel="돌아오길" />
        <Image source={startMascot} resizeMode="contain" style={styles.mascot} accessibilityLabel="돋보기를 든 돌아오길 악어 캐릭터" />

        {step === 'start' && (
          <>
            <View style={styles.introFrame}><Text style={styles.intro}>내 동네를 설정하고{`\n`}돌아오길과 함께 걸어 보세요 🏡</Text></View>
            <Pressable accessibilityRole="button" onPress={() => setStep('roles')} style={({ pressed }) => [styles.startButton, pressed && styles.pressed]}>
              <Text style={styles.startText}>시작하기 〉</Text>
            </Pressable>
            <View style={styles.loginRow}>
              <Text style={styles.accountText}>이미 계정이 있나요? </Text>
              <Pressable onPress={() => setStep('login')} hitSlop={10}><Text style={styles.loginText}>로그인</Text></Pressable>
            </View>
          </>
        )}

        {step === 'login' && (
          <>
            <SeparatorLabel label="이메일 주소로 로그인해 주세요" />
            <TextInput value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="이메일 주소" placeholderTextColor="#909090" style={[styles.input, styles.email]} />
            <TextInput value={password} onChangeText={setPassword} secureTextEntry placeholder="비밀번호" placeholderTextColor="#909090" style={[styles.input, styles.password]} onSubmitEditing={() => setStep('roles')} />
          </>
        )}

        {step === 'roles' && (
          <>
            <SeparatorLabel label="어떤 역할로 시작하시겠습니까?" />
            <RoleButton label="보호자로 시작하기" background={color.guardian} top={430} onPress={() => login('guardian')} />
            <RoleButton label="시민으로 시작하기" background={color.brand} top={488} onPress={() => login('citizen')} />
          </>
        )}
      </View>
      <View style={styles.homeIndicator} />
    </SafeAreaView>
  );
}

function SeparatorLabel({ label }: { label: string }) {
  return <View style={styles.separatorRow}><View style={styles.separator} /><Text style={styles.separatorText}>{label}</Text><View style={styles.separator} /></View>;
}

function RoleButton({ label, background, top, onPress }: { label: string; background: string; top: number; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [styles.roleButton, { backgroundColor: background, top }, pressed && styles.pressed]}>
      <Text style={styles.roleButtonText}>{label} 〉</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.guardianWash },
  body: { flex: 1, position: 'relative' },
  mascotHalo: { position: 'absolute', top: 144, left: 215, width: 121, height: 121, borderRadius: 61, backgroundColor: '#E2F4DB' },
  tagline: { position: 'absolute', top: 208, left: 63, width: 193, fontFamily: type.family, fontSize: 10, lineHeight: 19, color: color.figmaGray },
  logo: { position: 'absolute', top: 232, left: 38, width: 198, height: 66 },
  mascot: { position: 'absolute', top: 174, left: 227, width: 97, height: 146 },
  introFrame: { position: 'absolute', top: 372, left: 52, width: 272, height: 68, alignItems: 'center', justifyContent: 'center' },
  intro: { fontFamily: type.family, fontSize: 17, lineHeight: 24, color: '#525253', textAlign: 'center' },
  startButton: { position: 'absolute', top: 488, left: 16, right: 16, height: 50, borderRadius: 10, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center' },
  startText: { fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, color: '#FFFFFF' },
  loginRow: { position: 'absolute', top: 565, left: 91, width: 193, height: 19, flexDirection: 'row', alignItems: 'center', justifyContent: 'center' },
  accountText: { fontFamily: type.family, fontSize: 14, color: color.figmaGray },
  loginText: { fontFamily: type.familySemiBold, fontSize: 14, color: color.brandInk, textDecorationLine: 'underline' },
  separatorRow: { position: 'absolute', top: 370, left: 16, right: 16, height: 22, flexDirection: 'row', alignItems: 'center', gap: 20 },
  separator: { flex: 1, height: 1, backgroundColor: '#CAD9C5' },
  separatorText: { width: 190, textAlign: 'center', fontFamily: type.family, fontSize: 14, lineHeight: 19, color: color.figmaGray },
  input: { position: 'absolute', left: 16, right: 16, height: 46, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.9)', paddingHorizontal: 12, fontFamily: type.familySemiBold, fontSize: 16, color: '#525253' },
  email: { top: 429 },
  password: { top: 486 },
  roleButton: { position: 'absolute', left: 16, right: 16, height: 50, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  roleButtonText: { fontFamily: type.familyBold, fontSize: 17, color: '#FFFFFF' },
  homeIndicator: { position: 'absolute', bottom: 8, left: 120, width: 135, height: 5, borderRadius: 100, backgroundColor: '#000000' },
  pressed: { opacity: 0.82 },
});
