/**
 * 상단 상태바 — 시안의 44px 영역.
 *
 * ## 이 자리는 원래 OS 가 그리는 곳이다
 * 피그마의 44px 상태바는 iOS 가 직접 그리는 영역이다. 그래서
 *  - **네이티브**: 아무것도 그리지 않는다(OS 가 그린다).
 *  - **홈 화면 설치본(standalone)**: 마찬가지다. OS 상태바가 이미 위에 떠 있는데
 *    가짜를 하나 더 그리면 시계가 두 개 보인다.
 *  - **브라우저 탭**: 그 자리에 OS 상태바가 없으므로 44px 여백만 유지한다.
 *
 * ## 시각은 진짜를 쓴다
 * 시안값 "9:41"이 그대로 박혀 있었다(실측 08-11). 화면 안의 다른 숫자는 전부
 * 실데이터인데 시계만 멈춰 있으면 앱이 고장 난 것처럼 보인다.
 *
 * 신호·와이파이·배터리 아이콘은 **뺐다** — 앱이 알 수 없는 값이라 그리면 그림이다.
 */
import React, { useEffect, useState } from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';
import { type } from '../theme/tokens';

/** 홈 화면에 설치해 연 상태인가 — 그렇다면 OS 상태바가 이미 있다. */
function isStandalone(): boolean {
  if (typeof window === 'undefined') return false;
  const mm = window.matchMedia?.('(display-mode: standalone)')?.matches;
  const ios = (window.navigator as unknown as { standalone?: boolean }).standalone;
  return Boolean(mm || ios);
}

function nowLabel(): string {
  const d = new Date();
  const h = d.getHours();
  const m = String(d.getMinutes()).padStart(2, '0');
  // 시안과 같은 12시간 표기(9:41). 앞자리 0 은 붙이지 않는다.
  return `${h % 12 === 0 ? 12 : h % 12}:${m}`;
}

export default function FigmaStatusBar() {
  const [time, setTime] = useState(nowLabel);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    // 분이 바뀌는 순간에 맞춰 갱신하고, 이후 1분 주기로 돈다.
    const tick = () => setTime(nowLabel());
    const msToNextMinute = 60_000 - (Date.now() % 60_000);
    let interval: ReturnType<typeof setInterval> | undefined;
    const timeout = setTimeout(() => {
      tick();
      interval = setInterval(tick, 60_000);
    }, msToNextMinute);
    return () => {
      clearTimeout(timeout);
      if (interval) clearInterval(interval);
    };
  }, []);

  if (Platform.OS !== 'web') return null;
  // 설치본은 OS 상태바가 있다. 여백까지 없애야 시안의 프레임과 정확히 맞는다.
  if (isStandalone()) return null;

  return (
    <View style={styles.bar}>
      <Text style={styles.time}>{time}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { width: '100%', height: 44 },
  time: {
    position: 'absolute',
    left: 20,
    top: 12,
    width: 54,
    textAlign: 'center',
    fontFamily: type.familyRobotoSemiBold,
    fontSize: 15,
    lineHeight: 18,
    letterSpacing: -0.165,
    color: '#000000',
  },
});
