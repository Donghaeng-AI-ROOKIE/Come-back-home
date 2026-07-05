/**
 * API 클라이언트. 현재는 목 데이터. USE_MOCK=false 로 두면 실제 FastAPI 백엔드
 * (backend/app/api/phase0~3)에 연결. 함수 시그니처는 백엔드 계약을 그대로 반영.
 *
 * 백엔드 라우트 대응:
 *   getActiveAlerts   → (푸시/폴링; 데모는 목)
 *   getPoaPrediction  → GET  /phase3/cases/{caseId}/poa  (+ Phase2 predict 선행)
 *   getCrossValidation→ (Phase2 산출물 파생; 데모는 목)
 *   submitTip         → POST /phase3/cases/{caseId}/tips
 *   sendAlerts        → POST /phase3/cases/{caseId}/alerts
 *   getValidation     → (검증 리포트; 데모는 목)
 *   getFoundSummary   → GET  /phase1/cases/{caseId} + 집계
 */
import type {
  CrossValidation,
  FoundSummary,
  PoaGrid,
  PoliceAlert,
  TimeAxis,
  Tip,
  TipInput,
  TipResult,
  ValidationMetrics,
} from '../types/domain';
import { DEMO_CASE_ID } from '../data/missing';
import {
  buildAlert,
  buildBeforeAfter,
  buildCrossValidation,
  buildFoundSummary,
  buildPoaGrid,
  buildValidation,
} from '../data/mock';

export const USE_MOCK = true;
/** 실제 백엔드 주소 (에뮬레이터: 안드로이드=10.0.2.2, iOS 시뮬=localhost). */
export const API_BASE = 'http://localhost:8000';

function delay<T>(value: T, ms = 350): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

export async function getActiveAlerts(): Promise<PoliceAlert[]> {
  if (USE_MOCK) return delay([buildAlert()]);
  // 실서비스: 푸시(Notifee/FCM) + 지오펜스 백그라운드 폴링. 데모 미구현.
  return [];
}

export async function getPoaPrediction(caseId: string, t: TimeAxis): Promise<PoaGrid> {
  if (USE_MOCK) return delay(buildPoaGrid(t));
  const res = await fetch(`${API_BASE}/phase3/cases/${caseId}/poa?top=64`);
  if (!res.ok) throw new Error(`POA 조회 실패: ${res.status}`);
  // 백엔드는 top_cells(H3 셀 id+prob)를 반환 → 클라에서 셀 지오메트리로 매핑 필요.
  return buildPoaGrid(t); // TODO: H3 → 폴리곤 변환기 연결
}

export async function getCrossValidation(caseId: string): Promise<CrossValidation> {
  if (USE_MOCK) return delay(buildCrossValidation());
  return buildCrossValidation();
}

export async function submitTip(caseId: string, input: TipInput): Promise<TipResult> {
  if (USE_MOCK) {
    const { before, after, beforeKm2, afterKm2 } = buildBeforeAfter();
    const tip: Tip = {
      id: `tip-${Math.round(Date.now() / 1000)}`,
      caseId,
      text: input.text,
      location: input.location,
      seenAt: input.seenAt,
      hasPhoto: !!input.hasPhoto,
      p: 0.72,
      decision: 'layer1',
      createdAt: new Date().toISOString(),
    };
    const deltaPct = Math.round(((afterKm2 - beforeKm2) / beforeKm2) * 100);
    return delay({ tip, beforeAreaKm2: beforeKm2, afterAreaKm2: afterKm2, deltaPct, beforeGrid: before, afterGrid: after }, 700);
  }
  const res = await fetch(`${API_BASE}/phase3/cases/${caseId}/tips`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: input.text,
      location: input.location,
      seen_at: input.seenAt,
      with_photo: !!input.hasPhoto,
    }),
  });
  if (!res.ok) throw new Error(`제보 전송 실패: ${res.status}`);
  throw new Error('실서비스 응답 매핑 미구현'); // TODO
}

export async function sendAlerts(caseId: string): Promise<{ delivered: number; cells: number }> {
  if (USE_MOCK) return delay({ delivered: 128, cells: 12 });
  const res = await fetch(`${API_BASE}/phase3/cases/${caseId}/alerts`, { method: 'POST' });
  if (!res.ok) throw new Error(`알림 발송 실패: ${res.status}`);
  return { delivered: 0, cells: 0 };
}

export async function getValidation(caseId: string): Promise<ValidationMetrics> {
  if (USE_MOCK) return delay(buildValidation());
  return buildValidation();
}

export async function getFoundSummary(caseId: string): Promise<FoundSummary> {
  if (USE_MOCK) return delay(buildFoundSummary());
  return buildFoundSummary();
}

export { DEMO_CASE_ID };
