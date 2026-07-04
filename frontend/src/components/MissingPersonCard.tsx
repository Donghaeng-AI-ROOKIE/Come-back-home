/**
 * 실종자 정보 카드 (spec §2.5, §5). 단일 소스 useMissingPersonStore().profile 바인딩.
 * 실사진 대신 실루엣 플레이스홀더(개인정보/2차가해 방지). "남성"·"84세" 하드코딩 금지.
 * full: 이름 + 나이·성별·인지상태 + 인상착의 칩. compact: 좁은 행 레이아웃.
 * anon: MISSING_ANON(78세 어르신) + 구역만 — 실명·인지상태(의료정보) 비노출.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';
import { MISSING_ANON } from '../data/missing';
import { useMissingPersonStore } from '../store/missingPersonStore';

export type MissingPersonCardProps = {
  variant?: 'full' | 'compact';
  anon?: boolean;
  showAppearanceChips?: boolean;
  dark?: boolean;
};

export function MissingPersonCard({
  variant = 'full',
  anon = false,
  showAppearanceChips,
  dark = false,
}: MissingPersonCardProps) {
  const profile = useMissingPersonStore((s) => s.profile);
  const isFull = variant === 'full';
  // 기본값: full 또는 anon이면 인상착의 노출(anon은 실명 대신 인상착의·구역으로 식별).
  const chipsOn = showAppearanceChips ?? (anon || isFull);

  const sexLabel = profile.sex === 'F' ? '여성' : '남성';
  const title = anon ? MISSING_ANON : profile.name;
  // anon은 나이/인지상태(의료정보) 비노출 → 구역만. 일반은 나이·성별·인지상태.
  const meta = anon ? `${profile.area} 인근` : `${profile.age}세 · ${sexLabel} · ${profile.cognition}`;

  const c = dark
    ? {
        surface: color.operatorSurface,
        border: color.operatorBorder,
        title: color.operatorText,
        body: color.operatorTextSec,
        avatarBg: color.operatorSurfaceAlt,
        chipBg: color.operatorSurfaceAlt,
        chipInk: color.operatorText,
      }
    : {
        surface: color.surface,
        border: color.border,
        title: color.text,
        body: color.textBody,
        avatarBg: color.surfaceAlt,
        chipBg: color.surfaceAlt,
        chipInk: color.textBody,
      };

  const appearanceText = chipsOn ? ` 인상착의 ${profile.appearance.join(', ')}.` : '';
  const a11yLabel = anon
    ? `실종 어르신. ${MISSING_ANON}. ${profile.area} 인근.${appearanceText}`
    : `실종자 ${profile.name}. ${profile.age}세 ${sexLabel}. ${profile.cognition}.${appearanceText}`;

  const avatarSize = isFull ? 64 : 48;

  return (
    <View
      accessible
      accessibilityLabel={a11yLabel}
      style={[
        styles.card,
        { backgroundColor: c.surface, borderColor: c.border },
        isFull ? styles.cardFull : styles.cardCompact,
      ]}
    >
      <View style={styles.row}>
        <View
          style={[
            styles.avatar,
            {
              width: avatarSize,
              height: avatarSize,
              borderRadius: avatarSize / 2,
              backgroundColor: c.avatarBg,
              borderColor: c.border,
            },
          ]}
        >
          <Text
            style={[styles.avatarGlyph, { fontSize: avatarSize * 0.52 }]}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
          >
            {'👤'}
          </Text>
        </View>

        <View style={styles.textCol}>
          <Text
            style={[
              styles.title,
              { color: c.title, fontSize: isFull ? type.size.cardTitle : type.size.body },
            ]}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
            numberOfLines={1}
          >
            {title}
          </Text>
          <Text
            style={[styles.meta, { color: c.body }]}
            allowFontScaling
            maxFontSizeMultiplier={type.maxScale}
            numberOfLines={2}
          >
            {meta}
          </Text>

          {chipsOn ? (
            <View style={styles.chips}>
              {profile.appearance.map((item) => (
                <View key={item} style={[styles.chip, { backgroundColor: c.chipBg }]}>
                  <Text
                    style={[styles.chipText, { color: c.chipInk }]}
                    allowFontScaling
                    maxFontSizeMultiplier={type.maxScale}
                    numberOfLines={1}
                  >
                    {item}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    borderWidth: 1,
  },
  cardFull: { padding: space.lg },
  cardCompact: { padding: space.md },
  row: { flexDirection: 'row', alignItems: 'center' },
  avatar: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    marginRight: space.lg,
  },
  avatarGlyph: { textAlign: 'center' },
  textCol: { flex: 1 },
  title: { fontWeight: type.weight.black, fontFamily: type.family },
  meta: {
    marginTop: space.xs,
    fontSize: type.size.label,
    fontWeight: type.weight.medium,
    fontFamily: type.family,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', marginTop: space.sm },
  chip: {
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    borderRadius: radius.pill,
    marginRight: space.sm,
    marginTop: space.xs,
  },
  chipText: { fontSize: type.size.label, fontWeight: type.weight.medium, fontFamily: type.family },
});

export default MissingPersonCard;
