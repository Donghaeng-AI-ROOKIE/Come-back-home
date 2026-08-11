/**
 * 인상착의 실루엣 — **사진 자리에 들어가는 유일한 그림.**
 *
 * ## 왜 사진이 아닌가
 * 이 서비스는 사진을 받지 않는다(2026-08-07 결정 — 실제로 동작한 적 없는 스텁이었다).
 * 그러니 화면에 사람 사진이 떠 있으면 그건 실종자가 아니라 **아무 상관 없는 사람의
 * 얼굴**이다. 디자인 시안의 자리표시 사진을 그대로 두면 시연에서 그 얼굴이 실종자로
 * 읽힌다.
 *
 * 대신 보호자가 실제로 입력한 옷 색(백엔드가 `top_color`·`bottom_color`·`shoes_color`
 * 로 추출)을 채운 실루엣을 그린다 — 수색에 쓰이는 정보만 남고, 없는 정보는 회색으로
 * 비어 있는 것이 보인다.
 *
 * 색 이름 → hex 매핑은 프론트 담당이다(backend/app/phase1/color_extract.py 주석).
 */
import React from 'react';
import { View, StyleSheet } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';

/** 백엔드 color_extract 태그 전체. 없는 색이 오면 unknown 과 같게 다룬다. */
const HEX: Record<string, string> = {
  red: '#D64545', orange: '#E8883A', yellow: '#E9C548', mustard: '#C9A227',
  green: '#4C9A5A', olive: '#6B7A3A', khaki: '#8F8B5E', mint: '#7FCBB0',
  teal: '#3E8E8E', skyblue: '#7FB6E0', blue: '#3B6FB5', navy: '#2C3E63',
  purple: '#7B5EA7', lavender: '#B3A5D6', pink: '#E5A0B8', peach: '#F0BFA0',
  brown: '#8A5A3B', camel: '#C2946A', beige: '#DCC9A8', ivory: '#EFE7D6',
  white: '#F5F5F5', gray: '#A8A8A8', silver: '#C9CDD2', charcoal: '#4A4A4A',
  black: '#2B2B2B', wine: '#7A2E42', gold: '#C9A227',
};
/** 정보 없음 — "회색 옷"이 아니라 "모른다"는 뜻으로 읽히게 아주 옅게. */
const UNKNOWN = '#DDDDDD';

function hexOf(tag?: string): string {
  if (!tag || tag === 'unknown') return UNKNOWN;
  return HEX[tag] ?? UNKNOWN;
}

export type PersonSilhouetteProps = {
  colors?: { top?: string; bottom?: string; shoes?: string };
  size?: number;
  /** 원형 배지로 감쌀지(경보 상세의 프로필 자리). */
  rounded?: boolean;
  style?: any;
};

export default function PersonSilhouette({
  colors,
  size = 62,
  rounded = true,
  style,
}: PersonSilhouetteProps) {
  const top = hexOf(colors?.top);
  const bottom = hexOf(colors?.bottom);
  const shoes = hexOf(colors?.shoes);

  const known = [colors?.top, colors?.bottom, colors?.shoes]
    .filter((c) => c && c !== 'unknown').length;

  return (
    <View
      style={[
        styles.wrap,
        { width: size, height: size, borderRadius: rounded ? size / 2 : 8 },
        style,
      ]}
      accessible
      accessibilityRole="image"
      accessibilityLabel={
        known > 0
          ? '보호자가 입력한 옷 색으로 그린 실종자 실루엣입니다. 사진이 아닙니다.'
          : '인상착의 정보가 아직 없습니다.'
      }
    >
      <Svg width={size} height={size} viewBox="0 0 64 64">
        {/* 머리 — 얼굴은 그리지 않는다(식별 정보가 없으므로). */}
        <Circle cx="32" cy="15" r="9" fill="#B9B9B9" />
        {/* 상의 */}
        <Path d="M18 28 Q32 22 46 28 L46 42 L18 42 Z" fill={top} />
        {/* 팔 */}
        <Path d="M14 29 L18 28 L18 42 L14 42 Z" fill={top} />
        <Path d="M50 29 L46 28 L46 42 L50 42 Z" fill={top} />
        {/* 하의 */}
        <Path d="M20 42 L44 42 L41 56 L34 56 L33 46 L31 46 L30 56 L23 56 Z" fill={bottom} />
        {/* 신발 */}
        <Path d="M22 56 L30 56 L30 60 L21 60 Z" fill={shoes} />
        <Path d="M34 56 L42 56 L43 60 L34 60 Z" fill={shoes} />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: '#F2F2F2', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
});
