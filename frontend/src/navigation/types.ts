/** 네비게이션 파라미터 계약 (와이어프레임 2026-08-05, React Navigation v7).
 *
 * 역할 트리는 `보호자 / 시민` 둘이다. 운영자(관제 대시보드·검증 리포트) 트리는
 * 제거했다 — 와이어프레임에 없고, 관제는 백엔드 `/dashboard` 웹 화면이 맡는다.
 */
import type { NavigatorScreenParams } from '@react-navigation/native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { GeoPoint } from '../types/domain';
import type { CompositeScreenProps } from '@react-navigation/native';

export type RootStackParamList = {
  Auth: undefined;
  CitizenTabs: NavigatorScreenParams<CitizenTabParamList> | undefined;
  GuardianTabs: NavigatorScreenParams<GuardianTabParamList> | undefined;

  // 보호자 플로우 (홈에서 진입)
  /**
   * `regular` 12문항 온보딩 · `quick` 신고 직전 Tier1 5문항 ·
   * `supplement` 빠른 등록이 안 물은 Tier2·3 7문항(기존 persona 갱신).
   */
  RegChat: { mode?: 'regular' | 'quick' | 'supplement'; caseId?: string;
    /** 부스 시연: 진행자가 "다음 체험 준비"로 만든 복제 세션을 새로 만들지 않고 그대로 연다. */
    sessionId?: string } | undefined;
  RegDone: { personaId: string; name: string; age: number };
  /** 사전 등록 상세 — 저장된 내용 전체 열람·수정. */
  PersonaDetail: { personaId: string };
  Report: undefined;
  ReportSent: { caseId: string };

  // 시민 수색 플로우 — 딥링크 dora://alert/:caseId
  LockScreenAlert: { caseId: string };
  AlertDetail: { caseId: string };
  AlertSync: { caseId: string };
  Appearance: { caseId: string };
  TipWarn: { caseId: string };
  ReportChat: { caseId: string };
  ReportDone: { caseId: string };
  /** 상황 종료 상세 — 긴급 알림 목록의 초록 카드에서 연다. 카드가 가진 값만 들고 간다
      (이름·인상착의·위치는 종결 응답에 애초에 없다). 서버를 다시 부르지 않는다. */
  ResolvedDetail: {
    caseId: string;
    area: string;
    age?: number;
    closedAt: string;
    tipCount?: number;
    searchMinutes?: number;
  };

  // 시민 산책 플로우
  WalkActive: undefined;
  // path 는 **기기 안에서만** 요약 화면으로 넘어간다 — 서버는 산책 경로를
  // 저장하지 않는다(schemas/walk.py: 좌표가 아니라 지역 라벨만). 그래서
  // 걸은 길을 그리려면 이 화면 전이로 들고 가는 수밖에 없다.
  WalkSummary: { sessionId: string; distanceKm: number; durationMin: number; path?: GeoPoint[] };
};

/** 시민 하단 4탭 — 와이어프레임: 안심홈 / 산책하기 / 긴급알림 / 내 기록. */
export type CitizenTabParamList = {
  Home: undefined;
  Walk: undefined;
  Alerts: undefined;
  Records: undefined;
};

/** 보호자 하단 4탭 — Figma: 홈 / 사전등록 / 알림 / 내 정보. */
export type GuardianTabParamList = {
  GuardianHome: undefined;
  GuardianReg: undefined;
  GuardianAlerts: undefined;
  GuardianMy: undefined;
};

export type RootStackScreenProps<T extends keyof RootStackParamList> =
  NativeStackScreenProps<RootStackParamList, T>;

export type CitizenTabScreenProps<T extends keyof CitizenTabParamList> = CompositeScreenProps<
  BottomTabScreenProps<CitizenTabParamList, T>,
  RootStackScreenProps<keyof RootStackParamList>
>;

export type GuardianTabScreenProps<T extends keyof GuardianTabParamList> = CompositeScreenProps<
  BottomTabScreenProps<GuardianTabParamList, T>,
  RootStackScreenProps<keyof RootStackParamList>
>;

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace ReactNavigation {
    interface RootParamList extends RootStackParamList {}
  }
}
