/**
 * Metro 설정.
 *
 * 웹 타깃에서만 `react-native-maps` 를 스텁으로 바꿔치기한다 — 이유는
 * `src/shims/react-native-maps.web.ts` 주석 참고(요약: Marker·Circle 계열에
 * 웹 변형이 없어 모듈 평가 시점에 터진다).
 *
 * 네이티브(ios/android) 번들은 전혀 건드리지 않으므로 실기기 동작에 영향이 없다.
 */
const path = require('path');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

config.transformer.babelTransformerPath = require.resolve('react-native-svg-transformer/expo');
config.resolver.assetExts = config.resolver.assetExts.filter((ext) => ext !== 'svg');
config.resolver.sourceExts = [...config.resolver.sourceExts, 'svg'];

const MAPS_WEB_SHIM = path.resolve(__dirname, 'src/shims/react-native-maps.web.ts');

const defaultResolveRequest = config.resolver.resolveRequest;

config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (platform === 'web' && moduleName === 'react-native-maps') {
    return { type: 'sourceFile', filePath: MAPS_WEB_SHIM };
  }
  // 기본 리졸버로 위임. Expo 가 이미 resolveRequest 를 설정해 뒀을 수 있으므로
  // context.resolveRequest 가 아니라 원래 값을 우선 쓴다(있으면).
  return (defaultResolveRequest ?? context.resolveRequest)(context, moduleName, platform);
};

module.exports = config;
