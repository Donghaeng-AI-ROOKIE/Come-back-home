/**
 * 「돌아오길」 워드마크.
 *
 * ## PNG 를 쓰지 않는다
 * `logo-guardian.png`(77×42)·`logo-citizen.png`(57×31)를 쓰고 있었는데 둘 다
 * 문제가 있었다(실측 08-12).
 *
 *  - **흰 배경이 박혀 있다.** 알파 채널은 있는데 투명 픽셀이 0% 였다. 그래서
 *    초록 배경 화면(보호자 모드)에서 로고 자리에 **흰 상자**가 생겼다.
 *  - **원본이 딱 1배 크기다.** 폰은 화면 배율이 2~3배라 그대로 확대되며
 *    글자가 뭉개졌다.
 *
 * 벡터로 바꾸면 둘 다 사라진다 — 배경이 없고, 어떤 크기에서도 선명하다.
 * 크기는 시안 값을 그대로 쓴다(보호자 77×42, 시민 57×31).
 *
 * `logo-wordmark.svg` 는 `report-done-logo.svg` 에서 **루트의 고정 width/height 와
 * `preserveAspectRatio="none"` 만** 뗀 것이다. 크기를 쓰는 쪽에서 정하고, 비율이
 * 찌그러지지 않게 하려는 것이다.
 *
 * ⚠️ 이 파일 안의 `<rect fill="white"/>` 는 **배경이 아니라 clipPath 정의**다.
 * 배경인 줄 알고 지웠다가 로고가 통째로 잘려 사라졌다(실측 08-12). 흰 상자는
 * 이 SVG 가 아니라 PNG 쪽 문제였다 — 루트가 `fill="none"` 이라 배경이 없다.
 */
import React from 'react';
import Wordmark from '../../assets/figma/logo-wordmark.svg';

export default function FigmaLogo({ mode }: { mode: 'guardian' | 'citizen' }) {
  const isGuardian = mode === 'guardian';
  return (
    <Wordmark
      width={isGuardian ? 77 : 57}
      height={isGuardian ? 42 : 31}
      accessibilityLabel={isGuardian ? '돌아오길 보호자 안심 모드' : '돌아오길'}
    />
  );
}
