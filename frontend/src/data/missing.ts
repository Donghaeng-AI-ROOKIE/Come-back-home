/**
 * 실종자 단일 소스 (spec §5). 전 화면이 이 상수만 참조 — "남성"·"84세" 하드코딩 금지.
 */
import type { GeoPoint, MissingPerson } from '../types/domain';

export const MISSING: MissingPerson = {
  id: 'mp-kim-soonja',
  name: '김순자',
  rel: '어머니',
  age: 78,
  sex: 'F',
  cognition: '중기 치매',
  appearance: ['회색 점퍼', '검은 바지', '지팡이'],
  area: '정릉동',
  lastSeen: '정릉동 주민센터, 오후 3시 10분경',
  label: '78세 여성 · 치매 · 회색 점퍼 · 정릉동',
};

/** 시민 노출용 익명 표기 — 실명·의료정보 비노출. */
export const MISSING_ANON = '78세 어르신';

/** 데모 케이스 id — 경보/예측/제보가 공유하는 단일 사건. */
export const DEMO_CASE_ID = 'case-jeongneung-001';

/** 최종 목격 위치 (정릉동 주민센터 인근). */
export const LAST_SEEN: GeoPoint = { lat: 37.6061, lng: 127.0106 };
