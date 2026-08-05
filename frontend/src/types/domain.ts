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
  /**
   * 이 지도가 개인화된 prior 로 만들어졌는지.
   *   exaone   — AI가 사전등록 정보를 읽어 만든 예측
   *   fallback — AI 호출 실패, 프로파일 통계 평균 (개인화 없음)
   *   stub     — AI 미연결 (개인화 없음)
   * **fallback 은 조용히 일어난다.** 표시하지 않으면 통계 평균을 "AI 예측"으로
   * 보여주게 된다 — 수색 인력을 잘못된 확신으로 보내는 일이라 반드시 드러낸다.
   */
  priorSource: 'exaone' | 'fallback' | 'stub' | 'unknown';
  /** fallback/stub 일 때의 사유 (운영 진단용). */
  priorFallbackReason?: string;
};

// ── 경찰 실종경보 ─────────────────────────────────────
/**
 * 알림 종류 — 백엔드 `send_alerts(kind=...)`와 동일한 3종.
 *  - reflex     : D1 골든타임 1차 안전반경(POA 이전, 신고 직후)
 *  - poa        : 예측 기반 타겟 알림
 *  - new_region : D3, 새 지역에서 목격 가능성
 *
 * 프론트에서 이 값이 필요한 이유: "안볼래요" 억제를 어디까지 존중할지 가른다.
 * reflex·new_region 은 진짜 새로운 위험이라 억제를 뚫고 다시 알린다.
 */
export type AlertKind = 'reflex' | 'poa' | 'new_region';

export type PoliceAlert = {
  caseId: string;
  issuedAt: string; // ISO
  area: string;
  severity: Severity;
  kind: AlertKind;
  /**
   * 알림 대상 구역 (온디바이스 지오펜싱).
   *
   * 서버는 "이 구역 사람들에게 알려라"만 뿌리고, **내가 그 안에 있는지는 폰이
   * 판단한다** — 시민 위치가 서버로 올라가지 않는 것이 이 설계의 전제다.
   * 이 필드가 없으면 알림이 무차별 발송이 되고, "타겟 알림"이라는 서비스
   * 전제 자체가 무너진다.
   *
   * 실서비스 페이로드는 H3 셀 목록이 오지만, 푸시 인프라 이전인 지금은
   * 대표 좌표 + 반경으로 근사한다.
   */
  targetCenter: GeoPoint;
  targetRadiusM: number;
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
