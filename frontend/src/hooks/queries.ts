/** 서버 동기화 훅 (TanStack Query v5) + 파생 골든타임 (spec §2.4). */
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getActiveAlerts,
  getCrossValidation,
  getFoundSummary,
  getPoaPrediction,
  getValidation,
  touchPresence,
} from '../api/client';
import { useAppModeStore } from '../store/appModeStore';
import type { TimeAxis } from '../types/domain';

export function useActiveAlerts() {
  return useQuery({ queryKey: ['alerts'], queryFn: getActiveAlerts });
}

export function usePoaPrediction(caseId: string, t: TimeAxis) {
  return useQuery({
    queryKey: ['poa', caseId, t],
    queryFn: () => getPoaPrediction(caseId, t),
    enabled: !!caseId,
  });
}

export function useCrossValidation(caseId: string) {
  return useQuery({
    queryKey: ['crossval', caseId],
    queryFn: () => getCrossValidation(caseId),
    enabled: !!caseId,
  });
}

export function useValidation(caseId: string) {
  return useQuery({ queryKey: ['validation', caseId], queryFn: () => getValidation(caseId), enabled: !!caseId });
}

export function useFoundSummary(caseId: string) {
  return useQuery({ queryKey: ['found', caseId], queryFn: () => getFoundSummary(caseId), enabled: !!caseId });
}

/**
 * 익명 동시 참여자 수 (알림 개인화 #4) — 폴링이 곧 하트비트다.
 *
 * 주기는 서버 TTL(90s)의 1/3 — 한두 번 놓쳐도 내가 참여자 목록에서 사라지지 않는다.
 * refetchIntervalInBackground 는 기본값 false 그대로 둔다: 백그라운드에서까지
 * 폴링하면 화면을 안 보는 사람이 "함께 보고 있는 사람"으로 계속 세어져 거짓말이 된다.
 *
 * retry:false 인 이유 — 이 값은 실패해도 배지 하나가 안 뜨는 게 전부다.
 * 수색 화면의 본질 정보(지도·인상착의)를 재시도 폭풍으로 방해할 가치가 없다.
 */
export const PRESENCE_POLL_MS = 30_000;

export function usePresence(caseId: string, enabled = true) {
  return useQuery({
    queryKey: ['presence', caseId],
    queryFn: () => touchPresence(caseId),
    enabled: enabled && !!caseId,
    refetchInterval: PRESENCE_POLL_MS,
    staleTime: 0,
    retry: false,
  });
}

/**
 * 이 수 미만이면 참여자 수를 표시하지 않는다.
 *
 *  - "1명이 함께 찾고 있어요" = 나 혼자라는 뜻이라 사회적 증거로 역효과.
 *  - 익명 집합의 최소 크기 확보 — 카운트 1은 특정 개인을 가리키는 것과 같아진다.
 */
export const PRESENCE_MIN_VISIBLE = 2;

/**
 * 화면에 **표시할** 참여자 수. 임계 미만이면 null(표시하지 않음).
 *
 * 이 판정이 표시 컴포넌트가 아니라 훅에 있는 이유: 임계값은 디자인이 아니라
 * 정책이다. 컴포넌트 안에 두면 디자인 교체 시 규칙이 조용히 사라진다.
 * 반환 타입이 `number | null` 이라 호출부는 널 검사를 강제당한다.
 */
export function usePresenceCount(caseId: string, enabled = true): number | null {
  const { data } = usePresence(caseId, enabled);
  const watching = data ?? 0;
  return watching >= PRESENCE_MIN_VISIBLE ? watching : null;
}

/** 골든타임 — enteredSearchAt 기준 파생 카운트다운(초는 스토어에 저장 안 함). */
const GOLDEN_WINDOW_MS = 60 * 60 * 1000; // 1시간

export type GoldenTime = { elapsedSec: number; remainingSec: number; label: string; overdue: boolean };

export function useGoldenTime(windowMs = GOLDEN_WINDOW_MS): GoldenTime | null {
  const enteredSearchAt = useAppModeStore((s) => s.enteredSearchAt);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (enteredSearchAt == null) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [enteredSearchAt]);

  if (enteredSearchAt == null) return null;
  const elapsedSec = Math.max(0, Math.floor((now - enteredSearchAt) / 1000));
  const remainingSec = Math.max(0, Math.floor((enteredSearchAt + windowMs - now) / 1000));
  const mm = Math.floor(remainingSec / 60);
  const ss = remainingSec % 60;
  const label = `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
  return { elapsedSec, remainingSec, label, overdue: remainingSec === 0 };
}
