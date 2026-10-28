/**
 * 접수 네 번째 칸('키/체형/소지품')의 자유 서술을 **표시용 조각**으로 나눈다.
 *
 * 보호자는 이 칸에 "160/50/검정 핸드백"처럼 숫자만 적기도 한다. 그대로 보여 주면
 * 시민 화면에 `160/50/검정 핸드백` 칩이 떠서 어느 숫자가 키이고 몸무게인지 알 수
 * 없었다(10/27 운영 사건 7ccf1a190cd3). 표시 단계에서만 나누고 이름을 붙인다 —
 * 저장된 신고 원문과 서버 응답은 그대로다.
 *
 * - 숫자만 있는 조각: 아직 키가 없고 100~230 이면 키(cm), 아직 몸무게가 없고
 *   25~200 이면 몸무게(kg). 그 밖이면 무엇인지 모르므로 원문 그대로 둔다.
 * - 단위·이름이 붙은 조각("160cm", "50키로", "키 165", "몸무게 50")은 같은
 *   표기(`키 160cm`, `몸무게 50kg`)로 맞춘다. 범위 밖이거나 이름과 단위가
 *   어긋나면("키 50kg") 원문 그대로 둔다.
 * - 나머지 글자 조각("검정 핸드백", "마른 체형")은 그대로 둔다.
 *
 * node 테스트(scripts/body-notes.test.mjs)가 이 파일을 직접 읽으므로 다른 모듈을
 * import 하지 않는다.
 */

type Measure = 'height' | 'weight';

const SEPARATORS = /[/,，·\n]+/;
const RANGE: Record<Measure, [number, number]> = { height: [100, 230], weight: [25, 200] };
const BARE = /^(약\s*)?(\d{2,3}(?:\.\d+)?)\s*(정도|쯤)?$/;
// 이름(키·몸무게) 또는 단위(cm·kg) 중 하나는 있어야 측정값으로 읽는다. 둘 다 없는
// 숫자("60대")는 아래 replace 콜백이 그대로 돌려준다.
const MEASURE = /(?:(키|몸무게|체중)\s*(?:은|는|이|가)?\s*)?(약\s*)?(\d{2,3}(?:\.\d+)?)(?!\d)\s*(센티미터|센티|센치|cm|㎝|킬로그램|키로그램|킬로|키로|kg|㎏)?(\s*(?:정도|쯤))?/gi;

function measureOf(label: string | undefined, unit: string | undefined): Measure | null {
  const byLabel: Measure | null = label ? (label === '키' ? 'height' : 'weight') : null;
  const byUnit: Measure | null = unit ? (/센|cm|㎝/i.test(unit) ? 'height' : 'weight') : null;
  if (byLabel && byUnit && byLabel !== byUnit) return null;
  return byLabel ?? byUnit;
}

function inRange(kind: Measure, value: string): boolean {
  const n = Number(value);
  const [min, max] = RANGE[kind];
  return n >= min && n <= max;
}

function format(kind: Measure, value: string, approx: boolean): string {
  const about = approx ? '약 ' : '';
  return kind === 'height' ? `키 ${about}${value}cm` : `몸무게 ${about}${value}kg`;
}

export function bodyNotes(text: string | null | undefined): string[] {
  const seen: Record<Measure, boolean> = { height: false, weight: false };
  const out: string[] = [];
  for (const raw of String(text ?? '').split(SEPARATORS)) {
    const piece = raw.trim();
    if (!piece) continue;

    const bare = piece.match(BARE);
    if (bare) {
      const kind = (['height', 'weight'] as const).find((k) => !seen[k] && inRange(k, bare[2]));
      if (kind) {
        seen[kind] = true;
        out.push(format(kind, bare[2], Boolean(bare[1] || bare[3])));
      } else {
        out.push(piece);
      }
      continue;
    }

    const found: string[] = [];
    const rest = piece.replace(MEASURE, (match, label, pre, value, unit, post) => {
      const kind = measureOf(label, unit);
      if (!kind || !inRange(kind, value)) return match;
      seen[kind] = true;
      found.push(format(kind, value, Boolean(pre || post)));
      return ' ';
    }).replace(/\s+/g, ' ').trim();
    out.push(...found);
    if (rest) out.push(rest);
  }
  return out;
}

// 옷 이름이 든 조각은 옷 설명이다. 거기 붙은 숫자는 치수(상의 105, 신발 230)일 수
// 있어 키·몸무게로 읽지 않는다. 낱말은 AppearanceScreen 과 utils/appearanceAvatar 의
// 옷 이름을 합친 것이다.
const GARMENT = /상의|하의|옷|티|셔츠|점퍼|재킷|자켓|가디건|코트|후드|니트|맨투맨|바람막이|외투|조끼|블라우스|원피스|바지|슬랙스|치마|스커트|레깅스|트레이닝복|신발|운동화|구두|샌들|슬리퍼|부츠/;

/**
 * 경보의 인상착의 배열 → 시민 화면 칩.
 *
 * 서버는 `[상의, 하의, 신발, 키/체형/소지품]`에서 빈 칸을 뺀 배열을 보내고, 구조화
 * 인상착의가 없으면 요약 한 문장을 보낸다. 그래서 몇 번째가 어느 칸인지 알 수 없다.
 * 쉼표로 나눈 뒤 옷 이름이 든 조각은 그대로 두고, 나머지만 `bodyNotes` 로 나눈다.
 */
export function appearanceTags(values: string[]): string[] {
  const pieces = values.flatMap((value) => value.split(/[,，\n]+/)).map((value) => value.trim()).filter(Boolean);
  const clothing = pieces.filter((value) => GARMENT.test(value));
  const notes = pieces.filter((value) => !GARMENT.test(value));
  return [...clothing, ...bodyNotes(notes.join(','))];
}

/**
 * 경보 요약 한 줄 → 긴급 알림 목록 카드·잠금화면 문구.
 *
 * 서버 `summary` 는 인상착의 칸을 쉼표로 이은 원문("회색 점퍼, 검은 바지, 흰 운동화,
 * 160/50/검정 핸드백")이라, 칩만 고치면 목록 카드에는 `160/50` 이 그대로 남았다
 * (10/28 12회차 C2). 칩과 같은 규칙으로 나눈 뒤 쉼표로 다시 잇는다.
 */
export function appearanceLine(summary: string): string {
  return appearanceTags([summary]).join(', ');
}
