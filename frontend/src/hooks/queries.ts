/** 서버 동기화 훅 (TanStack Query v5) + 파생 골든타임 (spec §2.4). */
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getActiveAlerts,
  getCrossValidation,
  getFoundSummary,
  getPoaPrediction,
  getValidation,
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
