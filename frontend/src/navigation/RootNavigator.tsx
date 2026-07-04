/**
 * 최상위 역할·인증 게이트 (spec §2.2). role 클레임이 마운트 트리를 결정.
 * 운영자 스택은 시민 트리에 부재 — 컴포넌트 트리 자체가 분리.
 * 소비자 플로우 모달(락스크린/경보상세/경보연동/제보/제보완료)은 CitizenTabs와 함께 루트에 등록.
 */
import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { RootStackParamList } from './types';
import { useAuthStore } from '../store/authStore';
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

  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      {token == null ? (
        <Stack.Screen name="Auth" component={AuthScreen} />
      ) : role === 'operator' ? (
        <Stack.Screen name="Operator" component={OperatorStack} />
      ) : (
        <Stack.Group>
          <Stack.Screen name="CitizenTabs" component={CitizenTabs} />
          <Stack.Screen name="AlertDetail" component={AlertDetailScreen} />
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
