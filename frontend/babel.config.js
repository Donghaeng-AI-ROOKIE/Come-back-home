// babel-preset-expo가 react-native-worklets/reanimated 플러그인을 자동 포함(SDK 57).
module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
  };
};
