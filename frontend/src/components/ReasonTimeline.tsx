/**
 * 근거 타임라인 (spec §3.4, 운영자 '근거' 뷰). 마음 상태 추론 스텝을 세로로.
 * 각 스텝: 점 + 연결선 · 시각 · 상태(굵게) · 혼란도 바(0..1, width%) · 노트 캡션.
 * 혼란도는 색만이 아니라 수치(%)로도 병기 — 색약 접근성(spec §4.2). dark=운영자 다크.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';
import type { ReasonStep } from '../types/domain';

export type ReasonTimelineProps = {
  steps: ReasonStep[];
  dark?: boolean;
};

/** 혼란도 수준 → 심각도 색(고정 hex, 라이트/다크 공유). 색+수치 이중부호화. */
function confusionColor(c: number): string {
  if (c >= 0.66) return color.critical;
  if (c >= 0.33) return color.search;
  return color.walk;
}

export function ReasonTimeline({ steps, dark }: ReasonTimelineProps) {
  const c = dark
    ? {
        alt: color.operatorSurfaceAlt,
        border: color.operatorBorder,
        text: color.operatorText,
        sub: color.operatorTextSec,
      }
    : {
        alt: color.surfaceAlt,
        border: color.border,
        text: color.text,
        sub: color.textCaption,
      };

  return (
    <View style={styles.wrap}>
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1;
        const pct = Math.round(Math.min(1, Math.max(0, step.confusion)) * 100);
        const barColor = confusionColor(step.confusion);
        return (
          <View key={step.id} style={styles.row}>
            <View style={styles.rail}>
              <View style={[styles.dot, { backgroundColor: barColor, borderColor: c.border }]} />
              {!isLast ? <View style={[styles.line, { backgroundColor: c.border }]} /> : null}
            </View>
            <View style={[styles.content, isLast && styles.contentLast]}>
              <View style={styles.head}>
                <Text
                  style={[styles.time, { color: c.sub }]}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  {step.time}
                </Text>
                <Text
                  style={[styles.status, { color: c.text }]}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  {step.status}
                </Text>
              </View>
              <View
                style={styles.barGraphic}
                accessible
                accessibilityRole="image"
                accessibilityLabel={`혼란도 ${pct}%`}
              >
                <View style={[styles.barTrack, { backgroundColor: c.alt }]}>
                  <View style={[styles.barFill, { width: `${pct}%`, backgroundColor: barColor }]} />
                </View>
                <Text
                  style={[styles.pct, { color: c.sub }]}
                  allowFontScaling
                  maxFontSizeMultiplier={type.maxScale}
                >
                  {pct}%
                </Text>
              </View>
              <Text
                style={[styles.note, { color: c.sub }]}
                allowFontScaling
                maxFontSizeMultiplier={type.maxScale}
              >
                {step.note}
              </Text>
            </View>
          </View>
        );
      })}
    </View>
  );
}

const DOT = 14;

const styles = StyleSheet.create({
  wrap: { alignSelf: 'stretch' },
  row: { flexDirection: 'row', alignItems: 'stretch' },
  rail: { width: DOT, alignItems: 'center', marginRight: space.md },
  dot: {
    width: DOT,
    height: DOT,
    borderRadius: DOT / 2,
    borderWidth: 2,
    marginTop: 2,
  },
  line: { width: 2, flex: 1, marginTop: space.xs, borderRadius: 1 },
  content: { flex: 1, paddingBottom: space.lg },
  contentLast: { paddingBottom: 0 },
  head: { flexDirection: 'row', alignItems: 'baseline', flexWrap: 'wrap' },
  time: {
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
    marginRight: space.sm,
    fontVariant: ['tabular-nums'],
  },
  status: {
    fontSize: type.size.body,
    fontWeight: type.weight.black,
    fontFamily: type.family,
    flexShrink: 1,
  },
  barGraphic: { flexDirection: 'row', alignItems: 'center', marginTop: space.sm },
  barTrack: { flex: 1, height: 10, borderRadius: radius.pill, overflow: 'hidden' },
  barFill: { height: '100%', borderRadius: radius.pill },
  pct: {
    marginLeft: space.sm,
    minWidth: 44,
    textAlign: 'right',
    fontSize: type.size.label,
    fontWeight: type.weight.bold,
    fontFamily: type.family,
    fontVariant: ['tabular-nums'],
  },
  note: {
    marginTop: space.xs,
    fontSize: type.size.label,
    fontWeight: type.weight.regular,
    fontFamily: type.family,
    lineHeight: 22,
  },
});

export default ReasonTimeline;
