/**
 * 예측 시간축 슬라이더 (spec §3.4, §4.4). 4개 정지점 0h/1h/3h/6h + 연결 트랙선.
 * 각 정지점 = Pressable role="button", 라벨 "경과 Nh", 활성 강조(색+굵기+큰 점).
 * dark=운영자 다크. accent 기본 수색 앰버(예측 진행, spec §4.1).
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { color, space, type } from '../theme/tokens';
import type { TimeAxis } from '../types/domain';

export type TimeAxisSliderProps = {
  value: TimeAxis;
  onChange: (t: TimeAxis) => void;
  /** 활성 강조색. 기본 수색 앰버(예측 진행, spec §4.1). */
  accent?: string;
  dark?: boolean;
};

const STOPS: TimeAxis[] = [0, 1, 3, 6];

export function TimeAxisSlider({ value, onChange, accent = color.search, dark }: TimeAxisSliderProps) {
  const line = dark ? color.operatorBorder : color.border;
  const idleFill = dark ? color.operatorSurfaceAlt : color.surfaceAlt;
  const idleInk = dark ? color.operatorTextSec : color.textCaption;

  return (
    <View style={styles.wrap} accessibilityRole="tablist" accessibilityLabel="예측 시간축">
      <View style={styles.track}>
        <View style={[styles.line, { backgroundColor: line }]} />
        {STOPS.map((t) => {
          const active = t === value;
          return (
            <Pressable
              key={t}
              onPress={() => onChange(t)}
              accessibilityRole="button"
              accessibilityLabel={`경과 ${t}시간`}
              accessibilityState={{ selected: active }}
              style={({ pressed }) => [styles.stop, pressed && styles.pressed]}
            >
              <View style={styles.dotZone}>
                <View
                  style={[
                    styles.dot,
                    active
                      ? { backgroundColor: accent, borderColor: accent, transform: [{ scale: 1.25 }] }
                      : { backgroundColor: idleFill, borderColor: line },
                  ]}
                />
              </View>
              <Text
                style={[
                  styles.label,
                  {
                    color: active ? accent : idleInk,
                    fontWeight: active ? type.weight.black : type.weight.medium,
                  },
                ]}
                allowFontScaling
                maxFontSizeMultiplier={type.maxScale}
                numberOfLines={1}
              >
                {`경과 ${t}h`}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const DOT_ZONE = 24;

const styles = StyleSheet.create({
  wrap: { alignSelf: 'stretch' },
  track: { flexDirection: 'row', position: 'relative' },
  line: {
    position: 'absolute',
    height: 2,
    borderRadius: 1,
    top: DOT_ZONE / 2 - 1,
    left: '12.5%',
    right: '12.5%',
  },
  stop: {
    flex: 1,
    minHeight: 48,
    alignItems: 'center',
  },
  pressed: { opacity: 0.7 },
  dotZone: { height: DOT_ZONE, justifyContent: 'center', alignItems: 'center' },
  dot: {
    width: 14,
    height: 14,
    borderRadius: 7,
    borderWidth: 2,
  },
  label: {
    marginTop: space.xs,
    fontSize: type.size.label,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
  },
});

export default TimeAxisSlider;
