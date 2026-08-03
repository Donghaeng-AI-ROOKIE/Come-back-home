/** 색 토큰 — 디자인 인계 문서(claude.ai/design 「인계 토큰·컴포넌트」) 그대로.
 *  3색 의미 체계(긴급 빨강/수색 앰버/평시 그린)는 모바일 앱과 공유하는 확정값.
 *  액센트 블러플은 의미색이 아니라 상호작용/선택 표시 전용. */
export const T = {
  // 그라운드·표면
  appBg: "#161826",
  mapBg: "#0e1017",
  surface: "#181a28",
  card: "#1a1d2b",
  inset: "#1c1f2c",
  chip: "#20232f",
  border: "rgba(233,233,237,.09)",
  borderStrong: "rgba(233,233,237,.14)",
  // 텍스트
  text: "#e9e9ed",
  sub: "#9aa0b4",
  dim: "#7f8598",
  faint: "#6f7488",
  // 액센트 (상호작용 전용)
  accent: "#9184d9",
  accentLight: "#b5abfc",
  accentLighter: "#c4bcff",
  accentTint: "rgba(145,132,217,.16)",
  // 긴급 빨강 — 실종 경보 D1/D2/D3
  red: "#f2555a",
  redText: "#ff9ea1",
  redBg: "rgba(242,85,90,.14)",
  redBorder: "rgba(242,85,90,.4)",
  // 수색 앰버 — 진행 중 수색·POA
  amber: "#f0a63c",
  amberText: "#f0c07a",
  amberBg: "rgba(240,166,60,.14)",
  amberBorder: "rgba(240,166,60,.34)",
  // 평시 그린 — 종결·안전
  green: "#45b869",
  greenText: "#7cd79a",
  greenBg: "rgba(69,184,105,.14)",
  greenBorder: "rgba(69,184,105,.34)",
  // 제보 티어·마커
  tierDiscard: "#75798c",
  home: "#6fb0e0",
  mono: "ui-monospace,'SF Mono',Menlo,monospace",
} as const;

/** 실제 백엔드 축 필드명 → 한국어 라벨 (schemas/persona.py axis_scores 키 기준).
 *  디자인 목업의 "이동성/목적성/배회 경향"은 단순화였음 — 구현은 실축과 매핑한다. */
export const AXIS_LABELS_KO: Record<string, string> = {
  mobility_transport_capacity: "이동·보행 지구력",
  environmental_hazard_vulnerability: "환경위험 취약성",
  communication_approach_vulnerability: "의사소통·접근 취약성",
  autobiographical_destination_pull: "자전적기억 목적지",
  wayfinding_error_recovery_deficit: "길찾기 오류·회복",
  distress_induced_movement_reactivity: "정서 이동반응성",
};

export const axisLabel = (key: string): string => AXIS_LABELS_KO[key] ?? key;
