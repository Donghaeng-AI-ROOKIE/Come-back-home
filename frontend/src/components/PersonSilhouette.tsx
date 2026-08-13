/**
 * 인상착의 배지 — **작은 프로필 자리(42~88px)에 들어가는 그림.**
 *
 * ## 왜 사진이 아닌가
 * 이 서비스는 사진을 받지 않는다(2026-08-07 결정). 그러니 여기에 실제 사진이 뜨면
 * 그건 실종자가 아니라 **아무 상관 없는 사람의 얼굴**이다. 그래서 사진 대신 그린
 * 그림을 쓴다.
 *
 * ⚠️ 다만 이 그림은 **특정 인상이 있는 얼굴**이다(2026-08-12 교체). 실종자마다
 * 달라지지 않고 성별도 반영하지 않으므로, 시민이 "이렇게 생긴 사람"으로 읽지
 * 않도록 옆 텍스트가 실제 식별 정보를 담당해야 한다 — 나이·성별은 카드 문구가,
 * 부위별 옷 색은 인상착의 상세(AppearanceFigure)가 맡는다.
 *
 * ## 왜 여기서는 옷을 안 그리나
 * 42~88px 에서는 옷 모양을 그려 봐야 뭉개져 색조차 안 읽힌다(실측 08-12).
 * 전신 SVG·비트맵 틴트 둘 다 이 크기에서 실패했다. 그래서 배지는 "사람"이라는
 * 것만 전달하고 색은 상세 화면에 넘긴다.
 */
import React from 'react';
import { Image, StyleSheet, View } from 'react-native';
import { appearanceAvatarProfile, type AppearanceColors } from '../utils/appearanceAvatar';

const faceImage = require('../../assets/avatar/missing-person-face.png');

export type PersonSilhouetteProps = {
  colors?: AppearanceColors;
  /** 보호자 입력 순서: 상의, 하의, 신발, 키/체형/소지품. */
  appearance?: string[];
  size?: number;
  /** 원형 배지로 감쌀지(경보 상세의 프로필 자리). */
  rounded?: boolean;
  /**
   * 이전 SVG 아바타에서 전신/얼굴을 고르던 옵션. 지금은 그림 자체가 얼굴이라
   * 두 값의 결과가 같아 무시한다 — 호출부를 한꺼번에 고치지 않으려고 받아만 둔다.
   */
  focus?: 'full' | 'face';
  style?: any;
};

/** 스크린리더용 색 이름 — 화면에는 안 쓴다. */
const HEX_NAMES: Record<string, string> = {
  '#D84B4B': '빨강', '#E58A42': '주황', '#E7C547': '노랑', '#C7A12F': '머스타드',
  '#4E9A62': '초록', '#6F7F45': '올리브', '#918B65': '카키', '#73C4AA': '민트',
  '#368B88': '청록', '#75B5DF': '하늘색', '#3D6FB4': '파랑', '#344568': '남색',
  '#7B62A7': '보라', '#B0A5D6': '연보라', '#E49DB7': '분홍', '#EFB99D': '살구색',
  '#895D43': '갈색', '#BF9169': '카멜', '#D9C7A8': '베이지', '#EEE5D3': '아이보리',
  '#F8F8F5': '흰색', '#A5AAA8': '회색', '#C8CDD0': '은색', '#4D5352': '진회색',
  '#292D2C': '검정', '#7D3548': '와인', '#C59F2C': '금색',
};

export default function PersonSilhouette({
  colors,
  appearance = [],
  size = 62,
  rounded = true,
  style,
}: PersonSilhouetteProps) {
  const profile = appearanceAvatarProfile(colors, appearance);
  // 배지에 색을 그리지는 않지만, 화면을 못 보는 사용자에게는 읽어 준다.
  const spoken = [
    profile.topKnown && `상의 ${HEX_NAMES[profile.top] ?? '색상'}`,
    profile.bottomKnown && `하의 ${HEX_NAMES[profile.bottom] ?? '색상'}`,
    profile.shoesKnown && `신발 ${HEX_NAMES[profile.shoes] ?? '색상'}`,
  ].filter(Boolean).join(', ');

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
        spoken
          ? `실종자 자리 그림입니다. 사진이 아닙니다. 등록된 인상착의는 ${spoken}.`
          : '실종자 자리 그림입니다. 사진이 아닙니다.'
      }
    >
      <Image source={faceImage} style={styles.face} resizeMode="cover" />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: '#F4F7F5', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  // 원본 그림에 여백이 있어 그대로 넣으면 원형 배지 안에서 얼굴이 작다.
  // 살짝 키워 가운데를 채운다.
  face: { width: '112%', height: '112%' },
});
