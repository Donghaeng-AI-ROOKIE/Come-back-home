/**
 * 클라이언트 H3 판정. 실제 등록·조회에는 서버 targeting-policy의
 * res7/8/9 를 명시해서 사용한다. 현재 셀만 보내고 좌표·이동 이력은 보내지 않는다.
 * res9 는 기존 res7 보다 작은 위치 구역을 나타낸다.
 */
import { cellToParent, latLngToCell } from 'h3-js';

import type { GeoPoint } from '../types/domain';

/** 이전 클라이언트와 mock 전용 기본값. 실제 연결은 서버 정책 해상도를 명시한다. */
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
 * mock 전용 논리 부모 셀 근사. 실제 서버 대상은 지리적 교차 영역을 덮으므로
 * 이 결과를 실서비스 발송 대상으로 사용하지 않는다.
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
