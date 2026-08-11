export type AppearanceColors = {
  top?: string;
  bottom?: string;
  shoes?: string;
};

export type AvatarBuild = 'slim' | 'regular' | 'broad';
export type AvatarAccessory = 'hat' | 'glasses' | 'bag' | 'cane';

export type AppearanceAvatarProfile = {
  top: string;
  bottom: string;
  shoes: string;
  topKnown: boolean;
  bottomKnown: boolean;
  shoesKnown: boolean;
  build: AvatarBuild;
  heightScale: number;
  accessories: AvatarAccessory[];
};

/** 백엔드 `color_extract.py`가 보내는 표준 태그와 동일한 팔레트. */
const HEX: Record<string, string> = {
  red: '#D84B4B', orange: '#E58A42', yellow: '#E7C547', mustard: '#C7A12F',
  green: '#4E9A62', olive: '#6F7F45', khaki: '#918B65', mint: '#73C4AA',
  teal: '#368B88', skyblue: '#75B5DF', blue: '#3D6FB4', navy: '#344568',
  purple: '#7B62A7', lavender: '#B0A5D6', pink: '#E49DB7', peach: '#EFB99D',
  brown: '#895D43', camel: '#BF9169', beige: '#D9C7A8', ivory: '#EEE5D3',
  white: '#F8F8F5', gray: '#A5AAA8', silver: '#C8CDD0', charcoal: '#4D5352',
  black: '#292D2C', wine: '#7D3548', gold: '#C59F2C',
};

/** 색을 추측해서 잘못 알리지 않도록, 정말 모르는 항목만 중립색을 쓴다. */
const UNKNOWN = '#D5DAD8';

// 긴 단어를 먼저 둔다. 예: `진회색`을 `회색`으로, `연파랑`을 `파랑`으로
// 잘못 읽지 않게 백엔드와 같은 우선순위를 유지한다.
const COLOR_ALIASES: Array<[string, string[]]> = [
  ['charcoal', ['진회색', '차콜색', '차콜', '숯색']],
  ['olive', ['카키그린', '올리브색', '올리브', '국방색']],
  ['skyblue', ['스카이블루', '하늘색', '하늘빛', '연파랑']],
  ['lavender', ['연보라색', '연보라', '라벤더']],
  ['mustard', ['머스타드색', '머스타드', '겨자색', '겨자']],
  ['orange', ['오렌지색', '오렌지', '주황색', '주황', '귤색']],
  ['yellow', ['샛노란', '노란색', '노랑색', '노란', '노랑', '황색']],
  ['green', ['초록색', '초록', '녹색', '그린', '풀빛', '풀색']],
  ['khaki', ['카키색상', '카키색', '카키']],
  ['mint', ['민트그린', '민트색', '민트']],
  ['teal', ['청록색', '청록', '틸']],
  ['navy', ['진남색', '네이비색', '네이비', '감청색', '남색']],
  ['blue', ['파란색', '파랑색', '파란', '파랑', '블루', '청색']],
  ['purple', ['보라색', '자주빛', '자주색', '보라', '퍼플']],
  ['pink', ['연분홍', '분홍색', '핑크색', '분홍', '핑크']],
  ['peach', ['살구색', '살구빛', '피치색', '피치']],
  ['brown', ['브라운', '고동색', '갈색', '고동', '흙색', '밤색']],
  ['camel', ['카멜색', '낙타색', '카멜']],
  ['beige', ['베이지색', '베이지']],
  ['ivory', ['아이보리', '크림색', '크림', '미색']],
  ['wine', ['버건디', '와인색', '자두색', '와인']],
  ['black', ['검정색', '검은색', '까만색', '검정', '검은', '까만', '블랙', '흑색']],
  ['white', ['하얀색', '하양색', '화이트', '하얀', '하양', '흰색', '백색', '흰']],
  ['gray', ['그레이', '회색', '쥐색', '잿빛', '재색']],
  ['gold', ['골드', '금색', '금빛']],
  ['silver', ['실버', '은색', '은빛']],
  ['red', ['새빨간', '빨간색', '빨강색', '다홍색', '진홍색', '빨간', '빨강', '다홍', '진홍', '레드']],
];

function colorTag(value?: string): string | undefined {
  if (!value) return undefined;
  const normalized = value.trim().toLowerCase();
  if (HEX[normalized]) return normalized;
  for (const [tag, aliases] of COLOR_ALIASES) {
    if (aliases.some((alias) => normalized.includes(alias))) return tag;
  }
  return undefined;
}

function resolveGarment(tag: string | undefined, description: string | undefined) {
  const resolvedTag = colorTag(tag) ?? colorTag(description);
  return { color: resolvedTag ? HEX[resolvedTag] : UNKNOWN, known: Boolean(resolvedTag) };
}

function parseHeightScale(text: string): number {
  const match = text.match(/(1[3-9]\d)\s*(?:cm|센티|센티미터)/i);
  if (!match) return 1;
  const height = Number(match[1]);
  if (height <= 154) return 0.94;
  if (height >= 176) return 1.04;
  return 1;
}

function parseBuild(text: string): AvatarBuild {
  if (/(마른|왜소|슬림|호리호리)/.test(text)) return 'slim';
  if (/(통통|뚱뚱|건장|체격이\s*큰|큰\s*체격)/.test(text)) return 'broad';
  return 'regular';
}

function parseAccessories(text: string): AvatarAccessory[] {
  const values: AvatarAccessory[] = [];
  if (/(모자|캡|비니)/.test(text)) values.push('hat');
  if (/(안경|선글라스)/.test(text)) values.push('glasses');
  if (/(가방|백팩|배낭|크로스백)/.test(text)) values.push('bag');
  if (/(지팡이|보행봉)/.test(text)) values.push('cane');
  return values;
}

/**
 * 서버 색 태그를 우선하고, 이전 사건처럼 태그가 비어 있으면 보호자가 입력한
 * `상의 → 하의 → 신발 → 키/체형/소지품` 원문에서 보완한다.
 */
export function appearanceAvatarProfile(
  colors?: AppearanceColors,
  appearance: string[] = [],
): AppearanceAvatarProfile {
  const top = resolveGarment(colors?.top, appearance[0]);
  const bottom = resolveGarment(colors?.bottom, appearance[1]);
  const shoes = resolveGarment(colors?.shoes, appearance[2]);
  const extra = appearance.slice(3).join(' ');

  return {
    top: top.color,
    bottom: bottom.color,
    shoes: shoes.color,
    topKnown: top.known,
    bottomKnown: bottom.known,
    shoesKnown: shoes.known,
    build: parseBuild(extra),
    heightScale: parseHeightScale(extra),
    accessories: parseAccessories(extra),
  };
}
