/**
 * H3 셀 계산 — 푸시 타겟팅의 폰 쪽 절반 (2026-08-05 확정).
 *
 * ## 왜 폰이 셀을 계산하나
 * 푸시를 받으려면 서버가 "누구에게 보낼지"를 알아야 하는데, 그렇다고 좌표를 보낼
 * 수는 없다. 그래서 **폰이 자기 좌표를 res7 셀 하나로 바꿔서** 그것만 보낸다.
 * 정밀 좌표는 기기를 떠난 적이 없고, 서버는 "어느 동네 칸"까지만 안다 —
 * 서버를 믿을 필요가 없는 구조라는 게 핵심이다(반올림을 누가 하느냐의 차이).
 *
 * ## 왜 res7 인가
 * 백엔드 예측 격자는 res9(≈0.1km²)인데, 그 단위로 위치를 받으면 사실상 좌표다.
 * res7(≈5km²)이면 예측 구역(실측 17km²)을 구분하기에 충분하면서 개인 위치는
 * 안 드러난다 — 목적에 필요한 **최소** 해상도.
 *
 * ## 근사가 아니다
 * 한때 대상 구역을 중심+반경 원으로 근사했는데, 육각 셀 집합보다 넓어 구역 밖
 * 사람이 섞였다. 그건 "폰에 H3 가 없다"는 **틀린 전제**에서 나온 우회책이었고
 * (h3-js 는 그냥 npm 패키지다), 지금은 서버·폰이 같은 셀 id 를 비교한다.
 */
import { cellToParent, latLngToCell } from 'h3-js';

import type { GeoPoint } from '../types/domain';

/** 푸시 타겟팅 해상도. 백엔드 `settings.push_target_res` 와 **같아야 한다.** */
export const PUSH_TARGET_RES = 7;

/** 내 위치의 셀. 위치를 모르면 null — 서버에 "위치 없음"으로 알린다. */
export function cellOf(point: GeoPoint | null, res: number = PUSH_TARGET_RES): string | null {
  if (point == null) return null;
  if (!Number.isFinite(point.lat) || !Number.isFinite(point.lng)) return null;
  try {
    return latLngToCell(point.lat, point.lng, res);
  } catch {
    // 좌표가 범위를 벗어난 경우 등. 위치를 못 구한 것과 같게 다룬다.
    return null;
  }
}

/**
 * 내가 대상 셀 집합 안에 있는가 — 앱 안 관문의 지오펜스 판정.
 *
 * 서버가 보낸 셀의 해상도를 그대로 따라간다(payload 의 `target_res`). 해상도를
 * 여기 고정해두면 서버가 나중에 res6/res8 로 바꿨을 때 판정이 조용히 전부
 * false 가 된다 — 알림이 오는데 앱은 "구역 밖"이라고 하는 최악의 어긋남.
 */
export function isInCells(
  point: GeoPoint | null,
  cells: readonly string[],
  res: number = PUSH_TARGET_RES,
): boolean {
  const mine = cellOf(point, res);
  return mine != null && cells.includes(mine);
}

/**
 * 예측 셀(res9) 목록 → 대상 res7 부모 집합. 서버 `alerts.target_parent_cells()` 와
 * 같은 계산으로, 아직 푸시 페이로드가 없는 목 경보에서 대상 구역을 만드는 데 쓴다.
 */
export function parentCells(cells: readonly string[], res: number = PUSH_TARGET_RES): string[] {
  const out = new Set<string>();
  for (const cell of cells) {
    try {
      out.add(cellToParent(cell, res));
    } catch {
      /* 형식이 깨진 셀 id — 조용히 건너뛴다 */
    }
  }
  return [...out].sort();
}
