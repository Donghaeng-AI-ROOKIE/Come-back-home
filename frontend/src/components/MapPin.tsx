/**
 * 지도 커스텀 마커 (spec §2.5, §4.5). BaseMap(MapView) 안에서만 사용.
 * kind별 색/이모지 이중부호화: lastSeen=🔴 긴급(critical) / searchTeam=🟠 수색(search)
 * / tip=💬 제보 / me=🔵 내 위치(walk). 색만이 아니라 이모지·라벨로도 구분.
 * 좌표는 toLatLng로 변환. 정보성 마커라 accessibilityLabel로 요약.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Marker } from 'react-native-maps';
import { color, radius, type } from '../theme/tokens';
import { toLatLng } from '../utils/color';
import type { GeoPoint } from '../types/domain';

export type MapPinKind = 'lastSeen' | 'searchTeam' | 'tip' | 'me';

export type MapPinProps = {
  kind: MapPinKind;
  coordinate: GeoPoint;
  title?: string;
  description?: string;
};

const KIND: Record<MapPinKind, { emoji: string; ring: string; label: string }> = {
  lastSeen: { emoji: '🔴', ring: color.critical, label: '최종 목격 위치' },
  searchTeam: { emoji: '🟠', ring: color.search, label: '수색팀 위치' },
  tip: { emoji: '💬', ring: color.textBody, label: '제보 위치' },
  me: { emoji: '🔵', ring: color.walk, label: '내 위치' },
};

export function MapPin({ kind, coordinate, title, description }: MapPinProps) {
  const cfg = KIND[kind];
  const a11y = [cfg.label, title, description].filter((s): s is string => !!s).join(' · ');

  return (
    <Marker
      coordinate={toLatLng(coordinate)}
      title={title}
      description={description}
      anchor={{ x: 0.5, y: 0.5 }}
      accessibilityLabel={a11y}
    >
      <View
        style={[styles.bubble, { borderColor: cfg.ring }]}
        accessible
        accessibilityRole="image"
        accessibilityLabel={a11y}
      >
        <Text
          style={styles.emoji}
          allowFontScaling
          maxFontSizeMultiplier={type.maxScale}
        >
          {cfg.emoji}
        </Text>
      </View>
    </Marker>
  );
}

const styles = StyleSheet.create({
  bubble: {
    width: 34,
    height: 34,
    borderRadius: radius.pill,
    borderWidth: 2.5,
    backgroundColor: color.surface,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: color.text,
    shadowOpacity: 0.22,
    shadowRadius: 3,
    shadowOffset: { width: 0, height: 1 },
    elevation: 3,
  },
  emoji: {
    fontSize: 18,
    textAlign: 'center',
    fontFamily: type.family,
  },
});

export default MapPin;
