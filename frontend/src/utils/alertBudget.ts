/**
 * 알림 피로도 예산 (알림 개인화 #8) — **판정 규칙**.
 *
 * 한 문장: **알림을 눌러보는 사람에겐 넓게, 꺼버리는 사람에겐 중요한 것만.**
 *
 * ## 🚨 예산이 건드리지 않는 것: 진입 관문
 * 앱을 직접 열었는데 주변에 사건이 있다면, 참여도가 아무리 낮아도 첫 화면은
 * 경보 화면이다. 참여도는 **과거 다른 사건들에 대한 반응**이라 그걸로 지금 이
 * 사건을 감추면 알림 차단이 된다.
 *
 * 예산이 조절하는 건 둘뿐이다:
 *   1) **푸시를 보낼 확률 문턱** (meetsAlertThreshold) — 폰이 울리느냐
 *   2) "그만 볼래요"로 끈 사건이 얼마나 쉽게 돌아오는가 (rearmsAfterDismissal)
 *
 * ## 신호는 폰에만 있다
 * 열람·제보 이력은 서버로 올리지 않는다 — 올리는 순간 "익명 제보" 약속이 깨지고,
 * 서버가 시민 개개인의 관심사를 알게 된다. 그래서 **판정도 폰이 한다.**
 * 서버가 아는 것은 자기가 몇 건 보냈는지뿐이다(그건 추가 수집이 0이라 별개 축).
 *
 * ## 🚨 골든타임 알림은 어떤 등급에서도 면제
 * `reflex`(D1, 신고 직후 안전반경)는 피로도로 절대 묻히지 않는다. 피로도 관리는
 * "덜 중요한 걸 줄이는" 장치이지 "진짜 급한 걸 놓치는" 장치가 아니다.
 * 이 규칙이 깨지면 기능 전체가 해로워지므로 테스트로 고정한다.
 *
 * ## 검증 불가와 악용
 * 폰이 스스로 매기는 점수라 서버가 검증할 수 없다. 다만 조작해서 얻는 게
 * "알림을 더 받는 것"뿐이라 악용 인센티브가 없다.
 */
import type { AlertKind } from '../types/domain';

export type EngagementLevel = 'high' | 'normal' | 'low';

/** 참여 신호 누적치. 전부 기기 안에만 존재한다. */
export type EngagementSignals = {
  /** 자발적으로 경보를 열어본 횟수(벨·알림 탭). 관문에 강제로 떠서 본 건 세지 않는다. */
  opened: number;
  /** 제보를 실제로 보낸 횟수 — 가장 강한 관심 신호. */
  reported: number;
  /** "그만 볼래요"를 누른 횟수 — 피로 신호. */
  dismissed: number;
};

export const EMPTY_SIGNALS: EngagementSignals = { opened: 0, reported: 0, dismissed: 0 };

/**
 * 가중치. 제보가 열람보다 세 배 무거운 이유는 **비용이 다르기 때문**이다 —
 * 여는 건 궁금해서일 수 있지만 제보는 시간을 들여 참여한 것이다.
 * "그만 볼래요"는 명시적 거부라 열람보다 무겁게 센다.
 */
const W_OPENED = 1;
const W_REPORTED = 3;
const W_DISMISSED = -2;

/** 이 점수 이상이면 high. 제보 1건 또는 열람 3회. */
const HIGH_AT = 3;
/**
 * 이 점수 이하면 low.
 *
 * "그만 볼래요" **두 번**부터다(-2 × 2 = -4). 한 번은 피로가 아니라 "그 사건이
 * 나와 무관했다"일 수 있어서, 한 번으로 알림을 줄이면 오히려 놓친다.
 * (-2 로 잡으면 한 번에 걸린다 — 실제로 그렇게 돼 있던 것을 테스트가 잡았다.)
 */
const LOW_AT = -3;

export function engagementScore(s: EngagementSignals): number {
  return s.opened * W_OPENED + s.reported * W_REPORTED + s.dismissed * W_DISMISSED;
}

export function engagementLevel(s: EngagementSignals): EngagementLevel {
  const score = engagementScore(s);
  if (score >= HIGH_AT) return 'high';
  if (score <= LOW_AT) return 'low';
  return 'normal';
}

/**
 * 등급별 **알림 발송 확률 문턱** — 예산의 본체.
 *
 * 잘 확인하는 사람에겐 확신이 덜한 지역에서도 알리고, 잘 안 보는 사람에겐
 * 확실한 지역일 때만 알린다. 같은 장소·같은 사건이라도 사람에 따라
 * 알림이 가고 안 가고가 갈린다.
 *
 * ## 이 숫자는 **화면에 보이는 발견확률**이다 (2026-08-05 확정)
 * 백엔드 POA 원값은 전체 셀 합이 1이라 실측 최고 셀이 **18%**뿐이다 — 그 스케일로
 * 0.3/0.6 을 잡으면 **아무에게도 알림이 안 간다**(30% 이상 셀 0개).
 *
 * 더 큰 문제는 원값이 **구역이 넓어질수록 전부 낮아진다**는 것이다. 경과 6시간이면
 * 수백 셀로 퍼져 최고 셀도 5% 아래로 떨어지고, 고정 문턱은 그때부터 아무도 통과
 * 못 한다 — 시간이 갈수록 더 많은 눈이 필요한데 알림이 저절로 꺼지는 셈이다.
 *
 * 그래서 **최고 셀 대비 상대값**(프론트가 히트맵·범례에 쓰는 그 값)을 기준으로 한다.
 * 범례가 고 70%+ / 중 40~70% / 저 20~40% 이므로 아래 문턱은 각각 "저 상단"과
 * "중 상단"에 해당하고, **사용자가 지도에서 보는 색과 알림 여부가 일치한다.**
 */
export const PROB_THRESHOLD: Record<EngagementLevel, number> = {
  high: 0.3,   // 저~중 경계 — 덜 확실한 곳까지
  normal: 0.45,
  low: 0.6,    // 중 상단 — 확실한 곳만
};

/**
 * 내가 있는 셀의 발견확률이 내 문턱을 넘는가 = **이 알림을 나에게 보낼 것인가.**
 *
 * ## 🚨 이건 **푸시 발송** 판정이지 진입 관문 판정이 아니다 (2026-08-05 확정)
 * 관문은 사용자가 **직접 앱을 연** 순간의 이야기라, 대상 구역 안에 사건이 있으면
 * 확률과 무관하게 보여준다 — 확률이 낮다고 "당신 주변에 실종자가 있다"는 사실을
 * 숨길 이유가 없다. 이 함수가 가르는 건 **폰이 울리느냐**다.
 *
 * @param cellProb 내 위치가 속한 셀의 표시 확률.
 *   `null` = 판정 불가(위치 모름·POA 미도착) → **fail-open**. 골든타임에서
 *   놓친 알림의 비용이 성가신 알림보다 크다는 기존 원칙과 같다.
 *   `0` = 예측 셀 밖(판정은 됐고 확률이 최저) → 문턱 미달.
 *
 * 🚨 `reflex`(D1 골든타임)는 문턱 자체를 면제한다 — POA 가 나오기 **전**에
 * 나가는 알림이라 확률이라는 게 아직 없고, 이건 피로도로 줄일 대상이 아니다.
 */
export function meetsAlertThreshold(
  cellProb: number | null,
  kind: AlertKind,
  level: EngagementLevel,
): boolean {
  if (kind === 'reflex') return true;
  if (cellProb === null) return true;
  return cellProb >= PROB_THRESHOLD[level];
}

/**
 * 이 등급에서 **관문을 세울 만한** 알림 종류인가 → **항상 true.**
 *
 * 🚨 **참여도로 관문을 막지 않는다.** 내 주변에 실종자가 있는 한, 아직 아무 의사도
 * 밝히지 않은 경보라면 앱의 첫 화면은 무조건 경보 화면이다(2026-08-05 확정).
 *
 * 한때 low 등급에서 poa 를 걸러냈는데 그건 틀렸다. 참여도는 **과거 다른 사건들에
 * 대한 반응**이고, 그걸로 **지금 이 사건**을 감추면 피로도 관리가 아니라 알림
 * 차단이 된다. 알림을 꺼도 되는 유일한 근거는 그 사건에 대한 **명시적 의사표시**
 * ("그만 볼래요")뿐이고, 그건 rearmsAfterDismissal 이 다룬다.
 *
 * 함수를 남겨두는 이유: 판정 지점이 사라지면 나중에 누군가 같은 실수를 다시 하기
 * 쉽다. 여기서 "항상 true"라고 못박고 테스트로 고정한다.
 */
export function isWorthGating(_kind: AlertKind, _level: EngagementLevel): boolean {
  return true;
}

/**
 * "그만 볼래요" **이후** 발령된 이 종류가 억제를 뚫고 다시 관문을 세우는가.
 *
 * 등급이 올라갈수록 더 많은 종류가 억제를 뚫는다:
 *   low    reflex 만           — 껐다는 의사를 최대한 존중
 *   normal reflex, new_region  — 기본값(기존 동작)
 *   high   전부                — 관심이 많으니 새 소식은 계속 보여준다
 */
export function rearmsAfterDismissal(kind: AlertKind, level: EngagementLevel): boolean {
  if (kind === 'reflex') return true; // 면제
  if (level === 'high') return true;
  if (level === 'low') return false;
  return kind === 'new_region';
}
