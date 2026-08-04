/**
 * 실시간 산책 (와이어프레임 A-2).
 *
 * 이 화면이 앱의 평상시 얼굴이다. 실종 사건은 드물게 일어나므로, 사건이 없는
 * 날에 앱을 열 이유가 없으면 정작 알림이 필요한 날에는 앱이 지워져 있다.
 *
 * **거리는 앱이 잰다.** 서버가 경로 좌표로 재계산하지 않는 것은 의도된 설계다 —
 * 재계산하려면 경로를 보내 저장해야 하고, 그 순간 시민의 상시 위치 이력이 된다
 * (backend/app/schemas/walk.py 의 개인정보 경계).
 *
 * 지금은 위치 권한을 쓰지 않고 시간에 비례한 추정 거리를 쓴다. expo-location 을
 * 붙일 자리는 `useWalkTicker` 한 곳이며, 붙여도 서버 계약은 바뀌지 않는다.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/types';
import { color, radius, space, type } from '../theme/tokens';
import CTAButton from '../components/CTAButton';
import { useActiveWalk, useEndWalk } from '../hooks/queries';

/** 고령자 포함 평균 보행 속도 4.0km/h — 백엔드 게이지의 48m/분과 같은 계열 값. */
const KMH = 4.0;

/** 경과 시간(초)과 추정 거리(km)를 1초마다 갱신한다. */
function useWalkTicker(startedAt: string | undefined) {
  const [now, setNow] = useState(() => Date.now());
  const base = useRef<number | null>(null);

  useEffect(() => {
    if (!startedAt) return;
    base.current = new Date(startedAt).getTime();
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  if (!startedAt || base.current == null) return { elapsedSec: 0, distanceKm: 0 };
  const elapsedSec = Math.max(0, Math.floor((now - base.current) / 1000));
  return { elapsedSec, distanceKm: (elapsedSec / 3600) * KMH };
}

function clock(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export default function WalkActiveScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data: session, isLoading } = useActiveWalk();
  const endWalk = useEndWalk();
  const { elapsedSec, distanceKm } = useWalkTicker(session?.started_at);

  const onEnd = () => {
    if (!session) return;
    const durationMin = Math.max(0, elapsedSec / 60);
    endWalk.mutate(
      { sessionId: session.id, distanceKm: Number(distanceKm.toFixed(2)), durationMin },
      {
        onSuccess: (s) =>
          navigation.replace('WalkSummary', {
            sessionId: s.id,
            distanceKm: s.distance_km,
            durationMin: s.duration_min,
          }),
        // 종료 실패를 삼키면 기록이 사라진 것처럼 보인다 — 이유를 그대로 보여준다.
        onError: (e) => Alert.alert('산책을 종료하지 못했습니다', String(e)),
      },
    );
  };

  if (isLoading) {
    return (
      <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
        <View style={styles.center}>
          <Text style={styles.muted}>불러오는 중…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!session) {
    return (
      <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
        <View style={styles.center}>
          <Text style={styles.title}>진행 중인 산책이 없어요</Text>
          <Text style={styles.muted}>홈에서 산책을 시작해 주세요.</Text>
          <View style={styles.gap} />
          <CTAButton label="홈으로" onPress={() => navigation.goBack()} variant="ghost" />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <StatusBar style="dark" />

      {/* 지도 자리 — react-native-maps 는 시민 위치 권한이 붙은 뒤 연결한다.
          권한 없이 지도만 띄우면 "내 위치"가 비어 오히려 오작동처럼 보인다. */}
      <View style={styles.mapArea}>
        <View style={styles.banner} accessible accessibilityLabel="최근 3개월 간 이웃들의 동행으로 마포구에서 4명의 실종자를 찾았습니다">
          <Text style={styles.bannerText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            최근 3개월, 이웃들의 동행으로 마포구에서 <Text style={styles.bannerStrong}>4명</Text>의 실종자를 찾았습니다
          </Text>
        </View>
        <View style={styles.mapPlaceholder}>
          <Text style={styles.mapPlaceholderText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            지도는 위치 권한 연결 후 표시됩니다
          </Text>
        </View>
      </View>

      {/* 하단 컨트롤 */}
      <View style={styles.sheet}>
        <View style={styles.row}>
          <View style={styles.metric} accessible accessibilityLabel={`진행 시간 ${Math.floor(elapsedSec / 60)}분`}>
            <Text style={styles.metricLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              진행 시간
            </Text>
            <Text style={styles.metricValue} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {clock(elapsedSec)}
            </Text>
          </View>
          <View style={[styles.metric, styles.metricRight]} accessible accessibilityLabel={`거리 ${distanceKm.toFixed(1)}킬로미터`}>
            <Text style={styles.metricLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              거리
            </Text>
            <Text style={[styles.metricValue, styles.metricAccent]} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
              {distanceKm.toFixed(1)}
              <Text style={styles.metricUnit}> km</Text>
            </Text>
          </View>
        </View>

        <Text style={styles.estimate} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          거리는 걸은 시간으로 추정한 값입니다 (위치 권한 연결 전)
        </Text>

        <Pressable
          onPress={onEnd}
          disabled={endWalk.isPending}
          accessibilityRole="button"
          accessibilityLabel="산책 종료하기"
          style={({ pressed }) => [styles.endBtn, pressed && styles.pressed, endWalk.isPending && styles.disabled]}
        >
          <Text style={styles.endLabel} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
            {endWalk.isPending ? '저장 중…' : '산책 종료하기'}
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.walkWash },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl, gap: space.sm },
  gap: { height: space.lg },
  title: { fontSize: type.size.title, fontWeight: type.weight.black, color: color.text, fontFamily: type.family },
  muted: { fontSize: type.size.body, color: color.textBody, fontFamily: type.family, textAlign: 'center' },

  mapArea: { flex: 1, padding: space.lg, gap: space.md },
  banner: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: space.lg,
  },
  bannerText: { fontSize: type.size.caption, color: color.walkInk, fontFamily: type.family, lineHeight: 20, fontWeight: type.weight.medium },
  bannerStrong: { fontWeight: type.weight.black },
  mapPlaceholder: {
    flex: 1,
    borderRadius: radius.lg,
    borderWidth: 2,
    borderStyle: 'dashed',
    borderColor: color.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  mapPlaceholderText: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family },

  sheet: {
    backgroundColor: color.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: space.xl,
    gap: space.md,
    borderTopWidth: 1,
    borderTopColor: color.border,
  },
  row: { flexDirection: 'row', justifyContent: 'space-between' },
  metric: { gap: space.xs },
  metricRight: { alignItems: 'flex-end' },
  metricLabel: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family, fontWeight: type.weight.bold },
  metricValue: {
    fontSize: type.size.bigNum,
    fontWeight: type.weight.black,
    color: color.text,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
  },
  metricAccent: { color: color.walkInk },
  metricUnit: { fontSize: type.size.label, fontWeight: type.weight.bold },
  estimate: { fontSize: type.size.caption, color: color.textCaption, fontFamily: type.family, textAlign: 'center' },

  endBtn: {
    minHeight: 56,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    borderColor: color.critical,
    alignItems: 'center',
    justifyContent: 'center',
  },
  endLabel: { fontSize: type.size.cardTitle, fontWeight: type.weight.black, color: color.critical, fontFamily: type.family },
  pressed: { opacity: 0.85 },
  disabled: { opacity: 0.5 },
});
