/**
 * 운영자(경찰·관제) 스택 — 다크. 시민 트리에서 라우트로 도달 불가, 별도 마운트 (spec §2.3).
 * Command(메인) → CaseFound(발견 종료, fullScreenModal) / ValidationReport(검증, card).
 */
import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { OperatorStackParamList } from './types';
import { operatorTheme } from '../theme/theme';
import CommandDashboardScreen from '../screens/CommandDashboardScreen';
import CaseFoundScreen from '../screens/CaseFoundScreen';
import ValidationReportScreen from '../screens/ValidationReportScreen';

const Stack = createNativeStackNavigator<OperatorStackParamList>();

export default function OperatorStack() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: operatorTheme.bg },
      }}
    >
      <Stack.Screen name="Command" component={CommandDashboardScreen} />
      <Stack.Screen name="CaseFound" component={CaseFoundScreen} options={{ presentation: 'fullScreenModal' }} />
      <Stack.Screen name="ValidationReport" component={ValidationReportScreen} options={{ presentation: 'card' }} />
    </Stack.Navigator>
  );
}
