/**
 * 실종자 정보를 **화면에 내보내기 전에 통과하는 단일 관문** (spec §5).
 *
 * ## 왜 함수로 빼는가
 * "시민에게는 실명·나이·진단명을 노출하지 않는다"는 개인정보 결정인데, 지금까지는
 * 표시 컴포넌트 안의 `anon` 분기에 들어 있었다. 그러면 컴포넌트를 교체하는 순간
 * (디자인 시안 적용 등) 규칙이 조용히 사라지고, 새 컴포넌트가 `name`·`age`·
 * `cognition` 을 그대로 받아버리기 쉽다.
 *
 * 여기서 **미리 문자열로 눌러 담으면 컴포넌트는 원본 필드를 아예 못 본다.**
 * 못 받은 것은 샐 수 없다 — LLM 스토리텔링에서 "프롬프트가 아니라 입력에 제약을
 * 건다"고 한 것과 같은 원칙이다.
 *
 * ## 근거
 * 진단명·인지상태는 개인정보보호법 제23조 민감정보다. 그런데 수색에는 진단명이
 * 필요 없다 — "길을 찾지 못하고 계세요"면 시민의 행동 지침으로 충분하다.
 * 노출을 늘려도 시민이 다른 곳을 보게 되지 않으면 최소성 심사를 통과하지 못한다.
 */
import type { MissingPerson } from '../types/domain';
import { MISSING_ANON } from './missing';

/** 화면이 받는 전부. 원본 프로필은 여기서 끊긴다. */
export type MissingPersonView = {
  /** 표제 — 실명 또는 익명 표기. */
  title: string;
  /** 부제 — 구역, 또는 나이·성별·인지상태. */
  meta: string;
  /** 인상착의 (양쪽 다 노출 — 식별 표지라 수색에 직접 기여). */
  appearance: string[];
};

/**
 * **시민 노출용.** 실명·나이·인지상태를 넣지 않는다.
 * 경보·수색 등 불특정 다수가 보는 화면은 전부 이 뷰를 쓴다.
 */
export function toAnonView(p: MissingPerson): MissingPersonView {
  return {
    title: MISSING_ANON,
    meta: `${p.area} 인근`,
    appearance: p.appearance,
  };
}

/**
 * **보호자·운영자용.** 실명과 인지상태를 포함한다.
 * 이미 신원을 아는 사람(가족)이나 직무상 필요한 사람(경찰·관제)만 보는 화면에서만 쓸 것.
 */
export function toFullView(p: MissingPerson): MissingPersonView {
  const sexLabel = p.sex === 'F' ? '여성' : '남성';
  return {
    title: p.name,
    meta: `${p.age}세 · ${sexLabel} · ${p.cognition}`,
    appearance: p.appearance,
  };
}

/**
 * **경보(서버 실데이터)에서 바로 만드는 시민 노출용 뷰.**
 *
 * `toAnonView` 는 목업 상수 `MISSING` 을 담은 스토어를 전제한다 — 그래서 실제
 * 신고가 82세인데 화면에는 목업의 78세가 뜨는 일이 있었다(2026-08-05 실측).
 * 서버 경보에는 애초에 **이름이 오지 않으므로**(백엔드가 안 보낸다) 이 경로는
 * 익명화를 "지키는" 것이 아니라 구조적으로 보장한다.
 */
export function alertToView(a: {
  age?: number;
  area?: string;
  appearance?: string[];
  summary?: string;
}): MissingPersonView {
  // 표제도 실데이터로 만든다. 상수 MISSING_ANON 은 "78세 어르신"처럼 나이가 박혀
  // 있어, 실제 신고가 82세면 제목 78세·부제 82세로 **한 카드 안에서 모순**이 난다
  // (2026-08-05 실측). 나이를 모르면 나이를 빼고 쓴다.
  const title = a.age ? `${a.age}세 어르신` : '실종 어르신';
  const meta = a.area ? `${a.area} 인근` : '최종 목격 위치 기준';
  // 구조화 인상착의가 비면 요약 한 줄이라도 보여준다 — 수색의 핵심 단서다.
  const appearance = (a.appearance ?? []).filter(Boolean);
  return {
    title,
    meta,
    appearance: appearance.length ? appearance : (a.summary ? [a.summary] : []),
  };
}
