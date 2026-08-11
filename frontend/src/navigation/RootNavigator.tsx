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
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { RootStackParamList } from './types';
import { navigationRef } from './navigationRef';
import { useAuthStore } from '../store/authStore';
import { useAlertGate } from '../hooks/useAlertGate';
import { usePushRegistration } from '../hooks/usePushRegistration';
import { useNotificationRouting } from '../hooks/useNotificationRouting';
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

/**
 * 관문이 가로채도 되는 화면 — 시민 4탭. `getCurrentRoute()` 는 **잎 화면**을
 * 돌려주므로 'CitizenTabs' 가 아니라 탭 이름들과 비교해야 한다.
 * 여기 없는 화면(제보 작성·산책 중 등)은 진행 중인 일이 있다고 본다.
 */
const IDLE_ROUTES = new Set<string>(['Home', 'Walk', 'Alerts', 'Records']);

export default function RootNavigator() {
  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.role);
  // 저장된 토큰이 아직 유효한지 서버에 한 번 묻는다 — 서버가 모르는 토큰으로
  // 로그인 상태를 흉내 내면 남의 기록을 보여주게 된다.
  const restoring = useAuthStore((s) => s.restoring);
  const restore = useAuthStore((s) => s.restore);
  useEffect(() => {
    void restore();
  }, [restore]);
  // 경보 관문은 시민 트리에서만 선다. 운영자 역할은 이 브랜치에서 제거됐으므로
  // (관제 = 백엔드 /dashboard) 'citizen' 인지 직접 확인한다.
  const isCitizen = token != null && role === 'citizen';

  // 푸시 배선 — 훅은 만들어져 있었지만 어디에도 마운트되지 않아 토큰 등록이
  // 한 번도 일어나지 않았다. 등록은 시민 역할에서만(수색 알림의 수신자),
  // 탭 라우팅은 역할 무관하게 건다. 둘 다 푸시 미지원 환경(웹·Expo Go·
  // projectId 미설정)에서는 조용히 물러난다.
  usePushRegistration(isCitizen);
  useNotificationRouting();

  const gate = useAlertGate(isCitizen);

  // 관문 판정은 이제 **앱을 쓰는 도중에도 바뀐다**(useActiveAlerts 가 15초마다
  // 다시 묻는다). 그런데 아래 key 가 바뀌면 스택이 통째로 리마운트되므로, 제보를
  // 쓰던 중에 새 경보가 접수되면 입력하던 내용이 그대로 날아간다.
  //
  // 그래서 **탭 루트에 있을 때만** 새 관문을 세운다 — 홈에서 쉬고 있는 사람은
  // 가로채도 되지만(그게 관문의 목적이다), 무언가 하고 있는 사람은 건드리지 않는다.
  // 관문이 사라지는 방향(null)은 언제나 반영한다: 잃을 입력이 없고, 종결된 사건을
  // 계속 붙잡아 두면 안 된다.
  const [gateCase, setGateCase] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    if (gate.pending || gate.caseId === gateCase) return;
    const current = navigationRef.isReady() ? navigationRef.getCurrentRoute()?.name : undefined;
    if (gate.caseId == null || current == null || IDLE_ROUTES.has(current)) {
      setGateCase(gate.caseId);
    }
  }, [gate.pending, gate.caseId, gateCase]);
  // 첫 판정은 래치를 거치지 않고 바로 쓴다 — 한 박자 늦으면 홈이 잠깐 비쳤다가
  // 관문이 덮는 깜빡임이 생긴다.
  const gateCaseId = gateCase === undefined ? gate.caseId : gateCase;

  // 경보 조회가 끝날 때까지 네비게이터를 마운트하지 않는다. initialRouteName 은
  // 마운트 시점에 한 번만 읽히므로, 로딩 중에 먼저 띄우면 "경보 없음"으로 굳어
  // 관문이 영영 안 선다. 인증 화면 부트스트랩과 같은 패턴.
  if (restoring || gate.pending) {
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
      key={`${token == null ? 'auth' : (role ?? 'none')}:${gateCaseId ?? 'nogate'}`}
      screenOptions={{ headerShown: false }}
      initialRouteName={gateCaseId ? 'AlertDetail' : undefined}
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
            initialParams={gateCaseId ? { caseId: gateCaseId } : undefined}
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
