/** 서버 동기화 훅 (TanStack Query v5) + 파생 골든타임 (spec §2.4). */
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getPoaPrediction } from '../api/client';
import { getActiveWalk, getWalkStats, endWalk, startWalk } from '../api/walk';
import { getCase, runPrediction } from '../api/guardian';
import { useAppModeStore } from '../store/appModeStore';
import type { TimeAxis } from '../types/domain';

// ── 수색 ──────────────────────────────────────────────────────────
export function usePoaPrediction(caseId: string, t: TimeAxis) {
  return useQuery({
    queryKey: ['poa', caseId, t],
    queryFn: () => getPoaPrediction(caseId, t),
    enabled: !!caseId,
  });
}

export function useCase(caseId: string) {
  return useQuery({ queryKey: ['case', caseId], queryFn: () => getCase(caseId), enabled: !!caseId });
}

/**
 * 예측 실행. 10초 안팎 걸리므로 화면은 반드시 진행 표시를 띄운다.
 * 성공하면 POA 캐시를 버려 다음 조회가 새 예측을 읽게 한다.
 */
export function useRunPrediction(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => runPrediction(caseId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['poa', caseId] }),
  });
}

// ── 산책 ──────────────────────────────────────────────────────────
export function useWalkStats() {
  return useQuery({ queryKey: ['walkStats'], queryFn: () => getWalkStats() });
}

/** 앱 재시작 시 진행 중이던 산책 복원 (없으면 null). */
export function useActiveWalk() {
  return useQuery({ queryKey: ['activeWalk'], queryFn: () => getActiveWalk() });
}

export function useStartWalk() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (areaLabel?: string) => startWalk(areaLabel ?? ''),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['activeWalk'] }),
  });
}

export function useEndWalk() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { sessionId: string; distanceKm: number; durationMin: number }) =>
      endWalk(v.sessionId, v.distanceKm, v.durationMin),
    onSuccess: () => {
      // 종료하면 누적·레벨·배지가 전부 바뀐다 — 둘 다 무효화한다.
      qc.invalidateQueries({ queryKey: ['walkStats'] });
      qc.invalidateQueries({ queryKey: ['activeWalk'] });
    },
  });
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
