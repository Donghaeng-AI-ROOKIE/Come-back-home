import React, { useId, useMemo } from 'react';
import { SvgXml } from 'react-native-svg';
import { logoXml } from '../assets/guardianSvg';

/**
 * react-native-svg의 웹 렌더러는 SVG 내부 id를 문서 전역으로 해석한다.
 * 탭 화면이 숨겨진 채 남아 있으면 같은 로고의 gradient/clip id가 충돌하므로,
 * 각 인스턴스에 고유 id를 붙여 Figma 그라디언트를 그대로 보존한다.
 */
export function GuardianLogo({ width = 77, height = 42 }: { width?: number; height?: number }) {
  const reactId = useId();
  const xml = useMemo(() => {
    const suffix = reactId.replace(/[^a-zA-Z0-9_-]/g, '');
    return logoXml
      .replaceAll('paint0_linear_0_8169', `paint0_linear_0_8169_${suffix}`)
      .replaceAll('clip0_0_8169', `clip0_0_8169_${suffix}`);
  }, [reactId]);

  return <SvgXml xml={xml} width={width} height={height} />;
}

export default GuardianLogo;
