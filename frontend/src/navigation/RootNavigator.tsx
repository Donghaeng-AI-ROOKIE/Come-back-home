/**
 * 최상위 역할·인증 게이트 (와이어프레임 2026-08-05). role 클레임이 마운트 트리를 결정한다.
 *
 * 보호자 트리와 시민 트리는 컴포넌트 트리 자체가 분리된다 — 한쪽에서 다른 쪽
 * 화면으로 갈 수 있으면 "보호자가 시민 제보를 한다" 같은 경로가 열려 권한 경계가
 * 흐려진다. 역할을 바꾸려면 로그아웃 후 다시 고른다.
 *
 * 운영자 트리는 제거됐다 — 와이어프레임에 없고 관제는 백엔드 /dashboard 가 맡는다.
 *
 * 소비자 플로우 모달(락스크린/경보상세/경보연동/제보/제보완료)은 CitizenTabs 와
 * 함께 루트에 등록한다.
 *
 * 경보 진입 관문(알림 개인화 #1): 시민이고 살아있는 경보가 있으면 첫 화면이
 * CitizenTabs(산책 모드)가 아니라 AlertDetail 이다. 판정 규칙은 useAlertGate 참고.
 */
import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { RootStackParamList } from './types';
import { useAuthStore } from '../store/authStore';
import { useAlertGate } from '../hooks/useAlertGate';
import { color } from '../theme/tokens';
import CitizenTabs from './CitizenTabs';
import GuardianTabs from './GuardianTabs';
import AuthScreen from '../screens/AuthScreen';

// 시민 — 수색·제보
import LockScreenAlert from '../screens/LockScreenAlert';
import AlertDetailScreen from '../screens/AlertDetailScreen';
import AlertSyncScreen from '../screens/AlertSyncScreen';
import AppearanceScreen from '../screens/AppearanceScreen';
import TipWarnScreen from '../screens/TipWarnScreen';
import ReportChatScreen from '../screens/ReportChatScreen';
import ReportDoneScreen from '../screens/ReportDoneScreen';

// 시민 — 산책
import WalkActiveScreen from '../screens/WalkActiveScreen';
import WalkSummaryScreen from '../screens/WalkSummaryScreen';

// 보호자 — 사전등록·신고
import RegChatScreen from '../screens/RegChatScreen';
import RegDoneScreen from '../screens/RegDoneScreen';
import PersonaDetailScreen from '../screens/PersonaDetailScreen';
import ReportScreen from '../screens/ReportScreen';
import ReportSentScreen from '../screens/ReportSentScreen';

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function RootNavigator() {
  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.role);
  // 경보 관문은 시민 트리에서만 선다. 운영자 역할은 이 브랜치에서 제거됐으므로
  // (관제 = 백엔드 /dashboard) 'citizen' 인지 직접 확인한다.
  const isCitizen = token != null && role === 'citizen';

  const gate = useAlertGate(isCitizen);

  // 경보 조회가 끝날 때까지 네비게이터를 마운트하지 않는다. initialRouteName 은
  // 마운트 시점에 한 번만 읽히므로, 로딩 중에 먼저 띄우면 "경보 없음"으로 굳어
  // 관문이 영영 안 선다. 인증 화면 부트스트랩과 같은 패턴.
  if (gate.pending) {
    return (
      <View style={styles.boot} accessible accessibilityLabel="경보를 확인하는 중입니다">
        <ActivityIndicator size="large" color={color.critical} />
      </View>
    );
  }

  return (
    <Stack.Navigator
      // 관문 판정은 initialRouteName 으로만 반영되는데, 이 값은 네비게이터가
      // **마운트될 때 한 번만** 읽힌다. 로그인 직후처럼 네비게이터가 이미 떠 있는
      // 상태에서 판정이 바뀌면 initialRouteName 이 무시되고 화면 목록의 첫 항목
      // (CitizenTabs)으로 떨어져 관문이 조용히 사라진다.
      //
      // 위의 gate.pending 스피너로 언마운트를 노렸지만 그 경로로는 부족하다:
      // useActiveAlerts 는 훅이라 로그인 화면에서도 이미 돌고 있어서, 사용자가
      // 로그인할 때쯤이면 조회가 끝나 있고 스피너를 거치지 않는다.
      //
      // 그래서 판정 자체를 key 에 묶는다 — 결정이 바뀌면 새로 마운트된다.
      key={`${token == null ? 'auth' : (role ?? 'none')}:${gate.caseId ?? 'nogate'}`}
      screenOptions={{ headerShown: false }}
      initialRouteName={gate.caseId ? 'AlertDetail' : undefined}
    >
      {token == null ? (
        <Stack.Screen name="Auth" component={AuthScreen} />
      ) : role === 'guardian' ? (
        <Stack.Group>
          <Stack.Screen name="GuardianTabs" component={GuardianTabs} />
          <Stack.Screen name="RegChat" component={RegChatScreen} />
          <Stack.Screen name="RegDone" component={RegDoneScreen} />
          <Stack.Screen name="PersonaDetail" component={PersonaDetailScreen} />
          <Stack.Screen name="Report" component={ReportScreen} />
          <Stack.Screen name="ReportSent" component={ReportSentScreen} />
        </Stack.Group>
      ) : (
        <Stack.Group>
          <Stack.Screen name="CitizenTabs" component={CitizenTabs} />
          <Stack.Screen
            name="AlertDetail"
            component={AlertDetailScreen}
            initialParams={gate.caseId ? { caseId: gate.caseId } : undefined}
          />
          <Stack.Screen name="AlertSync" component={AlertSyncScreen} />
          <Stack.Screen name="Appearance" component={AppearanceScreen} />
          <Stack.Screen name="TipWarn" component={TipWarnScreen} />
          <Stack.Screen name="ReportChat" component={ReportChatScreen} />
          <Stack.Screen name="ReportDone" component={ReportDoneScreen} />
          <Stack.Screen name="WalkActive" component={WalkActiveScreen} />
          <Stack.Screen name="WalkSummary" component={WalkSummaryScreen} />
          <Stack.Screen
            name="LockScreenAlert"
            component={LockScreenAlert}
            options={{ presentation: 'fullScreenModal', animation: 'fade' }}
          />
        </Stack.Group>
      )}
    </Stack.Navigator>
  );
}

const styles = StyleSheet.create({
  boot: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: color.surface },
});
