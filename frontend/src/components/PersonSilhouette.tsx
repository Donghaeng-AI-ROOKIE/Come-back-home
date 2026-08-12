/**
 * 인상착의 아바타 — **사진 자리에 들어가는 유일한 그림.**
 *
 * ## 왜 사진이 아닌가
 * 이 서비스는 사진을 받지 않는다(2026-08-07 결정 — 실제로 동작한 적 없는 스텁이었다).
 * 그러니 화면에 사람 사진이 떠 있으면 그건 실종자가 아니라 **아무 상관 없는 사람의
 * 얼굴**이다. 디자인 시안의 자리표시 사진을 그대로 두면 시연에서 그 얼굴이 실종자로
 * 읽힌다.
 *
 * 보호자가 실제로 입력한 상의·하의·신발 색과 체형·소지품만 레이어로 그린다.
 * 얼굴 생김새는 만들지 않으므로 실제 인물로 오인되지 않으면서, 수색에 필요한 차림은
 * 작은 알림 카드에서도 빠르게 구분된다.
 */
import React, { useId } from 'react';
import { View, StyleSheet } from 'react-native';
import Svg, {
  Circle,
  Defs,
  Ellipse,
  G,
  Line,
  LinearGradient,
  Path,
  RadialGradient,
  Rect,
  Stop,
} from 'react-native-svg';
import { appearanceAvatarProfile, type AppearanceColors } from '../utils/appearanceAvatar';

export type PersonSilhouetteProps = {
  colors?: AppearanceColors;
  /** 보호자 입력 순서: 상의, 하의, 신발, 키/체형/소지품. */
  appearance?: string[];
  size?: number;
  /** 원형 배지로 감쌀지(경보 상세의 프로필 자리). */
  rounded?: boolean;
  /** 작은 프로필에서는 얼굴 부분만 확대해 보여준다. */
  focus?: 'full' | 'face';
  style?: any;
};

export default function PersonSilhouette({
  colors,
  appearance = [],
  size = 62,
  rounded = true,
  focus = 'full',
  style,
}: PersonSilhouetteProps) {
  const profile = appearanceAvatarProfile(colors, appearance);
  const known = [profile.topKnown, profile.bottomKnown, profile.shoesKnown].filter(Boolean).length;
  const isCompact = size < 80;
  const torsoHalf = profile.build === 'slim' ? 24 : profile.build === 'broad' ? 34 : 29;
  const left = 80 - torsoHalf;
  const right = 80 + torsoHalf;
  const transform = `translate(0 ${176 * (1 - profile.heightScale)}) scale(1 ${profile.heightScale})`;
  const has = (accessory: string) => profile.accessories.includes(accessory as never);
  const gradientId = useId().replace(/:/g, '');
  const backdropId = `${gradientId}-backdrop`;
  const skinId = `${gradientId}-skin`;
  const hairId = `${gradientId}-hair`;

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
          ? '보호자가 입력한 상의, 하의, 신발 색과 특징으로 그린 인상착의 아바타입니다. 사진이 아닙니다.'
          : '인상착의 정보가 아직 없습니다.'
      }
    >
      <Svg width={size} height={size} viewBox={focus === 'face' ? '38 4 84 82' : '0 0 160 190'}>
        <Defs>
          <RadialGradient id={backdropId} cx="42%" cy="32%" rx="72%" ry="72%">
            <Stop offset="0" stopColor="#F7FCF8" />
            <Stop offset="0.58" stopColor="#E5F5EA" />
            <Stop offset="1" stopColor="#D1EAD9" />
          </RadialGradient>
          <RadialGradient id={skinId} cx="35%" cy="28%" rx="72%" ry="78%">
            <Stop offset="0" stopColor="#FFE1C8" />
            <Stop offset="0.7" stopColor="#E9B68F" />
            <Stop offset="1" stopColor="#CB8C68" />
          </RadialGradient>
          <LinearGradient id={hairId} x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#AAA29B" />
            <Stop offset="0.48" stopColor="#77736F" />
            <Stop offset="1" stopColor="#504F4D" />
          </LinearGradient>
        </Defs>

        <Circle cx="80" cy="91" r="70" fill={`url(#${backdropId})`} />
        {!isCompact ? <Circle cx="80" cy="91" r="59" fill="none" stroke="#B9DEC5" strokeWidth="1.3" strokeDasharray="3 6" /> : null}
        <Ellipse cx="80" cy="176" rx="49" ry="7" fill="#AFCDB9" opacity="0.48" />

        <G transform={transform}>
          {/* 특정 얼굴을 재현하지 않는 공통 캐릭터 표정. */}
          <Circle cx="52" cy="49" r="6.5" fill={`url(#${skinId})`} stroke="#B97958" strokeOpacity="0.35" />
          <Circle cx="108" cy="49" r="6.5" fill={`url(#${skinId})`} stroke="#B97958" strokeOpacity="0.35" />
          <Circle cx="80" cy="47" r="29" fill={`url(#${skinId})`} stroke="#9D6D56" strokeOpacity="0.32" strokeWidth="1.2" />
          <Ellipse cx="70" cy="56" rx="5" ry="2.7" fill="#F49F9B" opacity="0.28" />
          <Ellipse cx="91" cy="56" rx="5" ry="2.7" fill="#F49F9B" opacity="0.28" />
          <Line x1="67" y1="43" x2="73" y2="42" stroke="#5D4B42" strokeWidth="1.5" strokeLinecap="round" />
          <Line x1="87" y1="42" x2="93" y2="43" stroke="#5D4B42" strokeWidth="1.5" strokeLinecap="round" />
          <Circle cx="71" cy="48" r="2.3" fill="#322C29" />
          <Circle cx="89" cy="48" r="2.3" fill="#322C29" />
          <Circle cx="70.3" cy="47.2" r="0.7" fill="#FFFFFF" />
          <Circle cx="88.3" cy="47.2" r="0.7" fill="#FFFFFF" />
          <Path d="M80 49 Q77.8 55 81 55" fill="none" stroke="#B97C61" strokeWidth="1.3" strokeLinecap="round" />
          <Path d="M72 60 Q80 66 88 60 Q85 69 80 69 Q75 69 72 60 Z" fill="#A94E48" />
          <Path d="M75 61 Q80 63 85 61" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" />

          {/* 부드러운 덩어리감이 보이도록 머리카락에도 밝은 면과 그림자를 둔다. */}
          <Path d="M52 43 C50 24 62 12 79 12 C100 12 112 26 107 47 C101 35 96 29 87 27 C79 35 66 36 55 34 C54 37 53 40 52 43 Z" fill={`url(#${hairId})`} />
          <Path d="M58 29 C65 17 82 15 93 20" fill="none" stroke="#FFFFFF" strokeOpacity="0.22" strokeWidth="4" strokeLinecap="round" />
          <Path d="M100 23 Q110 32 106 45" fill="none" stroke="#373836" strokeOpacity="0.3" strokeWidth="3" strokeLinecap="round" />

          {has('hat') ? (
            <G>
              <Path d="M54 29 C56 8 102 8 106 30 Z" fill="#5D9870" stroke="#386D4B" strokeWidth="1.3" />
              <Path d="M51 28 C66 25 104 25 111 31 C94 36 66 35 51 28 Z" fill="#3D7952" />
              <Path d="M63 17 Q78 9 94 17" fill="none" stroke="#FFFFFF" strokeOpacity="0.34" strokeWidth="3" strokeLinecap="round" />
            </G>
          ) : null}
          {has('glasses') ? (
            <G fill="none" stroke="#3F4644" strokeWidth="2.2">
              <Circle cx="70" cy="49" r="8" />
              <Circle cx="90" cy="49" r="8" />
              <Line x1="78" y1="49" x2="82" y2="49" />
              <Line x1="61" y1="47" x2="54" y2="44" />
              <Line x1="99" y1="47" x2="106" y2="44" />
            </G>
          ) : null}

          <Rect x="73" y="70" width="14" height="14" rx="6" fill={`url(#${skinId})`} />

          {/* 상의: 둥근 몸통과 소매를 각각 입체 레이어로 표현한다. */}
          <Path d={`M${left - 1} 84 Q${left - 14} 89 ${left - 15} 103 L${left - 11} 122 Q${left - 9} 130 ${left - 2} 128 Q${left + 4} 126 ${left + 2} 119 L${left + 5} 98 Z`} fill={profile.top} stroke="#43534B" strokeOpacity="0.26" strokeWidth="1.4" />
          <Path d={`M${right + 1} 84 Q${right + 14} 89 ${right + 15} 103 L${right + 11} 122 Q${right + 9} 130 ${right + 2} 128 Q${right - 4} 126 ${right - 2} 119 L${right - 5} 98 Z`} fill={profile.top} stroke="#43534B" strokeOpacity="0.26" strokeWidth="1.4" />
          <Ellipse cx={left - 8} cy="127" rx="6.5" ry="7" fill={`url(#${skinId})`} />
          <Ellipse cx={right + 8} cy="127" rx="6.5" ry="7" fill={`url(#${skinId})`} />
          <Path
            d={`M${left} 82 Q80 73 ${right} 82 L${right - 1} 128 Q80 134 ${left + 1} 128 Z`}
            fill={profile.top}
            stroke="#43534B"
            strokeOpacity="0.28"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
          <Path d={`M${left + 5} 86 Q${left + 11} 80 ${left + 16} 83 L${left + 13} 124`} fill="none" stroke="#FFFFFF" strokeOpacity="0.3" strokeWidth="5" strokeLinecap="round" />
          <Path d={`M${right - 5} 84 L${right - 2} 125`} fill="none" stroke="#24372F" strokeOpacity="0.14" strokeWidth="5" strokeLinecap="round" />
          <Path d="M69 81 Q80 93 91 81" fill="#FFFFFF" fillOpacity="0.82" stroke="#43534B" strokeOpacity="0.16" strokeWidth="1" />
          <Path d="M76 82 L80 92 L84 82" fill={profile.top} opacity="0.82" />

          {/* 하의 */}
          <Path d={`M${left + 2} 124 Q80 130 80 137 L77 164 Q76 169 ${left + 13} 169 Q${left + 7} 168 ${left + 8} 162 Z`} fill={profile.bottom} stroke="#35413C" strokeOpacity="0.3" strokeWidth="1.5" strokeLinejoin="round" />
          <Path d={`M${right - 2} 124 Q80 130 80 137 L83 164 Q84 169 ${right - 13} 169 Q${right - 7} 168 ${right - 8} 162 Z`} fill={profile.bottom} stroke="#35413C" strokeOpacity="0.3" strokeWidth="1.5" strokeLinejoin="round" />
          <Path d={`M${left + 9} 130 L${left + 16} 162`} fill="none" stroke="#FFFFFF" strokeOpacity="0.23" strokeWidth="4" strokeLinecap="round" />
          <Path d={`M${right - 7} 130 L${right - 10} 163`} fill="none" stroke="#1E2D28" strokeOpacity="0.14" strokeWidth="4" strokeLinecap="round" />

          {/* 신발: 레퍼런스처럼 발끝이 둥글고 반사광이 있는 형태. */}
          <Path d={`M${left + 5} 162 Q${left + 14} 159 ${left + 24} 164 L${left + 25} 174 Q${left + 10} 178 ${left - 1} 173 Q${left - 1} 166 ${left + 5} 162 Z`} fill={profile.shoes} stroke="#303735" strokeOpacity="0.45" strokeWidth="1.4" />
          <Path d={`M${right - 24} 164 Q${right - 14} 159 ${right - 5} 162 Q${right + 1} 166 ${right + 1} 173 Q${right - 10} 178 ${right - 25} 174 Z`} fill={profile.shoes} stroke="#303735" strokeOpacity="0.45" strokeWidth="1.4" />
          <Path d={`M${left + 5} 166 Q${left + 12} 163 ${left + 19} 166`} fill="none" stroke="#FFFFFF" strokeOpacity="0.5" strokeWidth="2.2" strokeLinecap="round" />
          <Path d={`M${right - 19} 166 Q${right - 12} 163 ${right - 5} 166`} fill="none" stroke="#FFFFFF" strokeOpacity="0.5" strokeWidth="2.2" strokeLinecap="round" />

          {has('bag') ? (
            <G>
              <Path d={`M${right - 7} 83 Q${right + 19} 96 ${right + 10} 133`} fill="none" stroke="#7B624B" strokeWidth="3.2" strokeLinecap="round" />
              <Rect x={right + 2} y="111" width="27" height="33" rx="8" fill="#C49150" stroke="#735337" strokeWidth="1.5" />
              <Path d={`M${right + 8} 114 Q${right + 15} 103 ${right + 23} 114`} fill="none" stroke="#735337" strokeWidth="2.2" />
              <Path d={`M${right + 7} 116 L${right + 10} 137`} stroke="#FFFFFF" strokeOpacity="0.28" strokeWidth="3" strokeLinecap="round" />
            </G>
          ) : null}
          {has('cane') ? (
            <G fill="none" strokeLinecap="round">
              <Path d={`M${right + 7} 125 Q${right + 20} 119 ${right + 20} 130 L${right + 14} 172`} stroke="#6B5039" strokeWidth="4.2" />
              <Path d={`M${right + 8} 124 Q${right + 17} 120 ${right + 20} 127`} stroke="#C7A27B" strokeWidth="1.5" />
              <Line x1={right + 10} y1="173" x2={right + 18} y2="173" stroke="#4D3A2B" strokeWidth="3.2" />
            </G>
          ) : null}
        </G>
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: '#F4F7F5', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
});
