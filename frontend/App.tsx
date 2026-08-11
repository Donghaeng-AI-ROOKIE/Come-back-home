/**
 * 돌아오길 — 앱 엔트리. Provider 스택 + NavigationContainer.
 * GestureHandler → SafeArea → Query → Navigation.
 */
import React, { useEffect, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { useFonts } from 'expo-font';
import { ActivityIndicator, Platform, StyleSheet, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NavigationContainer } from '@react-navigation/native';
import type { LinkingOptions } from '@react-navigation/native';
import RootNavigator from './src/navigation/RootNavigator';
import { navigationRef } from './src/navigation/navigationRef';
import type { RootStackParamList } from './src/navigation/types';
import { setupPwa } from './src/pwa';

// 홈 화면 설치·서비스 워커 등록. 웹이 아니면 아무 일도 하지 않는다.
// 모듈 수준에서 한 번만 — 리렌더마다 head 에 태그가 쌓이면 안 된다.
setupPwa();

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
    '42dotSans-Regular': require('./assets/fonts/42dotSans-Regular.ttf'),
    '42dotSans-Medium': require('./assets/fonts/42dotSans-Medium.ttf'),
    '42dotSans-SemiBold': require('./assets/fonts/42dotSans-SemiBold.ttf'),
    '42dotSans-Bold': require('./assets/fonts/42dotSans-Bold.ttf'),
    '42dotSans-ExtraBold': require('./assets/fonts/42dotSans-Bold.ttf'),
  });
  /**
   * 폰트 대기 상한 — 이보다 오래 흰 화면을 붙잡지 않는다.
   *
   * 폰트 4종이 **10.4MB**다(42dotSans TTF, 각 2.6MB). 위 useFonts 는 이게 다
   * 내려올 때까지 앱을 통째로 막는데, 그 대기에는 원래 시간 제한이 없었다.
   * 그래서 회선이 느리면 **영영 흰 화면**이었다 — PC 는 되는데 폰만 안 되는
   * 현상의 정체(현장 제보 08-11, 실측: 첫 렌더 필요량 13MB).
   *
   * 시간이 지나면 시스템 폰트로 먼저 그린다. 글자 크기·줄간격은 화면마다 px 로
   * 박혀 있어 배치는 그대로고, 받다 만 폰트는 뒤에서 계속 내려와 준비되는 대로
   * 브라우저가 알아서 바꿔 끼운다(FontFace). 즉 손해는 잠깐의 서체뿐이다.
   */
  const [fontWaitOver, setFontWaitOver] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setFontWaitOver(true), 2_500);
    return () => clearTimeout(id);
  }, []);

  if (!fontsLoaded && !fontError && !fontWaitOver) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#FFFFFF' }}>
        <ActivityIndicator color="#67AE6E" />
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <View style={Platform.OS === 'web' ? styles.webPhone : styles.nativeApp}>
            <NavigationContainer ref={navigationRef} linking={linking}>
              <StatusBar style="auto" />
              <RootNavigator />
            </NavigationContainer>
          </View>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Platform.OS === 'web' ? '#F2F2F2' : '#FFFFFF' },
  nativeApp: { flex: 1 },
  webPhone: { flex: 1, width: '100%', maxWidth: 375, alignSelf: 'center', backgroundColor: '#FFFFFF' },
});
