/**
 * 도메인 타입 — 백엔드(FastAPI, /phase0~3) 스키마를 프런트에 반영한 단일 소스.
 * 백엔드 대응: backend/app/schemas/{common,persona,prediction,case,tip}.py
 */

// ── 공통 ──────────────────────────────────────────────
export type GeoPoint = { lat: number; lng: number };

/** 역할 — 와이어프레임(2026-08-05)의 두 트리. 운영자는 앱에서 제거됐다
 *  (관제는 백엔드 /dashboard 웹 화면이 맡는다). */
export type Role = 'citizen' | 'guardian';

/** 앱 전역 모드 — 화면이 아니라 상태. 경찰 실종경보 연동만이 walk→search 트리거. */
export type AppMode = 'walk' | 'search';

/** 심각도 — critical=빨강(긴급), active=앰버(수색 진행 중). */
export type Severity = 'critical' | 'active';

export type CaseStatus = 'intake' | 'predicted' | 'searching' | 'found' | 'closed';

// ── 실종자 단일 소스 (spec §5) ────────────────────────
export type MissingPerson = {
  id: string;
  name: string;
  rel: string;
  age: number;
  sex: 'F' | 'M';
  cognition: string;
  appearance: string[];
  area: string;
  lastSeen: string;
  label: string;
  photoUrl?: string;
};

// ── POA(발견확률) — 지도 렌더용 ───────────────────────
export type PoaTier = 'high' | 'mid' | 'low' | 'lowest';

/** 예측 시간축 (경과 시간, 시간 단위). */
export type TimeAxis = 0 | 1 | 3 | 6;

export type PoaCell = {
  id: string;
  center: GeoPoint;
  /** 셀 폴리곤 꼭짓점(사각/육각). 지도 오버레이용. */
  polygon: GeoPoint[];
  /** 확률 0..1. */
  prob: number;
  tier: PoaTier;
  /** 교차검증(마음/몸) 불일치 셀. */
  mismatch?: boolean;
};

export type PoaGrid = {
  caseId: string;
  t: TimeAxis;
  cells: PoaCell[];
  /** 상위 셀 누적 발견확률 0..1. */
  cumulative: number;
  /** 최고확률 구역 요약 (접근성 라벨용). */
  topLabel: string;
};

// ── 경찰 실종경보 ─────────────────────────────────────
export type PoliceAlert = {
  caseId: string;
  issuedAt: string; // ISO
  area: string;
  severity: Severity;
  /** 내 위치로부터 거리(m) — '내 주변' 타겟 근거. */
  distanceM: number;
  summary: string;
  matchedPersonId?: string; // 보호자 사전등록 매칭 시
};

// ── 시민 제보 (spec / backend tip.py) ─────────────────
export type TipDecision = 'discard' | 'layer1' | 'layer2';

export type Tip = {
  id: string;
  caseId: string;
  text: string;
  location?: GeoPoint;
  seenAt?: string;
  hasPhoto: boolean;
  p?: number;
  decision?: TipDecision;
  createdAt: string;
};

/** 제보 챗봇이 수집하는 구조화 입력. */
export type TipInput = {
  text: string;
  location?: GeoPoint;
  seenAt?: string;
  direction?: string;
  hasPhoto?: boolean;
};

/** 제보 전송 결과 — 기여 시각화(수색구역 delta)까지 포함. */
export type TipResult = {
  tip: Tip;
  beforeAreaKm2: number;
  afterAreaKm2: number;
  deltaPct: number; // 음수 = 좁혀짐
  beforeGrid?: PoaGrid;
  afterGrid?: PoaGrid;
};

// ── 목표 지점(POI) 확률 ───────────────────────────────
export type Poi = {
  id: string;
  name: string;
  center: GeoPoint;
  prob: number;
  reason: string;
};

// ── 교차검증(마음 ↔ 몸) ───────────────────────────────
export type CrossValCell = { id: string; row: number; col: number; tier: PoaTier; mismatch: boolean };

export type CrossValidation = {
  caseId: string;
  /** 마음·몸 예측 일치도 0..1. */
  agreement: number;
  /** Jensen-Shannon divergence (0=완전일치). */
  jsd: number;
  mind: CrossValCell[];
  body: CrossValCell[];
};

// ── 근거 타임라인(마음 상태 추론) ─────────────────────
export type ReasonStep = {
  id: string;
  time: string;
  status: string;
  confusion: number; // 0..1
  note: string;
};

// ── 검증 수치 리포트 ──────────────────────────────────
export type AblationBar = { label: string; value: number; highlight?: boolean };

export type ValidationMetrics = {
  caseId: string;
  ablation: AblationBar[];        // 돌아오길 AI vs 고전모델 vs 유형평균
  hitAtDistanceM: number;         // 예측 반경 내 발견 거리(m)
  jsd: number;                    // 이동분포 유사도
  cumulativePoa: number;          // 누적 발견확률 0..1
};

// ── 발견·종료 요약 ────────────────────────────────────
export type FoundSummary = {
  caseId: string;
  elapsed: string;      // "52분"
  citizens: number;     // 동원 시민
  validTips: number;    // 유효 제보 수
  foundArea: string;
};

// ── 산책(평시) 데이터 ─────────────────────────────────
export type WalkStats = {
  steps: number;
  goal: number;
  distanceKm: number;
  durationMin: number;
  route: GeoPoint[];
};

export type WalkCourse = { id: string; name: string; distanceKm: number; durationMin: number; tag: string };
