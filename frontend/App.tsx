/**
 * 돌아오길 — 앱 엔트리. Provider 스택 + NavigationContainer.
 * GestureHandler → SafeArea → Query → Navigation.
 */
import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { useFonts } from 'expo-font';
import { ActivityIndicator, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NavigationContainer } from '@react-navigation/native';
import type { LinkingOptions } from '@react-navigation/native';
import RootNavigator from './src/navigation/RootNavigator';
import { navigationRef } from './src/navigation/navigationRef';
import { usePushRegistration } from './src/hooks/usePushRegistration';
import { useNotificationRouting } from './src/hooks/useNotificationRouting';
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
  const [fontsLoaded, fontError] = useFonts({
    'Dot42-Regular': require('./assets/fonts/42dotSans-Regular.ttf'),
    'Dot42-Medium': require('./assets/fonts/42dotSans-Medium.ttf'),
    'Dot42-SemiBold': require('./assets/fonts/42dotSans-SemiBold.ttf'),
    'Dot42-Bold': require('./assets/fonts/42dotSans-Bold.ttf'),
  });
  // 푸시 등록·라우팅은 앱 전역에서 한 번만. 개발 빌드 이전에는 조용히 아무 일도
  // 하지 않는다(Expo Go 에는 푸시 기능이 없다 — usePushRegistration 주석 참고).
  usePushRegistration();
  useNotificationRouting();

  if (!fontsLoaded && !fontError) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#FFFFFF' }}>
        <ActivityIndicator color="#67AE6E" />
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <NavigationContainer ref={navigationRef} linking={linking}>
            <StatusBar style="auto" />
            <RootNavigator />
          </NavigationContainer>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
