/**
 * 최상위 역할 게이트 (와이어프레임 2026-08-05). role 클레임이 마운트 트리를 결정한다.
 *
 * 보호자 트리와 시민 트리는 컴포넌트 트리 자체가 분리된다 — 한쪽에서 다른 쪽
 * 화면으로 갈 수 있으면 "보호자가 시민 제보를 한다" 같은 경로가 열려 권한 경계가
 * 흐려진다. 역할을 바꾸려면 로그아웃 후 다시 고른다.
 *
 * 운영자 트리는 제거됐다 — 와이어프레임에 없고 관제는 백엔드 /dashboard 가 맡는다.
 */
import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { RootStackParamList } from './types';
import { useAuthStore } from '../store/authStore';
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
import ReportScreen from '../screens/ReportScreen';
import ReportSentScreen from '../screens/ReportSentScreen';

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function RootNavigator() {
  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.role);

  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      {token == null ? (
        <Stack.Screen name="Auth" component={AuthScreen} />
      ) : role === 'guardian' ? (
        <Stack.Group>
          <Stack.Screen name="GuardianTabs" component={GuardianTabs} />
          <Stack.Screen name="RegChat" component={RegChatScreen} />
          <Stack.Screen name="RegDone" component={RegDoneScreen} />
          <Stack.Screen name="Report" component={ReportScreen} />
          <Stack.Screen name="ReportSent" component={ReportSentScreen} />
        </Stack.Group>
      ) : (
        <Stack.Group>
          <Stack.Screen name="CitizenTabs" component={CitizenTabs} />
          <Stack.Screen name="AlertDetail" component={AlertDetailScreen} />
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
