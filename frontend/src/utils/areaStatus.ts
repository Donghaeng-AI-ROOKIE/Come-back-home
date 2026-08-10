/**
 * "내가 예측 구역 안인가 / 얼마나 유력한 곳인가" — 시민 화면의 위치 표현.
 *
 * ## 왜 거리(m·분)를 버렸나 (2026-08-05 확정)
 * 예전에는 "약 300m · 걸어서 5분"을 보여줬는데, 그 거리는 **최종 목격지까지**였다.
 * 예측 결과가 아니라 확정 사실 하나까지의 거리라 정직하긴 했지만, 시민이 알아야
 * 할 것과 어긋난다 — 실종자는 그 점에 있지 않고 확률분포로 퍼져 있다.
 *
 * 그렇다고 "예측까지 몇 m"로 바꿀 수도 없다. **확률분포에는 점이 없다.**
 * 거리를 재려면 중심·최근접·최고확률 중 하나를 골라야 하는데 셋이 서로 다른
 * 질문에 답하고, 분포가 두 갈래면 중심은 아무도 없는 지점이 된다. 게다가 제보로
 * 재예측될 때마다 숫자가 튄다.
 *
 * 그래서 분포에 대해 **정직하게 말할 수 있는 것**만 말한다:
 *   - 내가 예측 구역 **안인가 밖인가**
 *   - 안이라면 그 칸이 **얼마나 유력한가**(고/중/저 등급)
 * 둘 다 재예측에 튀지 않고, 지도 히트맵 색과 그대로 일치한다.
 */
import type { PoaTier } from '../types/domain';
import { TIER_LABEL, TIER_RANGE, tierForProb } from '../theme/poa';

export type AreaStatus = {
  /** 판정이 됐는가. false 면 위치나 예측을 못 받은 것. */
  known: boolean;
  /** 예측 셀 안에 있는가. */
  inArea: boolean;
  /** 셀 안일 때의 발견확률 등급. */
  tier: PoaTier | null;
  /** 아주 짧은 표기 — 칩처럼 좁은 자리용. 판정 불가면 빈 문자열. */
  short: string;
  /** 배지 표기 — 확률 등급까지 포함. 판정 불가면 빈 문자열. */
  badge: string;
  /** 문장 표기 — 카드·낭독용. */
  label: string;
};

/**
 * @param cellProb `cellProbAt()` 결과.
 *   `null` = 판정 불가(위치 모름·예측 미도착) / `0` = 예측 셀 밖 / `>0` = 셀 안.
 */
export function describeArea(cellProb: number | null): AreaStatus {
  if (cellProb === null) {
    return {
      known: false,
      inArea: false,
      tier: null,
      short: '',
      badge: '',
      // 모르는 걸 아는 척하지 않는다 — 숫자를 지어내느니 못 말한다고 한다.
      label: '위치를 확인할 수 없어 예측 구역인지 알려드리지 못해요',
    };
  }
  if (cellProb <= 0) {
    return {
      known: true,
      inArea: false,
      tier: null,
      short: '예측 구역 밖',
      badge: '예측 구역 밖',
      label: '내 위치는 예측 구역 밖이에요',
    };
  }
  const tier = tierForProb(cellProb);
  return {
    known: true,
    inArea: true,
    tier,
    short: '예측 구역 안',
    badge: `예측 구역 안 · 발견확률 ${TIER_LABEL[tier]} (${TIER_RANGE[tier]})`,
    label: `내 위치가 예측 구역 안이에요 · 발견확률 ${TIER_LABEL[tier]} (${TIER_RANGE[tier]})`,
  };
}
