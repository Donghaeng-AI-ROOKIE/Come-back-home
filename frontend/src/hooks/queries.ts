/** 서버 동기화 훅 (TanStack Query v5) + 파생 골든타임 (spec §2.4). */
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getActiveAlerts, getGuidance, getPoaPrediction, touchPresence } from '../api/client';
import { getActiveWalk, getWalkStats, endWalk, startWalk } from '../api/walk';
import { getAreaLabels, getCase, getMyCases, listPersonas, runPrediction } from '../api/guardian';
import { useAppModeStore } from '../store/appModeStore';
import { useDebugStore } from '../store/debugStore';
import { useGuardianCaseStore } from '../store/guardianCaseStore';
import { useMyLocation } from './useMyLocation';
import { LAST_SEEN } from '../data/missing';
import { cellOf } from '../utils/h3cell';
import type { TimeAxis } from '../types/domain';

// ── 수색 ──────────────────────────────────────────────────────────
/**
 * 살아있는 경보 목록 — 경보 진입 관문(useAlertGate)이 판정 대상으로 쓴다.
 *
 * **내 res7 칸을 보내고 서버가 고른다.** 전체를 받아 폰이 거르는 구조로 만들면
 * 앱이 전국 실종자 명단을 받게 되고, 푸시에서 최소화해 둔 것이 무효가 된다.
 *
 * 칸이 바뀌면 queryKey 가 바뀌어 자동으로 다시 묻는다 — 측위가 끝나기 전에는
 * `null` 로 조회되어 빈 목록이 오고(fail-closed), 위치가 잡히면 그때 새 질문이
 * 나간다. 캐시가 "경보 없음"으로 굳지 않는 건 키가 다르기 때문.
 *
 * **주기 조회도 한다.** 앱 시작 때만 읽으면 보호자가 신고해도 시민 앱을 껐다 켜야
 * 경보가 보인다(개발·시연 내내 이게 병목이었다). 푸시가 붙은 뒤에도 백업으로 남는다 —
 * 푸시는 보내는 순간에만 도달하기 때문.
 *
 * @param enabled 시민 트리에서만 true. 운영자 화면에서 GPS 를 켜지 않기 위해
 *   `useMyLocation` 에 그대로 넘긴다.
 */
export const ALERT_POLL_MS = 15_000;

export function useActiveAlerts(enabled = true) {
  const { point } = useMyLocation(enabled);
  const forceInArea = useDebugStore((s) => s.forceInAlertArea);
  // 데모 오버라이드는 "판정을 건너뛰는" 게 아니라 **위치를 갈아끼우는** 쪽으로
  // 건다. 서버가 대상을 고르는 구조라 필터만 꺼봐야 받을 게 없기 때문이고,
  // 실제 동작(내 칸으로 묻는다)을 그대로 타는 편이 시연으로서도 정직하다.
  const cell = cellOf(forceInArea ? LAST_SEEN : point);
  return useQuery({
    queryKey: ['activeAlerts', cell],
    queryFn: () => getActiveAlerts(cell),
    enabled,
    // 앱을 열어 둔 채로 신고가 접수되는 경우를 이 주기가 잡는다. 골든타임이라
    // 오래 모르고 있으면 안 되고, 응답이 경보 몇 건짜리 배열이라 서버 부담도
    // 크지 않다(presence 하트비트가 이미 30초).
    refetchInterval: ALERT_POLL_MS,
    refetchOnWindowFocus: true,
  });
}

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
 * 이 기기가 접수한 사건들 — 보호자 알림(제보) 탭의 단일 창구.
 *
 * 시민 경보와 같은 주기로 다시 묻는다. 보호자가 제보 도착을 시민보다 늦게 알
 * 이유가 없다.
 */
export function useGuardianCases() {
  const caseIds = useGuardianCaseStore((s) => s.caseIds);
  return useQuery({
    queryKey: ['guardianCases', caseIds],
    queryFn: () => getMyCases(caseIds),
    enabled: caseIds.length > 0,
    refetchInterval: ALERT_POLL_MS,
    refetchOnWindowFocus: true,
  });
}

/**
 * 좌표 묶음 → 장소명. 서버가 캐시하므로 같은 골목은 한 번만 외부 조회된다.
 *
 * 이름이 늦게 와도 목록은 먼저 떠야 하므로, 화면은 이 결과를 **덧입히는** 용도로만
 * 쓴다(없으면 좌표를 보여준다).
 */
export function useAreaLabels(points: { lat: number; lng: number }[]) {
  const key = points.map((p) => `${p.lat.toFixed(4)},${p.lng.toFixed(4)}`).join('|');
  return useQuery({
    queryKey: ['areaLabels', key],
    queryFn: () => getAreaLabels(points),
    enabled: points.length > 0,
    // 장소 이름은 변하지 않는다 — 세션 동안 다시 묻지 않는다.
    staleTime: Infinity,
  });
}

/**
 * 예측 실행. 10초 안팎 걸리므로 화면은 반드시 진행 표시를 띄운다.
 * 성공하면 POA 캐시를 버려 다음 조회가 새 예측을 읽게 한다.
 */
export function useRunPrediction(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => runPrediction(caseId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['poa', caseId] });
      qc.invalidateQueries({ queryKey: ['activeAlerts'] });
      qc.invalidateQueries({ queryKey: ['guardianCases'] });
    },
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

/**
 * 수색 안내 문구 (알림 개인화 #5). 사건 중에는 거의 안 바뀌므로 자주 물을 이유가 없다 —
 * 페르소나는 고정이고 경과시간·POA 집중도만 서서히 변한다.
 */
export function useGuidance(caseId: string, enabled = true) {
  return useQuery({
    queryKey: ['guidance', caseId],
    queryFn: () => getGuidance(caseId),
    enabled: enabled && !!caseId,
    staleTime: 5 * 60_000,
    retry: false,
    // 서버가 LLM 으로 문구를 다듬는 **동안만** 다시 묻는다. 서버는 기다리지 않고
    // 템플릿을 먼저 주므로(골든타임), 이게 없으면 다듬은 문구가 화면에 영영 안 온다.
    // 항상 폴링하지 않는 이유: 다듬기는 사건당 한 번뿐이라 끝나면 물어볼 게 없다.
    refetchInterval: (q) => (q.state.data?.pending ? 3_000 : false),
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

/**
 * 등록된 가족 목록 — 보호자 홈.
 *
 * 스토어(guardianStore)가 아니라 서버에서 읽는다. 스토어는 방금 등록한 것을
 * 즉시 띄우기 위한 캐시라 앱을 다시 켜면 비어 있는데, 그때도 사전등록한 가족은
 * 보여야 한다(영속화가 붙어 서버에는 남아 있다).
 */
export function usePersonas() {
  return useQuery({ queryKey: ['personas'], queryFn: () => listPersonas() });
}
