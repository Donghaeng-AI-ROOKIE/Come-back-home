/**
 * 돌아오길 — 앱 엔트리. Provider 스택 + NavigationContainer.
 * GestureHandler → SafeArea → Query → Navigation.
 */
import React from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NavigationContainer } from '@react-navigation/native';
import type { LinkingOptions } from '@react-navigation/native';
import RootNavigator from './src/navigation/RootNavigator';
import type { RootStackParamList } from './src/navigation/types';
import {
  font42dotSans_400Regular,
  font42dotSans_500Medium,
  font42dotSans_600SemiBold,
  font42dotSans_700Bold,
  font42dotSans_800ExtraBold,
  useFonts,
} from '@expo-google-fonts/42dot-sans';

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
  const [fontsLoaded] = useFonts({
    '42dotSans-Regular': font42dotSans_400Regular,
    '42dotSans-Medium': font42dotSans_500Medium,
    '42dotSans-SemiBold': font42dotSans_600SemiBold,
    '42dotSans-Bold': font42dotSans_700Bold,
    '42dotSans-ExtraBold': font42dotSans_800ExtraBold,
  });

  if (!fontsLoaded) return null;

  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <View style={Platform.OS === 'web' ? styles.webPhone : styles.nativeApp}>
            <NavigationContainer linking={linking}>
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
