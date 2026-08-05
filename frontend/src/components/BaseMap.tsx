/**
 * 실 타일맵 래퍼 (spec §4.5). 라이트/그레이스케일 고정, POI 클러터 제거 → 히트맵 대비 확보.
 * 오버레이(Polygon/Marker/Circle/Polyline)는 children으로 <MapView> 안에 렌더한다.
 * web은 react-native-maps 미지원 → accessibilityLabel을 담은 스타일 플레이스홀더로 대체.
 */
import React from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';
import type { StyleProp, ViewStyle } from 'react-native';
import MapView, { PROVIDER_DEFAULT } from 'react-native-maps';
import type { MapStyleElement } from 'react-native-maps';
import { color, radius, space, type } from '../theme/tokens';
import { REGION } from '../data/mock';

export type BaseMapProps = {
  /** 초기 리전. 미지정 시 정릉동 기본 REGION. */
  region?: typeof REGION;
  style?: StyleProp<ViewStyle>;
  /** 라이트/그레이스케일 스타일 고정(기본 true) — 히트맵 대비용. */
  grayscale?: boolean;
  children?: React.ReactNode;
  scrollEnabled?: boolean;
  liteMode?: boolean;
  accessibilityLabel?: string;
  /**
   * OS 기본 현재위치 마커(+방향 콘) 표시. 위치 권한이 이미 허용된 화면에서만 켠다.
   *
   * 상대좌표 안내("2시 방향으로 200m")를 폐기하고 이걸 쓰는 이유: 시계 1칸이 30°인데
   * 도심 자기간섭으로 나침반 오차가 ±20~40°다. 결정타는 사용자의 자세 — 알림을 볼 때는
   * 멈춰서 폰을 눕히므로 GPS course 는 죽고(speed 0) 나침반은 하늘을 가리켜
   * "진행 방향"이라는 개념 자체가 성립하지 않는다. 반면 OS 는 센서융합으로 방향을
   * 추정하고, **부정확하면 콘을 넓게 그려 불확실성까지 시각화**한다. 우리가 직접
   * 계산해서 틀린 방향을 단정적으로 말하는 것보다 언제나 낫다.
   */
  showsUserLocation?: boolean;
};

/**
 * 라이트/그레이스케일 맵 스타일(§4.5). Google 계열에서 적용되고 Apple Maps에서는 무시(무해).
 * 채도↓·명도↑로 도로/지명을 흐리게 하여 위에 얹히는 POA 히트맵의 대비를 확보한다.
 */
const GRAYSCALE_STYLE: MapStyleElement[] = [
  { elementType: 'geometry', stylers: [{ saturation: -55 }, { lightness: 12 }] },
  { elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
];

export function BaseMap({
  region,
  style,
  grayscale = true,
  children,
  scrollEnabled = true,
  liteMode = false,
  accessibilityLabel = '지도',
  showsUserLocation = false,
}: BaseMapProps) {
  if (Platform.OS === 'web') {
    return (
      <View
        style={[styles.container, styles.webPlaceholder, style]}
        accessible
        accessibilityRole="image"
        accessibilityLabel={accessibilityLabel}
      >
        <Text style={styles.webIcon} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          🗺️
        </Text>
        <Text style={styles.webText} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          {accessibilityLabel}
        </Text>
        <Text style={styles.webNote} allowFontScaling maxFontSizeMultiplier={type.maxScale}>
          지도는 앱에서 표시돼요
        </Text>
      </View>
    );
  }

  return (
    <View
      style={[styles.container, style]}
      accessibilityRole="image"
      accessibilityLabel={accessibilityLabel}
    >
      <MapView
        provider={PROVIDER_DEFAULT}
        style={styles.map}
        initialRegion={region ?? REGION}
        showsPointsOfInterests={false}
        showsCompass={false}
        toolbarEnabled={false}
        rotateEnabled={false}
        pitchEnabled={false}
        scrollEnabled={scrollEnabled}
        zoomEnabled={scrollEnabled}
        liteMode={liteMode}
        showsUserLocation={showsUserLocation}
        // 위치로 이동 버튼은 끈다 — 지도가 카드 안에 작게 들어가 있어
        // 컨트롤이 정보(최종 목격 핀·예상 반경)를 가린다.
        showsMyLocationButton={false}
        customMapStyle={grayscale ? GRAYSCALE_STYLE : undefined}
      >
        {children}
      </MapView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    minHeight: 180,
    borderRadius: radius.lg,
    overflow: 'hidden',
    backgroundColor: color.surfaceAlt,
    borderWidth: 1,
    borderColor: color.border,
  },
  map: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 },
  webPlaceholder: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
    borderStyle: 'dashed',
  },
  webIcon: { fontSize: 32, marginBottom: space.sm },
  webText: {
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
    color: color.text,
    textAlign: 'center',
  },
  webNote: {
    marginTop: space.xs,
    fontSize: type.size.caption,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    color: color.textCaption,
    textAlign: 'center',
  },
});

export default BaseMap;
