import React, { useState } from 'react';
import { ActivityIndicator, Image, Pressable, SafeAreaView, StyleSheet, Text, TextInput, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useAuthStore } from '../store/authStore';
import type { Role } from '../types/domain';
import { color, type } from '../theme/tokens';
import FigmaStatusBar from '../components/FigmaStatusBar';

const authLogo = require('../../assets/figma/auth-logo.png');
const startMascot = require('../../assets/figma/mascot-start.png');
/**
 * 피그마 「초기 로그인 v2」 3화면 그대로:
 *   1. start  — 시작하기 / "이미 계정이 있나요? 로그인"
 *   2. form   — 이메일 주소·비밀번호 (가입·로그인 공용, 제목만 다르다)
 *   3. roles  — 어떤 역할로 시작하시겠습니까
 *
 * 시작하기 → 역할 선택 → 가입 폼. 로그인 → 로그인 폼.
 * 역할을 폼 안의 칩으로 합치지 않는다 — 시안이 별도 화면으로 잡아 둔 단계다.
 */
type AuthStep = 'start' | 'roles' | 'form';

/** 서버 오류 메시지를 그대로 보여준다 — "실패했습니다"로 뭉개면 왜 안 되는지 모른다. */
function errorText(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e);
  return m.replace(/^\d+\s*/, '') || '연결에 실패했습니다. 네트워크를 확인해 주세요.';
}

export default function AuthScreen() {
  const signIn = useAuthStore((s) => s.signIn);
  const signUp = useAuthStore((s) => s.signUp);
  const [step, setStep] = useState<AuthStep>('start');
  const [mode, setMode] = useState<'signup' | 'login'>('login');
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
      if (mode === 'signup') await signUp(loginId, password, role);
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
        <Text style={styles.tagline}>우리가 만드는 안심 귀가 네트워크</Text>
        <Image source={authLogo} resizeMode="contain" style={styles.logo} accessibilityLabel="돌아오길" />
        <Image source={startMascot} resizeMode="contain" style={styles.mascot} accessibilityLabel="돋보기를 든 돌아오길 악어 캐릭터" />

        {step === 'start' && (
          <>
            <View style={styles.introFrame}><Text style={styles.intro}>내 동네를 설정하고{`\n`}돌아오길과 함께 걸어 보세요 🏡</Text></View>
            <Pressable accessibilityRole="button" onPress={() => { setError(''); setMode('signup'); setStep('roles'); }} style={({ pressed }) => [styles.startButton, pressed && styles.pressed]}>
              <Text style={styles.startText}>시작하기 〉</Text>
            </Pressable>
            <View style={styles.loginRow}>
              <Text style={styles.accountText}>이미 계정이 있나요? </Text>
              <Pressable onPress={() => { setError(''); setMode('login'); setStep('form'); }} hitSlop={10}><Text style={styles.loginText}>로그인</Text></Pressable>
            </View>
          </>
        )}

        {step === 'roles' && (
          <>
            <SeparatorLabel label="어떤 역할로 시작하시겠습니까?" />
            <RoleButton
              label="보호자로 시작하기"
              background={color.guardian}
              top={430}
              onPress={() => { setRole('guardian'); setStep('form'); }}
            />
            <RoleButton
              label="시민으로 시작하기"
              background={color.brand}
              top={488}
              onPress={() => { setRole('citizen'); setStep('form'); }}
            />
          </>
        )}

        {step === 'form' && (
          <>
            <SeparatorLabel
              label={mode === 'signup' ? '이메일 주소로 가입해 주세요' : '이메일 주소로 로그인해 주세요'}
            />
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

            {/* 시안의 역할 버튼이 있던 자리(top 545)를 확인 버튼이 이어받는다.
                더 아래로 내리면 작은 화면에서 화면 밖으로 밀려 눌리지 않는다. */}
            <Pressable
              accessibilityRole="button"
              onPress={submit}
              disabled={busy}
              style={({ pressed }) => [
                styles.roleButton,
                { backgroundColor: mode === 'signup' && role === 'guardian' ? color.guardian : color.brand, top: 545 },
                (pressed || busy) && styles.pressed,
              ]}
            >
              {busy ? <ActivityIndicator color="#FFFFFF" /> : (
                <Text style={styles.roleButtonText}>{mode === 'signup' ? '가입하고 시작하기' : '로그인'} 〉</Text>
              )}
            </Pressable>

            <Pressable
              onPress={() => { setError(''); setStep(mode === 'signup' ? 'start' : 'start'); }}
              hitSlop={10}
              style={styles.backRow}
            >
              <Text style={styles.loginText}>{mode === 'signup' ? '처음으로' : '계정 만들기'}</Text>
            </Pressable>
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
  error: { position: 'absolute', top: 508, left: 16, right: 16, fontFamily: type.family, fontSize: 12, lineHeight: 17, color: color.criticalInk },
  backRow: { position: 'absolute', top: 607, left: 16, right: 16, alignItems: 'center' },
  roleButtonText: { fontFamily: type.familyBold, fontSize: 17, color: '#FFFFFF' },
  homeIndicator: { position: 'absolute', bottom: 8, left: 120, width: 135, height: 5, borderRadius: 100, backgroundColor: '#000000' },
  pressed: { opacity: 0.82 },
});
