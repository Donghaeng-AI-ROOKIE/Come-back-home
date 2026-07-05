/** 네비게이션 파라미터 계약 (spec §2.2, React Navigation v7). */
import type { NavigatorScreenParams } from '@react-navigation/native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { CompositeScreenProps } from '@react-navigation/native';

export type RootStackParamList = {
  Auth: undefined;
  CitizenTabs: NavigatorScreenParams<CitizenTabParamList> | undefined;
  Operator: NavigatorScreenParams<OperatorStackParamList> | undefined;
  // 소비자 플로우 모달/카드 (딥링크 dora://alert/:caseId)
  LockScreenAlert: { caseId: string };
  AlertDetail: { caseId: string };
  AlertSync: { caseId: string };
  ReportChat: { caseId: string };
  ReportDone: { caseId: string; beforeAreaKm2?: number; afterAreaKm2?: number; deltaPct?: number };
};

export type CitizenTabParamList = {
  Home: undefined;
  Search: undefined;
  Reg: undefined;
};

export type OperatorStackParamList = {
  Command: undefined;
  CaseFound: undefined;
  ValidationReport: undefined;
};

export type RootStackScreenProps<T extends keyof RootStackParamList> = NativeStackScreenProps<RootStackParamList, T>;

export type CitizenTabScreenProps<T extends keyof CitizenTabParamList> = CompositeScreenProps<
  BottomTabScreenProps<CitizenTabParamList, T>,
  RootStackScreenProps<keyof RootStackParamList>
>;

export type OperatorStackScreenProps<T extends keyof OperatorStackParamList> = NativeStackScreenProps<
  OperatorStackParamList,
  T
>;

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace ReactNavigation {
    interface RootParamList extends RootStackParamList {}
  }
}
