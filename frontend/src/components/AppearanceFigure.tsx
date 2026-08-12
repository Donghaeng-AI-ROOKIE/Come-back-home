/**
 * 인상착의 전신 그림 — **큰 화면(인상착의 상세) 전용.**
 *
 * ## 왜 사진이 아닌가
 * 이 서비스는 사진을 받지 않는다(2026-08-07 결정). 그러니 화면에 사람 사진이 떠
 * 있으면 그건 실종자가 아니라 **아무 상관 없는 사람의 얼굴**이다. 시안의 자리표시
 * 사진을 그대로 두면 시연에서 그 얼굴이 실종자로 읽힌다. 그래서 보호자가 실제로
 * 입력한 옷 색만 반영한 그림을 그린다.
 *
 * ## 왜 PersonSilhouette 과 따로 있나
 * 저쪽은 42~62px 배지에 쓰인다. 그 크기에서는 전신을 넣어 봐야 옷이 뭉개져
 * 색조차 안 읽히므로 얼굴만 확대해 보여준다(`focus="face"`). 이 그림은 198px
 * 상세 화면 전용이라 반대로 **전신이 다 보이고 옷 모양이 살아 있어야** 한다.
 * 요구가 정반대라 한 컴포넌트에 옵션으로 묶지 않고 나눴다.
 *
 * ## 색이 들어가는 방식
 * 상의·하의·신발이 각각 별도 `<G fill=...>` 이라 순색으로 칠해진다. 단추·주머니·
 * 솔기·신발끈은 색과 무관한 별도 stroke 라 **어떤 색에서도 형태가 남는다** —
 * 어두운 색을 칠하면 디테일이 뭉개지던 비트맵 틴트 방식의 문제가 없다.
 *
 * 색을 모르는 부위는 중립 회색으로 둔다. 추측해서 잘못 알리지 않는다는
 * utils/appearanceAvatar.ts 의 원칙과 같다.
 */
import React from 'react';
import { StyleSheet, View } from 'react-native';
import Svg, { Circle, Ellipse, G, Line, Path, Rect } from 'react-native-svg';
import { appearanceAvatarProfile, type AppearanceColors } from '../utils/appearanceAvatar';

export type AppearanceFigureProps = {
  colors?: AppearanceColors;
  /** 보호자 입력 순서: 상의, 하의, 신발, 키/체형/소지품. */
  appearance?: string[];
  size?: number;
  style?: any;
};

const OUTLINE = '#AEB7B5';
const DETAIL = '#7A8583';
const SKIN = '#F2C6A4';
const HAIR = '#9B7658';
const SHIRT = '#FFFFFF';
/** 색을 모르는 옷 — 회색(gray)은 실제 옷 색이라 그것과 겹치지 않게 더 밝게 둔다. */
const UNKNOWN = '#E8ECEA';

export default function AppearanceFigure({
  colors,
  appearance = [],
  size = 198,
  style,
}: AppearanceFigureProps) {
  const profile = appearanceAvatarProfile(colors, appearance);
  // 체형·키는 그림을 새로 그리지 않고 변형으로 준다. 발이 바닥에 붙어 있어야
  // 하므로 세로는 아래 기준(160), 가로는 몸 중앙(50) 기준으로 늘이고 줄인다.
  const sx = profile.build === 'slim' ? 0.94 : profile.build === 'broad' ? 1.06 : 1;
  const sy = profile.heightScale;
  const transform = `translate(${50 * (1 - sx)} ${160 * (1 - sy)}) scale(${sx} ${sy})`;
  const has = (item: string) => profile.accessories.includes(item as never);
  const top = profile.topKnown ? profile.top : UNKNOWN;
  const bottom = profile.bottomKnown ? profile.bottom : UNKNOWN;
  const shoes = profile.shoesKnown ? profile.shoes : '#F8F9F8';

  const known = [profile.topKnown, profile.bottomKnown, profile.shoesKnown].filter(Boolean).length;

  return (
    <View
      style={[styles.wrap, { width: size, height: size }, style]}
      accessible
      accessibilityRole="image"
      accessibilityLabel={
        known > 0
          ? '보호자가 입력한 상의, 하의, 신발 색으로 그린 인상착의 그림입니다. 사진이 아닙니다.'
          : '인상착의 색 정보가 아직 없습니다.'
      }
    >
      <Svg width="100%" height="100%" viewBox="0 0 100 160" preserveAspectRatio="xMidYMid meet">
        <Ellipse cx="50" cy="153" rx="31" ry="3.8" fill="#DCE3E0" opacity="0.58" />
        <G transform={transform}>
          {/* 머리카락과 이목구비 없는 얼굴 — 특정 인물로 읽히지 않게 한다. */}
          <Path d="M37 18 C37 8 43 4 50 4 C58 4 64 9 63 18 L61 23 L39 23 Z" fill={HAIR} stroke={OUTLINE} strokeWidth="0.8" />
          <Path d="M39 13 C43 7 48 9 50 12 C53 7 59 9 62 15 L62 19 C58 15 55 14 50 14 C45 14 42 16 38 19 Z" fill="#B08866" opacity="0.9" />
          <Path d="M39 18 C39 13 42 10 50 10 C58 10 61 13 61 18 L60 26 C59 32 55 36 50 36 C45 36 41 32 40 26 Z" fill={SKIN} stroke={OUTLINE} strokeWidth="0.75" />
          <Path d="M39.5 18 C40 11 45 8 50 9 C56 8 61 12 61 18 C57 14 54 13 50 13 C46 13 43 15 39.5 20 Z" fill={HAIR} />
          <Path d="M45 32 Q50 34 55 32" fill="none" stroke="#D59F80" strokeWidth="0.55" strokeLinecap="round" opacity="0.65" />

          {/* 목과 안에 받쳐 입은 흰 셔츠 */}
          <Path d="M45.5 32 L45.5 39 L54.5 39 L54.5 32 C52 35 48 35 45.5 32 Z" fill={SKIN} stroke={OUTLINE} strokeWidth="0.7" />
          <Path d="M42 39 L50 36.5 L58 39 L58 71 L42 71 Z" fill={SHIRT} stroke={OUTLINE} strokeWidth="0.8" />
          <Path d="M42 39 L47.5 46 L50 38 L45.5 36.5 Z M58 39 L52.5 46 L50 38 L54.5 36.5 Z" fill="#F4F6F5" stroke={OUTLINE} strokeWidth="0.6" />
          <Line x1="50" y1="46" x2="50" y2="68" stroke="#C9D0CE" strokeWidth="0.65" />
          <Circle cx="50" cy="51" r="0.75" fill="#D8DEDC" />
          <Circle cx="50" cy="58" r="0.75" fill="#D8DEDC" />

          {/* 상의(가디건) — 좌·우 패널, 소매, 밑단. 여기부터 색이 들어간다. */}
          <G fill={top} stroke={OUTLINE} strokeWidth="0.9" strokeLinejoin="round">
            <Path d="M42.5 39 C36 40 30 43 27 49 C24 57 23.5 69 24 79 L25 91 C25.3 94 27.5 96 30.5 95.7 C33 95.4 34.2 93.4 34.5 90 L36 71 L42.8 70 Z" />
            <Path d="M57.5 39 C64 40 70 43 73 49 C76 57 76.5 69 76 79 L75 91 C74.7 94 72.5 96 69.5 95.7 C66.5 95.4 65.8 93.4 65.5 90 L64 71 L57.2 70 Z" />
            <Path d="M42.5 39 L47.5 46 L47.5 88 L35 88 L35 66 L42.8 61 Z" />
            <Path d="M57.5 39 L52.5 46 L52.5 88 L65 88 L65 66 L57.2 61 Z" />
            <Path d="M34.5 86 L65.5 86 L65.5 92 C57 94 43 94 34.5 92 Z" />
            <Path d="M25 89 L34.7 89 L34.7 95 L26 95.7 Z M65.3 89 L75 89 L74 95.7 L65.3 95 Z" />
          </G>
          {/* 주머니·여밈선·단추는 색과 별개 레이어 — 어두운 옷에서도 남는다. */}
          <G fill="none" stroke={DETAIL} strokeWidth="0.55" opacity="0.78">
            <Path d="M35 68 L42 68 L42 79 L36 79" />
            <Path d="M65 68 L58 68 L58 79 L64 79" />
            <Line x1="47.5" y1="47" x2="47.5" y2="87" />
            <Line x1="52.5" y1="47" x2="52.5" y2="87" />
          </G>
          <Circle cx="47.7" cy="56" r="0.9" fill="#F9FAF9" stroke={DETAIL} strokeWidth="0.45" />
          <Circle cx="47.7" cy="65" r="0.9" fill="#F9FAF9" stroke={DETAIL} strokeWidth="0.45" />
          <Circle cx="47.7" cy="74" r="0.9" fill="#F9FAF9" stroke={DETAIL} strokeWidth="0.45" />

          {/* 손은 소매 위에 얹는다 — 팔 실루엣이 깨끗하게 남는다. */}
          <Path d="M26 94 C24 97 24.5 101 27 102.5 C29 104 32 102 32.5 99 L32 93 Z" fill={SKIN} stroke={OUTLINE} strokeWidth="0.7" />
          <Path d="M74 94 C76 97 75.5 101 73 102.5 C71 104 68 102 67.5 99 L68 93 Z" fill={SKIN} stroke={OUTLINE} strokeWidth="0.7" />

          {/* 하의 — 다리를 둘로 나눠 가운데 솔기가 실제로 보이게 한다. */}
          <G fill={bottom} stroke={OUTLINE} strokeWidth="0.9" strokeLinejoin="round">
            <Path d="M35 91 L50 91 L49 141 C48.8 144 46.8 145 43.8 144.7 L35.5 144 C33.6 143.8 33 142 33.3 140 Z" />
            <Path d="M50 91 L65 91 L66.7 140 C67 142 66.4 143.8 64.5 144 L56.2 144.7 C53.2 145 51.2 144 51 141 Z" />
          </G>
          <Path d="M39 93 L39 138 M61 93 L61 138 M50 93 L50 119" fill="none" stroke={DETAIL} strokeWidth="0.55" opacity="0.58" />
          <Path d="M35 95 Q42 98 50 95 Q58 98 65 95" fill="none" stroke={DETAIL} strokeWidth="0.6" opacity="0.7" />

          {/* 신발 — 갑피만 칠하고 밑창·끈은 노출한다. */}
          <G fill={shoes} stroke={OUTLINE} strokeWidth="0.9" strokeLinejoin="round">
            <Path d="M34 142 C37 141 42 141.5 46 144 L48.5 149 C48 151.5 45 152.5 37 152 C33 152 31.5 150.5 32.5 148 Z" />
            <Path d="M66 142 C63 141 58 141.5 54 144 L51.5 149 C51 151.5 55 152.5 63 152 C67 152 68.5 150.5 67.5 148 Z" />
          </G>
          <G fill="none" stroke={DETAIL} strokeWidth="0.6" strokeLinecap="round" opacity="0.82">
            <Path d="M33 149 L47.5 149 M67 149 L52.5 149" />
            <Path d="M38 145 L43 147 M37 147 L43.5 148.5 M62 145 L57 147 M63 147 L56.5 148.5" />
          </G>

          {/* 소지품 — 접수 4번째 칸('키/체형/소지품')에 적힌 내용. */}
          {has('glasses') ? <G fill="none" stroke="#56605E" strokeWidth="1"><Circle cx="45" cy="22" r="3" /><Circle cx="55" cy="22" r="3" /><Line x1="48" y1="22" x2="52" y2="22" /></G> : null}
          {has('hat') ? <Path d="M38 14 Q50 2 62 14 L62 17 L38 17 Z" fill="#65706D" stroke="#4F5A57" strokeWidth="0.7" /> : null}
          {has('bag') ? <G><Path d="M63 45 Q57 65 31 92" fill="none" stroke="#65706D" strokeWidth="2.3" /><Rect x="25" y="94" width="11" height="11" rx="1.7" fill="#65706D" stroke="#4F5A57" strokeWidth="0.7" /></G> : null}
          {has('cane') ? <Path d="M73 98 Q78 94 78 101 L78 150" fill="none" stroke="#65706D" strokeWidth="2" strokeLinecap="round" /> : null}
        </G>
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: '#F4F7F5', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', borderRadius: 8 },
});
