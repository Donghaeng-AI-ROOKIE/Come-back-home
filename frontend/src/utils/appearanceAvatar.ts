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
  ['blue', ['파란색', '파랑색', '파란', '파랑', '블루', '청색', '청바지', '데님']],
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

type AppearanceDescriptions = {
  top?: string;
  bottom?: string;
  shoes?: string;
  extra: string;
};

/**
 * \uC637 \uC774\uB984\uC73C\uB85C \uBD80\uC704\uB97C \uAC00\uB978\uB2E4 \u2014 **\uBC30\uC5F4 \uC704\uCE58\uB85C \uAC00\uB974\uC9C0 \uC54A\uB294\uB2E4.**
 *
 * \uC811\uC218 \uD654\uBA74\uC740 \uC0C1\uC758\u00B7\uD558\uC758\u00B7\uC2E0\uBC1C\u00B7\uBD80\uAC00\uC815\uBCF4\uB97C \uAC01\uAC01 \uB2E4\uB978 \uCE78\uC73C\uB85C \uBC1B\uC73C\uBBC0\uB85C \uBD80\uC704\uB294 \uC560\uCD08\uC5D0
 * \uD655\uC815\uB3FC \uC788\uACE0, \uADF8 \uD655\uC815\uAC12\uC740 `appearance_colors` \uD0DC\uADF8\uB85C \uC628\uB2E4. \uC5EC\uAE30 \uC624\uB294
 * `appearance` \uBC30\uC5F4\uC740 **\uD45C\uC2DC\uC6A9 \uBAA9\uB85D**\uC774\uB77C \uBD80\uC704 \uC815\uBCF4\uAC00 \uC5C6\uB2E4 \u2014 \uBC31\uC5D4\uB4DC\uAC00 \uBE48 \uCE78\uC744
 * \uAC78\uB7EC \uB0B4\uAE30 \uB54C\uBB38\uC774\uB2E4(phase3/alerts.py: `if x and x.strip()`, \uBE48 \uCE69\uC774 \uB728\uB358 \uBB38\uC81C\uB97C
 * \uACE0\uCE58\uBA74\uC11C \uC0DD\uAE34 \uB3D9\uC791).
 *
 * \uADF8\uB798\uC11C `appearance[0]` \uC774 \uC0C1\uC758\uB77C\uB294 \uBCF4\uC7A5\uC774 \uC5C6\uB2E4. \uBCF4\uD638\uC790\uAC00 \uC0C1\uC758\uB97C \uBE44\uC6B0\uBA74
 * \uBC30\uC5F4\uC774 \uD55C \uCE78\uC529 \uBC00\uB824 `["\uCCAD\uBC14\uC9C0", "\uAC80\uC740 \uC6B4\uB3D9\uD654"]` \uAC00 \uB418\uACE0, \uC704\uCE58\uB85C \uC77D\uC73C\uBA74
 * **\uC0C1\uC758\uAC00 \uD30C\uB797\uAC8C \uCE60\uD574\uC9C4\uB2E4**(\uC2E4\uCE21 08-12). \uC218\uC0C9 \uD654\uBA74\uC5D0\uC11C \uC637 \uC0C9\uC774 \uD2C0\uB9AC\uB294 \uAC74
 * \uADF8\uB0E5 \uD2C0\uB9B0 \uC815\uBCF4\uB77C, \uBAA8\uB974\uB294 \uCC44\uB85C \uB450\uB294 \uD3B8\uC774 \uB0AB\uB2E4.
 *
 * \uADF8\uB798\uC11C \uC637 \uC774\uB984\uC774 \uD655\uC778\uB41C \uD56D\uBAA9\uB9CC \uC4F0\uACE0, \uBABB \uCC3E\uC73C\uBA74 \uBE44\uC6CC \uB454\uB2E4(\uC911\uB9BD \uD68C\uC0C9).
 * \uD55C \uD56D\uBAA9\uC774 \uB450 \uBD80\uC704\uC5D0 \uAC78\uB9AC\uBA74 \uBA3C\uC800 \uC7A1\uC740 \uCABD\uB9CC \uC4F4\uB2E4 \u2014 \uAC19\uC740 \uBB38\uC7A5\uC744 \uC0C1\u00B7\uD558\uC758\uC5D0
 * \uBAA8\uB450 \uB123\uC73C\uBA74 \uC591\uCABD\uC774 \uAC19\uC740 \uC0C9\uC774 \uB41C\uB2E4.
 */
const TOP_GARMENT = /\uC0C1\uC758|\uC637|\uD2F0|\uC154\uCE20|\uC810\uD37C|\uC7AC\uD0B7|\uC790\uCF13|\uAC00\uB514\uAC74|\uCF54\uD2B8|\uD6C4\uB4DC|\uB2C8\uD2B8|\uB9E8\uD22C\uB9E8|\uBC14\uB78C\uB9C9\uC774|\uC678\uD22C|\uC870\uB07C|\uBE14\uB77C\uC6B0\uC2A4|\uC6D0\uD53C\uC2A4/;
const BOTTOM_GARMENT = /\uD558\uC758|\uBC14\uC9C0|\uCCAD\uBC14\uC9C0|\uBA74\uBC14\uC9C0|\uC2AC\uB799\uC2A4|\uCE58\uB9C8|\uB808\uAE45\uC2A4|\uBC18\uBC14\uC9C0|\uD2B8\uB808\uC774\uB2DD\uBCF5/;
const SHOE_GARMENT = /\uC2E0\uBC1C|\uC6B4\uB3D9\uD654|\uAD6C\uB450|\uC0CC\uB4E4|\uC2AC\uB9AC\uD37C|\uBD80\uCE20/;

function descriptionsFromAppearance(appearance: string[]): AppearanceDescriptions {
  const values = appearance.map((value) => value.trim()).filter(Boolean);
  const parts = values.flatMap((value) => value.split(/[\n,/|\u00B7]+/).map((part) => part.trim()).filter(Boolean));

  const used = new Set<string>();
  const take = (pattern: RegExp): string | undefined => {
    const hit = parts.find((part) => !used.has(part) && pattern.test(part));
    if (hit) used.add(hit);
    return hit;
  };
  const top = take(TOP_GARMENT);
  const bottom = take(BOTTOM_GARMENT);
  const shoes = take(SHOE_GARMENT);

  // \uB0A8\uC740 \uD56D\uBAA9\uC740 \uD0A4\u00B7\uCCB4\uD615\u00B7\uC18C\uC9C0\uD488 \uD6C4\uBCF4. \uC0C9 \uD310\uC815\uACFC \uACB9\uCE58\uC9C0 \uC54A\uC73C\uBBC0\uB85C(\uC22B\uC790 cm, \uB9C8\uB978/\uD1B5\uD1B5,
  // \uBAA8\uC790\u00B7\uC548\uACBD\u00B7\uAC00\uBC29\u00B7\uC9C0\uD321\uC774) \uC804\uBD80 \uB118\uACA8\uB3C4 \uC548\uC804\uD558\uB2E4 \u2014 \uBD80\uAC00\uC815\uBCF4\uAC00 4\uBC88\uC9F8 \uCE78\uC5D0 \uC628\uB2E4\uB294
  // \uAC00\uC815\uB3C4 \uBC30\uC5F4\uC774 \uBC00\uB9AC\uBA74 \uAE68\uC9C0\uBBC0\uB85C \uC704\uCE58\uB85C \uC790\uB974\uC9C0 \uC54A\uB294\uB2E4.
  const extra = parts.filter((part) => !used.has(part)).join(' ');

  return { top, bottom, shoes, extra };
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
  const descriptions = descriptionsFromAppearance(appearance);
  const top = resolveGarment(colors?.top, descriptions.top);
  const bottom = resolveGarment(colors?.bottom, descriptions.bottom);
  const shoes = resolveGarment(colors?.shoes, descriptions.shoes);
  const extra = descriptions.extra;

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
