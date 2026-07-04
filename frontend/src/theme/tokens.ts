/**
 * 디자인 토큰 (spec §7 확정본).
 * 색은 "브랜드"가 아니라 "상태 심각도"를 부호화한다 — 앰버를 긴급에 쓰지 않는다.
 */
import type { TextStyle } from 'react-native';
import type { PoaTier } from '../types/domain';

export const color = {
  // 모드 색 (심각도 위계: 평시 그린 → 진행 앰버 → 긴급 빨강)
  walk: '#1DA35C', // 산책 모드(평시)
  walkInk: '#127A43',
  walkWash: '#E9F7EF',
  search: '#E8703F', // 수색 진행(2차) — 타이머·진행바·세그먼트 활성
  searchInk: '#B14E27',
  searchWash: '#FDEEE7',
  critical: '#D62839', // 긴급 실종경보(승격) — 락스크린·경보상세·골든타임·최종목격
  criticalInk: '#8E1B26',
  criticalWash: '#FCEBEC',

  // 텍스트 (WCAG 대비 확보 — #8B909A 폐기)
  text: '#14161C', // primary 16.8:1
  textBody: '#5C616B', // secondary 본문 최소 6.2:1
  textCaption: '#6B7079', // tertiary 캡션 4.6:1 (#8B909A 대체)

  // 표면/보더 (라이트)
  surface: '#FFFFFF',
  surfaceAlt: '#F7F8FA',
  successWash: '#F4F1ED',
  border: '#ECEEF1',

  // 운영자 다크 트리 전용
  operatorBg: '#0F1114',
  operatorSurface: '#1B1E24',
  operatorSurfaceAlt: '#22262E',
  operatorBorder: '#2A2E36',
  operatorText: '#F4F6F8',
  operatorTextSec: 'rgba(255,255,255,0.72)', // ≥4.6:1 (spec §4.3)
} as const;

/**
 * POA 4단계 팔레트 — 색상+명도 이중부호화 (spec §4.2).
 * 명도(L*) 단조 증가 30→90 이라 흑백/색약에서도 순서 보존.
 */
export type PoaPatternKind = 'solid' | 'hatch' | 'dot' | 'outline';

export const poa: Record<PoaTier, {
  fill: string;
  border: string;
  opacity: number;
  pattern: PoaPatternKind;
  L: number;
}> = {
  high: { fill: '#B31022', border: '#7A0C18', opacity: 0.82, pattern: 'solid', L: 30 },
  mid: { fill: '#EA580C', border: '#A63C08', opacity: 0.70, pattern: 'hatch', L: 55 },
  low: { fill: '#F5A623', border: '#C77E12', opacity: 0.58, pattern: 'dot', L: 74 },
  lowest: { fill: '#FDE38A', border: '#C9A94A', opacity: 0.42, pattern: 'outline', L: 90 },
};

// 타이포 — Pretendard 의도(미임베드 시 시스템 폰트). 최소 15sp + Dynamic Type.
type Weight = TextStyle['fontWeight'];
export const type = {
  family: undefined as string | undefined, // Pretendard 임베드 시 'Pretendard'
  minBody: 15,
  maxScale: 1.6, // maxFontSizeMultiplier
  size: {
    title: 20, // 화면 타이틀
    cardTitle: 18, // 카드 제목
    body: 16, // 본문
    label: 15, // 라벨 (최소)
    caption: 13, // 캡션(비필수 하한)
    bigNum: 34, // 대형 수치
  },
  weight: {
    regular: '400' as Weight,
    medium: '600' as Weight,
    bold: '700' as Weight,
    black: '800' as Weight,
  },
} as const;

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;
export const radius = { sm: 8, md: 12, lg: 16, xl: 24, pill: 999 } as const;

/** 최소 터치 히트영역 (spec §4.4). */
export const HIT = 48;
