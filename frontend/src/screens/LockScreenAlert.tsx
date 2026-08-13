import React from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { useAppModeStore } from '../store/appModeStore';
import { useEngagementStore } from '../store/engagementStore';
import { color, type } from '../theme/tokens';
import { useTabBarMetrics } from '../theme/tabBar';
import StatusIcons from '../../assets/figma/lock-status.svg';
import NotificationBackground from '../../assets/figma/lock-notification-bg.svg';
import NotificationMask from '../../assets/figma/lock-notification-mask.svg';
import NotificationHeader from '../../assets/figma/lock-notification-header.svg';
import { useActiveAlerts } from '../hooks/queries';
import { alertToView } from '../data/missingView';

const appIcon = require('../../assets/figma/lock-app-icon.png');

export default function LockScreenAlert() {
  // 잠금화면 흉내라 흰 인디케이터가 시안에 있지만, 실기기에는 OS 가 그린 것이
  // 이미 있다 — 겹치지 않게 안전영역이 0 일 때만 (theme/tabBar.ts).
  const { showFakeIndicator } = useTabBarMetrics();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'LockScreenAlert'>>();
  const caseId = route.params.caseId;
  const dismissCase = useAppModeStore((s) => s.dismissCase);
  const recordDismissed = useEngagementStore((s) => s.recordDismissed);
  const recordOpened = useEngagementStore((s) => s.recordOpened);
  const { data: alerts } = useActiveAlerts();
  const alert = alerts?.find((item) => item.caseId === caseId);
  const view = alertToView(alert ?? {});
  const appearance = view.appearance.slice(0, 3);
  const issuedAt = alert?.issuedAt ? new Date(alert.issuedAt) : null;
  const issuedTime = issuedAt && !Number.isNaN(issuedAt.getTime())
    ? issuedAt.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false })
    : '--:--';

  const openDetail = () => {
    recordOpened();
    navigation.navigate('AlertDetail', { caseId });
  };
  const dismiss = () => {
    dismissCase(caseId);
    recordDismissed();
    navigation.goBack();
  };

  return (
    <View style={styles.root} accessibilityLabel="실종자 발생 알림">
      <StatusBar style="light" />

      <Text style={styles.statusTime}>9:41</Text>
      <StatusIcons width={67} height={12} style={styles.statusIcons} />
      <Text style={styles.clock}>13:24</Text>
      <Text style={styles.date}>Monday, 30 July</Text>
      <Text style={styles.weekday}>Saturday</Text>

      <View style={styles.notification}>
        <NotificationBackground width={375} height={140} style={styles.notificationBackground} />
        <NotificationMask width={359} height={212} style={styles.notificationMask} />
        <NotificationHeader width={359} height={45} style={styles.notificationHeader} />

        <Image source={appIcon} resizeMode="contain" style={styles.appIcon} />
        <Text style={styles.appName}>돌아오길</Text>
        <Text style={styles.appTime}>{issuedTime}</Text>
        <Text style={styles.title}>실종자 발생</Text>
        <Text style={styles.subtitle}>{alert?.summary || '내 주변에 실종자가 있어요!'}</Text>
        <Text style={styles.person}>{view.title} • {view.meta}</Text>

        <View style={styles.tagRow}>{appearance.map((label) => <View key={label} style={styles.tag}><Text style={styles.tagText} numberOfLines={1}>{label}</Text></View>)}</View>

        <Text style={styles.probabilityLabel}>{alert ? `수색 대상 ${alert.targetCells.length}개 구역` : '수색 범위를 확인하는 중'}</Text>
        <View style={styles.probabilityTrack}><View style={[styles.probabilityValue, { width: alert ? '100%' : '0%' }]} /></View>

        <Pressable style={[styles.action, styles.confirm]} onPress={openDetail} accessibilityRole="button">
          <Text style={styles.confirmText}>지금 확인</Text>
        </Pressable>
        <Pressable style={[styles.action, styles.ignore]} onPress={dismiss} accessibilityRole="button">
          <Text style={styles.ignoreText}>관심 없어요</Text>
        </Pressable>
      </View>

      {showFakeIndicator ? <View style={styles.homeIndicator} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, minHeight: 812, backgroundColor: '#C7C7CC', position: 'relative', overflow: 'hidden' },
  statusTime: { position: 'absolute', left: 20, top: 12, width: 54, textAlign: 'center', color: '#FFFFFF', fontSize: 15, lineHeight: 18, fontWeight: '600' },
  statusIcons: { position: 'absolute', right: 14, top: 16 },
  clock: { position: 'absolute', top: 91, width: '100%', textAlign: 'center', color: '#FFFFFF', fontSize: 80, lineHeight: 96, fontWeight: '200', letterSpacing: -0.6 },
  date: { position: 'absolute', top: 190, width: '100%', textAlign: 'center', color: '#FFFFFF', fontSize: 22, lineHeight: 27, fontWeight: '400', letterSpacing: 0.3 },
  weekday: { position: 'absolute', left: 20, top: 259, color: '#FFFFFF', fontSize: 28, lineHeight: 34, fontWeight: '400', letterSpacing: 0.4 },
  notification: { position: 'absolute', left: 0, right: 0, top: 296, height: 216 },
  notificationBackground: { position: 'absolute', left: 0, top: 0 },
  notificationMask: { position: 'absolute', left: 8, top: 4 },
  notificationHeader: { position: 'absolute', left: 8, top: 4 },
  appIcon: { position: 'absolute', left: 18, top: 15, width: 20, height: 18 },
  appName: { position: 'absolute', left: 45, top: 18, fontFamily: type.family, fontSize: 13, lineHeight: 18, color: '#616164' },
  appTime: { position: 'absolute', right: 16, top: 18, width: 40, textAlign: 'right', fontFamily: type.family, fontSize: 13, lineHeight: 18, color: '#616164' },
  title: { position: 'absolute', left: 23, top: 49, fontFamily: type.familySemiBold, fontSize: 15, lineHeight: 20, color: '#000000' },
  subtitle: { position: 'absolute', left: 23, right: 73, top: 78, fontFamily: type.family, fontSize: 13, lineHeight: 18, color: '#000000' },
  person: { position: 'absolute', left: 23, right: 73, top: 104, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#000000' },
  tagRow: { position: 'absolute', left: 149, right: 20, top: 103, height: 16, flexDirection: 'row', gap: 5 },
  tag: { maxWidth: 72, height: 16, paddingHorizontal: 6, borderRadius: 20, backgroundColor: '#FFC9CB', alignItems: 'center', justifyContent: 'center' },
  tagText: { fontFamily: type.familyBold, fontSize: 10, lineHeight: 13, color: '#E05454' },
  probabilityLabel: { position: 'absolute', left: 23, top: 130, fontFamily: type.family, fontSize: 11, lineHeight: 13, color: '#000000' },
  probabilityTrack: { position: 'absolute', left: 24, right: 24, top: 152, height: 4, borderRadius: 12, overflow: 'hidden', backgroundColor: '#C7C7CC' },
  probabilityValue: { height: 4, backgroundColor: color.figmaRed },
  action: { position: 'absolute', top: 169, height: 35, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  confirm: { left: 24, right: 189, backgroundColor: color.figmaRed },
  ignore: { left: 190, right: 23, backgroundColor: '#DADADA' },
  confirmText: { fontSize: 15, lineHeight: 20, fontWeight: '600', color: '#FFFFFF' },
  ignoreText: { fontSize: 15, lineHeight: 20, fontWeight: '600', color: '#8E8E93' },
  homeIndicator: { position: 'absolute', bottom: 8, left: 120, width: 135, height: 5, borderRadius: 100, backgroundColor: '#FFFFFF' },
});
