/**
 * 익명 동시 참여자 배지 (알림 개인화 #4) — "지금 N명이 함께 찾고 있어요".
 *
 * 목적은 사회적 증거다. 혼자가 아니라는 신호가 제보 참여를 끌어올린다.
 *
 * 색: **중립**(surfaceAlt/textBody). 토큰 §은 색을 "상태 심각도"로만 쓰라고 못박는데
 * 참여자 수는 심각도가 아니다. 그린은 산책 모드, 앰버는 수색 진행, 빨강은 긴급에
 * 예약돼 있으므로 여기에 쓰면 위계가 깨진다.
 *
 * 2명 미만이면 아예 렌더하지 않는다:
 *  - "1명이 함께 찾고 있어요" = 나 혼자라는 뜻이라 사회적 증거로 역효과.
 *  - 익명 집합의 최소 크기 확보 — 카운트 1은 특정 개인을 가리키는 것과 같아진다.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';
import { usePresence } from '../hooks/queries';

export type PresenceBadgeProps = {
  caseId: string;
  /** 다크 트리(운영자·잠금화면)에서 쓸 때. */
  dark?: boolean;
};

/** 이 수 미만이면 표시하지 않는다 (위 주석의 두 가지 이유). */
export const PRESENCE_MIN_VISIBLE = 2;

export function PresenceBadge({ caseId, dark = false }: PresenceBadgeProps) {
  // 실패해도 조용히 사라진다 — 에러 UI를 띄우면 배지 하나 때문에
  // 긴급 화면에 "오류"가 뜨는 셈이라 오히려 해롭다.
  const { data } = usePresence(caseId);
  const watching = data ?? 0;
  if (watching < PRESENCE_MIN_VISIBLE) return null;

  const text = `지금 ${watching}명이 함께 찾고 있어요`;

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
        {text}
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
