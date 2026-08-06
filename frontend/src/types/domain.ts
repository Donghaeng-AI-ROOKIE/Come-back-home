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

/**
 * 예측 시간축 — **경과시간(시간)**. 0 = "지금 실제 경과시간".
 *
 * 시작점(최종 목격 위치)은 고정이고 바뀌는 것은 "얼마나 걸을 수 있었나"뿐이다.
 * 물감 한 방울처럼 떨어뜨린 자리는 그대로고 퍼진 범위만 커진다.
 */
export type TimeAxis = 0 | 0.5 | 1 | 2 | 3 | 4 | 6 | 8;

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
  /**
   * 도로망 위에서 걸은 예측인지. false 면 연속 공간(도로 제약 없음)이다.
   * `use_roadnet` 기본값이 true 라(PR #122) false 는 대개 로딩 실패를 뜻한다 —
   * 이 폴백도 조용해서 POA·지도는 정상으로 나온다.
   */
  roadnetUsed: boolean;
  roadnetFallbackReason?: string;
  /**
   * 이 지도가 계산된 시각과, 그때의 경과시간.
   *
   * 서버가 45분마다 다시 예측하지만(phase2.refresher) **화면에 안 보이면
   * 수색대는 지도가 최신인지 알 수 없다.** 갱신이 실패해 오래된 지도를 계속
   * 보고 있어도 모르게 되므로 반드시 표시한다.
   */
  computedAt?: string;
  elapsedHours?: number;
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

/**
 * 푸시 알림 페이로드 — 백엔드 `alerts.send_alerts()` 가 `data` 에 싣는 것.
 *
 * 대상 구역은 **H3 셀 목록**이다. 예측 격자(res9)를 그대로 실으면 500개 ≈ 7KB 로
 * Expo `data` 상한(약 4KiB)을 넘지만, res7 부모로 접으면 3~8개뿐이라 그냥 실린다.
 * 한때 중심+반경으로 근사했던 것은 해상도를 낮출 생각을 안 한 탓이다.
 *
 * 필드명이 snake_case 인 것은 서버 JSON 을 그대로 받기 때문(변환 계층 없음).
 */
export type PushPayload = {
  case_id: string;
  kind: AlertKind;
  /** 대상 H3 셀(부모 해상도). 폰이 자기 셀과 대조해 관문 여부를 정한다. */
  target_cells: string[];
  /** 위 셀들의 해상도. 폰이 자기 좌표를 **이 해상도로** 변환해 비교해야 한다. */
  target_res: number;
  appearance: string;
};

export type PoliceAlert = {
  caseId: string;
  issuedAt: string; // ISO
  area: string;
  severity: Severity;
  kind: AlertKind;
  /**
   * 알림 대상 구역 — H3 셀 목록(부모 해상도, `targetRes`).
   *
   * 이 필드가 없으면 알림이 무차별 발송이 되고 "타겟 알림"이라는 서비스 전제가
   * 무너진다. 서버는 이 목록 안 기기에만 푸시를 보내고, 앱 안 관문도 **같은
   * 목록**으로 판정한다 — 둘이 어긋나면 "알림은 왔는데 앱은 구역 밖이라 한다"가 된다.
   *
   * 근사가 아니라 셀 id 비교다. 한때 중심+반경 원으로 근사했는데 육각 셀 집합보다
   * 넓어 구역 밖 사람이 섞였고, 그건 "폰에 H3 가 없다"는 틀린 전제 때문이었다.
   */
  targetCells: string[];
  /** 위 셀들의 해상도. 폰은 자기 좌표를 이 해상도로 바꿔 비교한다(utils/h3cell.ts). */
  targetRes: number;
  summary: string;
  matchedPersonId?: string; // 보호자 사전등록 매칭 시
  /**
   * 시민 화면이 띄울 최소 신원. **이름은 없다** — 불특정 다수에게 가는 알림이라
   * 나이·인상착의로 충분하고, 이름까지 뿌리면 목적을 넘는 개인정보 제공이 된다.
   */
  age?: number;
  appearance?: string[];
  lkp?: GeoPoint;
  lkpTime?: string;
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
