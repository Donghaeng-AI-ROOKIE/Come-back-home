/**
 * 실종자 정보 카드 (spec §2.5, §5).
 * 실사진 대신 실루엣 플레이스홀더(개인정보/2차가해 방지). "남성"·"84세" 하드코딩 금지.
 * full: 넓은 레이아웃 + 인상착의 칩. compact: 좁은 행 레이아웃.
 *
 * **표시 전용 컴포넌트다.** 무엇을 노출할지는 여기서 정하지 않는다 —
 * 화면이 `toAnonView()`(시민용) 또는 `toFullView()`(보호자·운영자용)로 미리
 * 눌러 담아 넘긴다. 이 컴포넌트는 원본 프로필의 `name`·`age`·`cognition` 을
 * 아예 받지 못하므로, 교체하거나 잘못 써도 민감정보가 샐 수 없다.
 * 자세한 근거: `data/missingView.ts`
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { color, radius, space, type } from '../theme/tokens';
import type { MissingPersonView } from '../data/missingView';

export type MissingPersonCardProps = {
  /** 노출 범위가 이미 결정된 뷰. `toAnonView` / `toFullView` 참고. */
  view: MissingPersonView;
  variant?: 'full' | 'compact';
  showAppearanceChips?: boolean;
  dark?: boolean;
};

export function MissingPersonCard({
  view,
  variant = 'full',
  showAppearanceChips,
  dark = false,
}: MissingPersonCardProps) {
  const isFull = variant === 'full';
  const chipsOn = showAppearanceChips ?? isFull;

  const { title, meta, appearance } = view;

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

  // 낭독도 뷰가 준 문자열만 조합한다 — 시각 표시와 낭독의 노출 범위가 어긋나면
  // 스크린리더 사용자에게만 더 많은 정보가 새는 셈이 된다.
  const appearanceText = chipsOn ? ` 인상착의 ${appearance.join(', ')}.` : '';
  const a11yLabel = `실종자 정보. ${title}. ${meta}.${appearanceText}`;

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
              {appearance.map((item) => (
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
  title: { fontFamily: type.familyExtraBold },
  meta: {
    marginTop: space.xs,
    fontSize: type.size.label,
    fontFamily: type.familySemiBold,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', marginTop: space.sm },
  chip: {
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    borderRadius: radius.pill,
    marginRight: space.sm,
    marginTop: space.xs,
  },
  chipText: { fontSize: type.size.label, fontFamily: type.familySemiBold },
});

export default MissingPersonCard;
