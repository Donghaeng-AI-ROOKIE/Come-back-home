/**
 * 익명 동시 참여자 배지 (알림 개인화 #4) — "지금 N명이 함께 찾고 있어요".
 *
 * 목적은 사회적 증거다. 혼자가 아니라는 신호가 제보 참여를 끌어올린다.
 *
 * **표시 전용 컴포넌트다.** 데이터도 정책도 안에 두지 않는다 — 참여자 수는
 * `usePresenceCount(caseId)` 로 화면이 가져오고, "몇 명 미만이면 안 띄운다"는
 * 임계값도 거기에 있다. 디자인 교체 시 이 파일이 통째로 바뀌어도 하트비트와
 * 임계 규칙이 같이 사라지지 않게 하기 위해서다.
 *
 * 색: **중립**(surfaceAlt/textBody). 토큰 §은 색을 "상태 심각도"로만 쓰라고 못박는데
 * 참여자 수는 심각도가 아니다. 그린은 산책 모드, 앰버는 수색 진행, 빨강은 긴급에
 * 예약돼 있으므로 여기에 쓰면 위계가 깨진다.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';

export type PresenceBadgeProps = {
  /** 표시할 참여자 수. `usePresenceCount()` 가 null 을 주면 렌더하지 않는다. */
  watching: number;
  /** 다크 트리(운영자·잠금화면)에서 쓸 때. */
  dark?: boolean;
  /**
   * 짧은 표기("4명"). 이미 "지금 함께 찾고 있어요" 같은 문맥이 옆에 있어
   * 전체 문장을 반복하면 같은 말이 두 번 나오는 자리에서 쓴다.
   * 낭독 문구는 compact 여부와 무관하게 항상 전체 문장이다 — 스크린리더에는
   * 옆 문맥이 함께 읽힌다는 보장이 없으므로 "4명"만 들리면 뜻이 없다.
   */
  compact?: boolean;
};

export function PresenceBadge({ watching, dark = false, compact = false }: PresenceBadgeProps) {
  const text = `지금 ${watching}명이 함께 찾고 있어요`;
  const label = compact ? `${watching}명` : text;

  return (
    <View
      accessible
      accessibilityRole="text"
      // 폴링으로 수시로 바뀌는 값이라 live region 을 걸면 스크린리더가 계속 끼어든다.
      // 긴급 경보 낭독을 방해하지 않도록 갱신은 조용히 둔다.
      accessibilityLabel={text}
      style={[styles.pill, { backgroundColor: dark ? color.operatorSurfaceAlt : color.surfaceAlt }]}
    >
      <View style={[styles.dot, { backgroundColor: dark ? color.operatorTextSec : color.textCaption }]} />
      <Text
        style={[styles.label, { color: dark ? color.operatorText : color.textBody }]}
        allowFontScaling
        maxFontSizeMultiplier={type.maxScale}
        numberOfLines={1}
      >
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: space.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
  label: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
  },
});

export default PresenceBadge;
