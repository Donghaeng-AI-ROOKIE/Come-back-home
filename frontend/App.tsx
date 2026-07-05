/**
 * 돌아오길 — 앱 엔트리. Provider 스택 + NavigationContainer.
 * GestureHandler → SafeArea → Query → Navigation.
 */
import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NavigationContainer } from '@react-navigation/native';
import type { LinkingOptions } from '@react-navigation/native';
import RootNavigator from './src/navigation/RootNavigator';
import type { RootStackParamList } from './src/navigation/types';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false } },
});

// 딥링크: dora://alert/:caseId → 경보 상세 직접 진입 (spec §2.2)
const linking: LinkingOptions<RootStackParamList> = {
  prefixes: ['dora://'],
  config: {
    screens: {
      LockScreenAlert: 'lock/:caseId',
      AlertDetail: 'alert/:caseId',
      AlertSync: 'sync/:caseId',
    },
  },
};

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <NavigationContainer linking={linking}>
            <StatusBar style="auto" />
            <RootNavigator />
          </NavigationContainer>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
