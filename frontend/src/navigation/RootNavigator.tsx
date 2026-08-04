/**
 * 최상위 역할·인증 게이트 (spec §2.2). role 클레임이 마운트 트리를 결정.
 * 운영자 스택은 시민 트리에 부재 — 컴포넌트 트리 자체가 분리.
 * 소비자 플로우 모달(락스크린/경보상세/경보연동/제보/제보완료)은 CitizenTabs와 함께 루트에 등록.
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
import OperatorStack from './OperatorStack';
import AuthScreen from '../screens/AuthScreen';
import LockScreenAlert from '../screens/LockScreenAlert';
import AlertDetailScreen from '../screens/AlertDetailScreen';
import AlertSyncScreen from '../screens/AlertSyncScreen';
import ReportChatScreen from '../screens/ReportChatScreen';
import ReportDoneScreen from '../screens/ReportDoneScreen';

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function RootNavigator() {
  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.role);
  const isCitizen = token != null && role !== 'operator';

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
      screenOptions={{ headerShown: false }}
      initialRouteName={gate.caseId ? 'AlertDetail' : undefined}
    >
      {token == null ? (
        <Stack.Screen name="Auth" component={AuthScreen} />
      ) : role === 'operator' ? (
        <Stack.Screen name="Operator" component={OperatorStack} />
      ) : (
        <Stack.Group>
          <Stack.Screen name="CitizenTabs" component={CitizenTabs} />
          <Stack.Screen
            name="AlertDetail"
            component={AlertDetailScreen}
            initialParams={gate.caseId ? { caseId: gate.caseId } : undefined}
          />
          <Stack.Screen name="AlertSync" component={AlertSyncScreen} />
          <Stack.Screen name="ReportChat" component={ReportChatScreen} />
          <Stack.Screen name="ReportDone" component={ReportDoneScreen} />
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
