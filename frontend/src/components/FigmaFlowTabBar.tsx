import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, type } from '../theme/tokens';
import { FLOW_TAB_PADDING_TOP, useTabBarMetrics } from '../theme/tabBar';
import { useKeyboardVisible } from '../hooks/useKeyboardVisible';
import { useGuardianCases } from '../hooks/queries';
import { activeCases } from '../utils/guardianSearchCard';
import { citizenTabAccent, guardianEmergency, guardianTabAccent, type FlowTabKey } from '../utils/tabAccent';
import FigmaTabIcon, { type FigmaTabIconName } from './FigmaTabIcon';

type TabKey = FlowTabKey;

/**
 * 탭 내비게이터 밖 화면(스택)의 하단 탭바.
 *
 * 긴급 모드면 강조가 빨강이다(utils/tabAccent). 보호자는 진행 중 사건이 있거나
 * `emergency`(실종 신고 흐름)일 때, 시민은 긴급 알림 탭일 때다.
 *
 * `active` 가 null 이면 어느 탭도 강조하지 않는다 — 어느 탭에도 속하지 않는 화면용이다.
 * 탭은 그대로 눌러 이동할 수 있다.
 */
export default function FigmaFlowTabBar({ mode, active, emergency = false }: {
  mode: 'guardian' | 'citizen';
  active: TabKey | null;
  /** 이 화면이 실종 신고 흐름이다(보호자) — 진행 중 사건이 목록에 아직 없어도 빨강. */
  emergency?: boolean;
}) {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  // 탭 내비게이터가 아니라 일반 View 라 안전영역을 아무도 안 넣어 준다 —
  // 탭바 세 개가 같은 규칙을 쓰도록 같은 훅에서 받는다 (theme/tabBar.ts).
  const tabBar = useTabBarMetrics();
  // 키보드가 떠 있으면 그리지 않는다 — 앱이 보이는 높이에 맞춰 줄어들면서
  // 탭바가 키보드 바로 위로 따라 올라오기 때문이다(hooks/useKeyboardVisible).
  const keyboardOpen = useKeyboardVisible();
  const guardian = mode === 'guardian';
  // 진행 중 사건 목록은 보호자 탭(GuardianTabs)이 주기 조회하는 것을 따라 읽기만 한다 —
  // 요청이 늘지 않는다. 시민 화면에서는 묻지 않는다(hooks/queries 의 useGuardianCases).
  const { data: cases } = useGuardianCases(guardian ? 'follow' : 'off');
  if (keyboardOpen) return null;
  const accent = color[guardian
    ? guardianTabAccent(guardianEmergency(emergency, activeCases(cases ?? []).length))
    : citizenTabAccent(active)];
  const items: { key: TabKey; label: string; icon: FigmaTabIconName }[] = guardian
    ? [
        { key: 'home', label: '홈', icon: 'home' },
        { key: 'register', label: '사전등록', icon: 'register' },
        { key: 'alert', label: '알림', icon: 'alert' },
        { key: 'profile', label: '내 정보', icon: 'profile' },
      ]
    : [
        { key: 'home', label: '안심 홈', icon: 'home' },
        { key: 'register', label: '산책하기', icon: 'walk' },
        { key: 'alert', label: '긴급 알림', icon: 'alert' },
        { key: 'profile', label: '내 정보', icon: 'profile' },
      ];
  const goTo = (key: TabKey) => {
    if (guardian) {
      const screen = key === 'home' ? 'GuardianHome' : key === 'register' ? 'GuardianReg' : key === 'alert' ? 'GuardianAlerts' : 'GuardianMy';
      navigation.navigate('GuardianTabs', { screen });
      return;
    }
    const screen = key === 'home' ? 'Home' : key === 'register' ? 'Walk' : key === 'alert' ? 'Alerts' : 'Records';
    navigation.navigate('CitizenTabs', { screen });
  };
  return (
    <View style={[styles.bar, { height: tabBar.height, paddingBottom: tabBar.paddingBottom }]}>
      {items.map((item) => (
        <Pressable
          key={item.key}
          style={styles.item}
          onPress={() => goTo(item.key)}
        >
          <FigmaTabIcon name={item.icon} focused={active === item.key} activeColor={accent} />
          <Text style={[styles.label, active === item.key && { color: accent }]}>{item.label}</Text>
        </Pressable>
      ))}
      {tabBar.showFakeIndicator ? <View pointerEvents="none" style={styles.homeIndicator} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  // height·paddingBottom 은 useTabBarMetrics 가 기기별로 넣는다.
  // paddingTop 은 12 — 내비게이터 탭바의 `7 + 아이템 padding 5` 와 맞춘다.
  bar: { backgroundColor: '#FFFFFF', borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#D8D8D8', flexDirection: 'row', paddingTop: FLOW_TAB_PADDING_TOP },
  // 보호자 탭바에만 위 모서리 42 라운드를 주고 있었다. 둥근 만큼 뒤 화면의 회색
  // 배경이 양끝에 비쳐 바가 떠 있는 것처럼 보였다(현장 제보 08-13).
  // 시민·보호자 모두 화면 끝까지 꽉 찬 사각형으로 통일한다.
  item: { flex: 1, alignItems: 'center', outlineStyle: 'none' } as any,
  label: { fontFamily: type.familyCssBold, fontSize: 10, lineHeight: 13, letterSpacing: 0.16, color: color.figmaGray, marginTop: 1 },
  homeIndicator: { position: 'absolute', bottom: 8, left: '32%', right: '32%', height: 5, borderRadius: 100, backgroundColor: '#000000' },
});
