/**
 * "내가 예측 구역 안인가" 배선 — 판정 규칙은 utils/areaStatus.ts.
 *
 * 위치와 예측을 각각 훅으로 받아 셀을 찾는다. 두 훅 모두 공유 캐시(단일 GPS
 * 구독 · react-query)라 화면마다 불러도 추가 요청이 생기지 않는다.
 */
import { usePoaPrediction } from './queries';
import { useMyLocation } from './useMyLocation';
import { useDebugStore } from '../store/debugStore';
import { cellProbAt } from '../utils/alertGate';
import { describeArea } from '../utils/areaStatus';
import type { AreaStatus } from '../utils/areaStatus';

export function useAreaStatus(caseId: string): AreaStatus {
  const { point } = useMyLocation();
  const poa = usePoaPrediction(caseId, 1);
  // 시연·검증용 강제값(기본 null). 정릉동 예측 셀 밖에서도 "구역 안" 표기를
  // 확인할 수 있어야 해서 둔다 — forceInAlertArea 가 지오펜스만 건너뛰는 것과 짝.
  const forceCellProb = useDebugStore((s) => s.forceCellProb);
  const real = cellProbAt(point, poa.data);
  return describeArea(forceCellProb != null ? forceCellProb : real);
}

export default useAreaStatus;
