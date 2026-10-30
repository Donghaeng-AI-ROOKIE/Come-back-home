/** 보호자 하단 4탭 (Figma): 홈 / 사전등록 / 알림 / 내 정보. */
import React, { useState } from 'react';
import { Alert, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useQueryClient } from '@tanstack/react-query';
import { SafeAreaView } from 'react-native-safe-area-context';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { PlatformPressable } from '@react-navigation/elements';
import type { GuardianTabParamList, RootStackParamList } from './types';
import { captureDemoTemplate, prepareNextDemoTurn } from '../api/guardian';
import { ApiError } from '../api/config';
import { color, radius, space, type } from '../theme/tokens';
import { useTabBarMetrics } from '../theme/tabBar';
import { useKeyboardVisible } from '../hooks/useKeyboardVisible';
import CTAButton from '../components/CTAButton';
import GuardianHomeScreen from '../screens/GuardianHomeScreen';
import RegChatScreen from '../screens/RegChatScreen';
import { useAuthStore } from '../store/authStore';
import { useGuardianStore } from '../store/guardianStore';
import GuardianAlertsScreen from '../screens/GuardianAlertsScreen';
import FigmaTabIcon from '../components/FigmaTabIcon';
import { useDemoBooth, useGuardianCases, usePersonas } from '../hooks/queries';
import { useGuardianCaseStore } from '../store/guardianCaseStore';
import { listedCases } from '../utils/guardianTips';
import { activeCases } from '../utils/guardianSearchCard';
import { guardianEmergency, guardianTabAccent } from '../utils/tabAccent';
import { notify } from '../utils/notify';

const Tab = createBottomTabNavigator<GuardianTabParamList>();

/** 확인 창 — 웹(부스 폰은 Pages 웹앱)은 Alert 버튼이 안 떠서 window.confirm 을 쓴다. */
function confirmAsync(title: string, message: string): Promise<boolean> {
  if (Platform.OS === 'web') return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  return new Promise((resolve) => Alert.alert(title, message, [
    { text: '취소', style: 'cancel', onPress: () => resolve(false) },
    { text: '확인', style: 'destructive', onPress: () => resolve(true) },
  ], { cancelable: true, onDismiss: () => resolve(false) }));
}

/** 내 정보 — 로그아웃과 등록 현황. 부스 계정에는 진행자 영역(템플릿 저장·다음 체험 준비)이 더 보인다. */
function GuardianMyScreen() {
  const { user, userId, signOut, switchRole } = useAuthStore();
  const [switching, setSwitching] = useState(false);
  const cachedPersona = useGuardianStore((s) => s.persona);
  const reset = useGuardianStore((s) => s.reset);
  const { data: personas, isLoading } = usePersonas();
  // ── 부스 진행자(결선) — 서버가 부스 계정에만 템플릿 상태를 준다(그 외 403 → 영역 숨김) ──
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const qc = useQueryClient();
  const booth = useDemoBooth();
  const [busy, setBusy] = useState<null | 'capture' | 'next'>(null);
  const [boothMessage, setBoothMessage] = useState<string | null>(null);
  const showBoothMessage = (title: string, message: string) => {
    setBoothMessage(`${title}\n${message}`);
    notify(title, message);
  };
  const boothLine = booth.data
    ? booth.data.exists
      ? `템플릿: ${booth.data.name ?? '-'} (${String(booth.data.age ?? '-').replace(/세$/, '')}세) · 대화 ${booth.data.n_messages ?? 0}줄${booth.data.label ? ` · ${booth.data.label}` : ''}`
      : '템플릿 없음 — 사전 등록을 "이렇게 등록할게요" 요약까지 진행한 뒤 저장하세요'
    : '';
  const captureTemplate = async () => {
    if (busy) return;
    if (!(await confirmAsync('템플릿으로 저장', '지금 요약 확인 중인 대화를 다음 체험자들의 시작 상태로 저장합니다. 기존 템플릿은 덮어씁니다.'))) return;
    setBusy('capture');
    setBoothMessage(null);
    try {
      const meta = await captureDemoTemplate('부스', userId ?? undefined);
      await booth.refetch();
      showBoothMessage('저장했습니다', `${meta.name ?? '-'} (${String(meta.age ?? '-').replace(/세$/, '')}세) · 대화 ${meta.n_messages ?? 0}줄`);
    } catch (e) {
      showBoothMessage('저장하지 못했습니다', e instanceof ApiError ? e.message : String(e));
    } finally { setBusy(null); }
  };
  const nextTurn = async () => {
    if (busy) return;
    setBusy('next');
    setBoothMessage(null);
    try {
      // 다른 진행자가 저장했을 수도 있으므로, 삭제 확인 전에 최신 준비 상태를 읽는다.
      const current = await booth.refetch({ throwOnError: true });
      if (!current.data?.exists) {
        showBoothMessage('먼저 시작 대화를 저장해 주세요', '사전 등록에서 "이렇게 등록할게요" 요약이 나오면, "맞아요"를 누르기 전에 내 정보에서 "지금 대화를 템플릿으로 저장"을 눌러 주세요. 저장 후 다음 체험을 준비할 수 있습니다. 기존 가족과 신고는 그대로 유지했습니다.');
        return;
      }
      if (!(await confirmAsync('다음 체험 준비', '이 계정의 신고는 철회 종결되고 등록된 가족은 지워집니다. 템플릿을 복제해 "맞아요" 직전 화면으로 엽니다.'))) return;
      const r = await prepareNextDemoTurn('보호자', userId ?? undefined);
      // 이전 체험의 캐시(등록 가족·사건)를 비운다 — 안 비우면 홈에 지운 가족이 남아 보인다.
      reset();
      qc.removeQueries({ queryKey: ['personas'] });
      qc.removeQueries({ queryKey: ['personaStatus'] });
      qc.removeQueries({ queryKey: ['guardianCases'] });
      navigation.navigate('RegChat', { sessionId: r.session.id });
    } catch (e) {
      showBoothMessage('준비하지 못했습니다', e instanceof ApiError ? e.message : String(e));
    } finally { setBusy(null); }
  };
  const registered = personas?.length
    ? personas.map((persona) => `${persona.name} (${persona.age}세)`).join(', ')
    : cachedPersona ? `${cachedPersona.name} (${cachedPersona.age}세)` : '없음';

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.wrap}>
        <Text style={styles.title} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          내 정보
        </Text>
        <View style={styles.card}>
          <Text style={styles.rowKey} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            보호자
          </Text>
          <Text style={styles.rowVal} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {user ?? '-'}
          </Text>
          <View style={styles.divider} />
          <Text style={styles.rowKey} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            등록된 가족
          </Text>
          <Text style={styles.rowVal} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {isLoading && !cachedPersona ? '불러오는 중…' : registered}
          </Text>
        </View>
        {booth.data ? (
          <View style={styles.card}>
            <Text style={styles.rowKey} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              부스 진행자
            </Text>
            <Text style={styles.rowVal} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {boothLine}
            </Text>
            {boothMessage ? (
              <Text accessibilityRole="alert" style={styles.rowKey} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
                {boothMessage}
              </Text>
            ) : null}
            <View style={styles.divider} />
            <CTAButton label={busy === 'capture' ? '저장 중…' : '지금 대화를 템플릿으로 저장'} onPress={captureTemplate} disabled={busy !== null} variant="ghost" />
            <View style={styles.switchGap} />
            <CTAButton label={busy === 'next' ? '준비 중…' : '다음 체험 준비'} onPress={nextTurn} disabled={busy !== null} />
          </View>
        ) : null}
        <View style={styles.spacer} />
        {/* 역할을 바꿔야 하는 경우가 실제로 있다 — 가입할 때 잘못 고르면 보호자
            계정으로는 산책·제보 화면에 갈 수 없고, 계정을 새로 만드는 수밖에
            없었다(현장 실측 08-11). 기록은 계정에 붙어 있어 그대로 남는다. */}
        <CTAButton
          label={switching ? '전환 중…' : '시민 모드로 전환'}
          onPress={async () => {
            if (switching) return;
            setSwitching(true);
            try {
              await switchRole('citizen');
            } catch (e) {
              Alert.alert('전환하지 못했습니다', String(e));
            } finally {
              setSwitching(false);
            }
          }}
          variant="ghost"
        />
        <View style={styles.switchGap} />
        <CTAButton
          label="로그아웃"
          onPress={() => {
            reset();   // 역할을 바꿔 다시 로그인할 때 이전 보호자 등록이 남지 않게 한다
            signOut();
          }}
          variant="ghost"
        />
      </ScrollView>
    </SafeAreaView>
  );
}

export default function GuardianTabs() {
  // 시민 탭과 같은 이유로 안전영역을 더해서 높이를 정한다 (theme/tabBar.ts).
  const tabBar = useTabBarMetrics();
  // 키보드가 떠 있으면 탭바를 감춘다 — 앱이 보이는 높이로 줄어들면서 탭바가
  // 키보드 바로 위로 올라와 대화 영역을 잡아먹는다(hooks/useKeyboardVisible).
  const keyboardOpen = useKeyboardVisible();
  /**
   * 알림 탭에 보인 제보를 "본 제보"로 적는다 — 홈 "수색 중" 카드의 새 제보 수가
   * 이 기록을 뺀 나머지다(utils/guardianSearchCard).
   *
   * 탭에 들어올 때와 나갈 때 적는다. 나갈 때 적는 이유: 탭을 열어 둔 사이에 들어온
   * 제보도 목록에 곧바로 그려졌으므로 본 것이다. 적는 대상은 탭 목록과 같은 사건
   * 하나뿐이다(listedCases) — 목록에 없는 사건의 제보까지 읽음 처리하면 안 된다.
   * 사건 목록은 알림 탭과 **같은 쿼리 키**라 요청이 늘지 않는다.
   */
  const { data: cases } = useGuardianCases();
  const markTipsSeen = useGuardianCaseStore((s) => s.markTipsSeen);
  const markShownTipsSeen = () => {
    for (const c of listedCases(cases ?? [])) markTipsSeen(c.id, (c.tips ?? []).map((t) => t.id));
  };
  // 진행 중 사건이 있으면 네 탭 모두 빨강으로 강조한다 — 홈 "수색 중" 카드와 같은 판정이고
  // 위와 같은 사건 목록이다. 모두 종결·철회되면 초록으로 돌아온다(utils/tabAccent).
  const accent = color[guardianTabAccent(guardianEmergency(false, activeCases(cases ?? []).length))];
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: accent,
        tabBarInactiveTintColor: color.figmaGray,
        tabBarLabelStyle: { fontSize: 10, lineHeight: 13, letterSpacing: 0.16, fontFamily: type.familyRobotoSemiBold, marginTop: 1 },
        tabBarStyle: {
          backgroundColor: color.surface,
          borderTopColor: color.border,
          height: tabBar.height,
          paddingTop: 7,
          paddingBottom: tabBar.paddingBottom,
          display: keyboardOpen ? 'none' : 'flex',
        },
        tabBarItemStyle: styles.tabItem,
        tabBarButton: (props) => <PlatformPressable {...props} style={[props.style, styles.tabButton]} />,
        tabBarBackground: () => (
          <View style={styles.tabBackground}>
            {tabBar.showFakeIndicator ? <View style={styles.homeIndicator} /> : null}
          </View>
        ),
      }}
    >
      <Tab.Screen
        name="GuardianHome"
        component={GuardianHomeScreen}
        options={{ tabBarLabel: '홈', tabBarIcon: ({ focused }) => <FigmaTabIcon name="home" focused={focused} activeColor={accent} /> }}
      />
      <Tab.Screen
        name="GuardianReg"
        component={RegChatScreen}
        options={{ tabBarLabel: '사전등록', tabBarIcon: ({ focused }) => <FigmaTabIcon name="register" focused={focused} activeColor={accent} /> }}
      />
      <Tab.Screen
        name="GuardianAlerts"
        component={GuardianAlertsScreen}
        listeners={{ focus: markShownTipsSeen, blur: markShownTipsSeen }}
        options={{ tabBarLabel: '알림', tabBarIcon: ({ focused }) => <FigmaTabIcon name="alert" focused={focused} activeColor={accent} /> }}
      />
      <Tab.Screen
        name="GuardianMy"
        component={GuardianMyScreen}
        options={{ tabBarLabel: '내 정보', tabBarIcon: ({ focused }) => <FigmaTabIcon name="profile" focused={focused} activeColor={accent} /> }}
      />
    </Tab.Navigator>
  );
}

const styles = StyleSheet.create({
  /**
   * 화면 끝까지 꽉 찬 사각형 — 시민 탭바(CitizenTabs)와 같다.
   *
   * 위 모서리에 42 라운드가 걸려 있었다. 그러면 둥근 만큼 **뒤 화면의 회색
   * 배경이 탭바 양끝에 비친다** — 실기기에서 바가 떠 있는 것처럼 보였다
   * (현장 제보 08-13). 시민 모드와 나란히 놓으면 차이가 분명하다.
   */
  tabBackground: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, backgroundColor: '#FFFFFF' },
  tabItem: { outlineStyle: 'none' } as any,
  tabButton: { flex: 1, outlineStyle: 'none' } as any,
  homeIndicator: { position: 'absolute', bottom: 8, left: '32%', right: '32%', height: 5, borderRadius: 100, backgroundColor: '#000000' },
  safe: { flex: 1, backgroundColor: color.surfaceAlt },
  wrap: { flexGrow: 1, padding: space.xl, gap: space.lg },
  title: { fontSize: type.size.title, color: color.text, fontFamily: type.familyExtraBold },
  card: { backgroundColor: color.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: color.border, padding: space.lg, gap: space.xs },
  rowKey: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.familyBold },
  rowVal: { fontSize: type.size.label, color: color.text, fontFamily: type.familySemiBold },
  divider: { height: 1, backgroundColor: color.border, marginVertical: space.md },
  switchGap: { height: 10 },
  spacer: { flex: 1 },
});
