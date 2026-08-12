import React, { useState } from 'react';
import { ActivityIndicator, Image, Pressable, SafeAreaView, StyleSheet, Text, TextInput, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useAuthStore } from '../store/authStore';
import type { Role } from '../types/domain';
import { color, type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';
import { useTabBarMetrics } from '../theme/tabBar';
import AuthIntroText from '../../assets/figma/auth-intro-text.svg';
import AuthAccountText from '../../assets/figma/auth-account-text.svg';
import AuthTaglineText from '../../assets/figma/auth-tagline-text.svg';
import AuthLoginLabel from '../../assets/figma/auth-login-label.svg';
import AuthRoleLabel from '../../assets/figma/auth-role-label.svg';

const authLogo = require('../../assets/figma/auth-logo.png');
const startMascot = require('../../assets/figma/mascot-start.png');
type AuthStep = 'start' | 'role' | 'login' | 'signup';

/** 서버 오류 메시지를 그대로 보여준다 — "실패했습니다"로 뭉개면 왜 안 되는지 모른다. */
function errorText(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e);
  return m.replace(/^\d+\s*/, '') || '연결에 실패했습니다. 네트워크를 확인해 주세요.';
}

export default function AuthScreen() {
  // 시안의 검은 인디케이터 막대는 **그림**이다. OS 가 진짜를 그리는 기기에서는
  // 두 개가 겹쳐 보이므로 안전영역이 0 일 때만 그린다 (theme/tabBar.ts).
  const { showFakeIndicator } = useTabBarMetrics();
  const signIn = useAuthStore((s) => s.signIn);
  const signUp = useAuthStore((s) => s.signUp);
  const [step, setStep] = useState<AuthStep>('start');
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<Role>('citizen');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (busy) return;
    setError('');
    setBusy(true);
    try {
      if (step === 'signup') await signUp(loginId, password, role);
      else await signIn(loginId, password);
      // 성공하면 이 화면이 통째로 언마운트된다(RootNavigator 가 역할 트리로 바꾼다).
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="dark" />
      <FigmaStatusBar />
      <View style={styles.body}>
        <View style={styles.mascotHalo} />
        <AuthTaglineText width={131} height={9} style={styles.tagline} accessibilityLabel="우리가 만드는 안심 귀가 네트워크" />
        <Image source={authLogo} resizeMode="contain" style={styles.logo} accessibilityLabel="돌아오길" />
        <Image source={startMascot} resizeMode="contain" style={styles.mascot} accessibilityLabel="돋보기를 든 돌아오길 악어 캐릭터" />

        {step === 'start' && (
          <>
            <View style={styles.introFrame}><AuthIntroText width={251} height={42} accessibilityLabel="내 동네를 설정하고 돌아오길과 함께 걸어 보세요" /></View>
            <Pressable accessibilityRole="button" onPress={() => { setError(''); setStep('role'); }} style={({ pressed }) => [styles.startButton, pressed && styles.pressed]}>
              <Text style={styles.startText}>시작하기 〉</Text>
            </Pressable>
            <View style={styles.loginRow}>
              <AuthAccountText width={168} height={14} accessibilityLabel="이미 계정이 있나요? 로그인" />
              <Pressable accessibilityRole="button" accessibilityLabel="로그인" onPress={() => { setError(''); setStep('login'); }} hitSlop={10} style={styles.loginHit} />
            </View>
          </>
        )}

        {step === 'role' && (
          <>
            <SeparatorLabel label="어떤 역할로 시작하시겠습니까?" />
            <RoleChoice label="보호자로 시작하기 〉" tone="guardian" onPress={() => { setRole('guardian'); setError(''); setStep('signup'); }} style={styles.guardianChoice} />
            <RoleChoice label="시민으로 시작하기 〉" tone="citizen" onPress={() => { setRole('citizen'); setError(''); setStep('signup'); }} style={styles.citizenChoice} />
          </>
        )}

        {(step === 'login' || step === 'signup') && (
          <>
            {/* 시안 문구 그대로 — 필드도 "이메일 주소"다(가입만 문장을 바꾼다). */}
            <SeparatorLabel label={step === 'signup' ? '이메일 주소로 가입해 주세요' : '이메일 주소로 로그인해 주세요'} />
            <TextInput
              value={loginId}
              onChangeText={setLoginId}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              textContentType="username"
              placeholder="이메일 주소"
              placeholderTextColor="#909090"
              style={[styles.input, styles.email]}
              accessibilityLabel="이메일 주소"
              editable={!busy}
            />
            <TextInput
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoCapitalize="none"
              textContentType="password"
              placeholder="비밀번호"
              placeholderTextColor="#909090"
              style={[styles.input, styles.password]}
              accessibilityLabel="비밀번호"
              editable={!busy}
              onSubmitEditing={submit}
              returnKeyType="go"
            />

            {error ? <Text style={styles.error} accessibilityRole="alert">{error}</Text> : null}

            <Pressable
              accessibilityRole="button"
              onPress={submit}
              disabled={busy}
              style={({ pressed }) => [styles.submitButton, { backgroundColor: step === 'signup' && role === 'guardian' ? color.guardian : color.brand }, (pressed || busy) && styles.pressed]}
            >
              {busy ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.roleButtonText}>{step === 'signup' ? '가입하고 시작하기' : '로그인'} 〉</Text>}
            </Pressable>

            <Pressable onPress={() => { setError(''); setStep(step === 'signup' ? 'login' : 'role'); }} hitSlop={10} style={styles.switchRow}>
              <Text style={styles.loginText}>{step === 'signup' ? '이미 계정이 있어요' : '계정 만들기'}</Text>
            </Pressable>
          </>
        )}
      </View>
      {showFakeIndicator ? <View style={styles.homeIndicator} /> : null}
    </SafeAreaView>
  );
}

function SeparatorLabel({ label }: { label: string }) {
  const exactLabel = label === '어떤 역할로 시작하시겠습니까?'
    ? <AuthRoleLabel width={188} height={14} accessibilityLabel={label} />
    : label === '이메일 주소로 로그인해 주세요'
      ? <AuthLoginLabel width={184} height={14} accessibilityLabel={label} />
      : <Text style={styles.separatorText}>{label}</Text>;
  return <View style={styles.separatorRow}><View style={styles.separator} /><View style={styles.separatorLabel}>{exactLabel}</View><View style={styles.separator} /></View>;
}

function RoleChoice({ label, tone, onPress, style }: { label: string; tone: 'guardian' | 'citizen'; onPress: () => void; style: object }) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [styles.roleChoice, style, tone === 'guardian' ? styles.guardianTone : styles.citizenTone, pressed && styles.pressed]}
    >
      <Text style={styles.roleChoiceText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.guardianWash },
  body: { flex: 1, position: 'relative' },
  mascotHalo: { position: 'absolute', top: 144, left: 215, width: 121, height: 121, borderRadius: 61, backgroundColor: '#E2F4DB' },
  tagline: { position: 'absolute', top: 208, left: 63 },
  // Figma 원본은 153×75 로 내보낸 로고를 1:1 크기로 놓는다. 넓은 컨테이너에
  // contain으로 넣으면 높이에 맞춰 135px까지 줄어 실제 시안보다 작아진다.
  logo: { position: 'absolute', top: 230, left: 51, width: 174, height: 83 },
  mascot: { position: 'absolute', top: 174, left: 227, width: 97, height: 146 },
  introFrame: { position: 'absolute', top: 372, left: 52, width: 272, height: 68, alignItems: 'center', justifyContent: 'center' },
  startButton: { position: 'absolute', top: 488, left: 16, right: 16, height: 50, borderRadius: 10, backgroundColor: color.brand, alignItems: 'center', justifyContent: 'center' },
  startText: { fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#FFFFFF' },
  loginRow: { position: 'absolute', top: 565, left: 91, width: 193, height: 19, flexDirection: 'row', alignItems: 'center', justifyContent: 'center' },
  loginHit: { position: 'absolute', right: 10, top: -8, width: 54, height: 30 },
  loginText: { fontFamily: type.familySemiBold, fontSize: 14, color: color.brandInk, textDecorationLine: 'underline' },
  separatorRow: { position: 'absolute', top: 370, left: 16, right: 16, height: 22, flexDirection: 'row', alignItems: 'center', gap: 20 },
  separator: { flex: 1, height: 1, backgroundColor: '#CAD9C5' },
  separatorLabel: { width: 190, height: 19, alignItems: 'center', justifyContent: 'center' },
  separatorText: { width: 190, textAlign: 'center', fontFamily: type.family, fontSize: 14, lineHeight: 19, color: color.figmaGray },
  input: { position: 'absolute', left: 16, right: 16, height: 46, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.9)', paddingHorizontal: 12, fontFamily: type.familySemiBold, fontSize: 16, color: '#525253' },
  email: { top: 429 },
  password: { top: 486 },
  roleChoice: { position: 'absolute', left: 16, right: 16, height: 50, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  guardianChoice: { top: 430 },
  citizenChoice: { top: 488 },
  guardianTone: { backgroundColor: color.guardian },
  citizenTone: { backgroundColor: color.brand },
  roleChoiceText: { fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#FFFFFF' },
  error: { position: 'absolute', top: 545, left: 16, right: 16, fontFamily: type.family, fontSize: 13, lineHeight: 18, letterSpacing: -0.08, color: color.criticalInk },
  submitButton: { position: 'absolute', top: 575, left: 16, right: 16, height: 50, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  switchRow: { position: 'absolute', top: 643, left: 16, right: 16, alignItems: 'center' },
  roleButtonText: { fontFamily: type.familyBold, fontSize: 17, lineHeight: 22, letterSpacing: -0.41, color: '#FFFFFF' },
  homeIndicator: { position: 'absolute', bottom: 8, left: 120, width: 135, height: 5, borderRadius: 100, backgroundColor: '#000000' },
  pressed: { opacity: 0.82 },
});
