/** 네비게이션 파라미터 계약 (와이어프레임 2026-08-05, React Navigation v7).
 *
 * 역할 트리는 `보호자 / 시민` 둘이다. 운영자(관제 대시보드·검증 리포트) 트리는
 * 제거했다 — 와이어프레임에 없고, 관제는 백엔드 `/dashboard` 웹 화면이 맡는다.
 */
import type { NavigatorScreenParams } from '@react-navigation/native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { CompositeScreenProps } from '@react-navigation/native';

export type RootStackParamList = {
  Auth: undefined;
  CitizenTabs: NavigatorScreenParams<CitizenTabParamList> | undefined;
  GuardianTabs: NavigatorScreenParams<GuardianTabParamList> | undefined;

  // 보호자 플로우 (홈에서 진입)
  RegChat: undefined;
  RegDone: { personaId: string; name: string; age: number };
  Report: undefined;
  ReportSent: { caseId: string };

  // 시민 수색 플로우 — 딥링크 dora://alert/:caseId
  LockScreenAlert: { caseId: string };
  AlertDetail: { caseId: string };
  AlertSync: { caseId: string };
  Appearance: { caseId: string };
  TipWarn: { caseId: string };
  ReportChat: { caseId: string };
  ReportDone: { caseId: string; beforeAreaKm2?: number; afterAreaKm2?: number; deltaPct?: number };

  // 시민 산책 플로우
  WalkActive: undefined;
  WalkSummary: { sessionId: string; distanceKm: number; durationMin: number };
};

/** 시민 하단 4탭 — 와이어프레임: 안심홈 / 산책하기 / 긴급알림 / 내 기록. */
export type CitizenTabParamList = {
  Home: undefined;
  Walk: undefined;
  Alerts: undefined;
  Records: undefined;
};

/** 보호자 하단 3탭 — 와이어프레임: 홈 / 사전등록 / 내 정보. */
export type GuardianTabParamList = {
  GuardianHome: undefined;
  GuardianReg: undefined;
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
