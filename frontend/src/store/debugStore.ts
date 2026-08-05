/**
 * 데모·개발용 오버라이드. **프로덕션 판정 로직은 여기에 두지 않는다** —
 * 이 스토어를 통째로 지워도 앱이 정상 동작해야 한다.
 */
import { create } from 'zustand';

type DebugState = {
  /**
   * 지오펜스를 무시하고 "알림 대상 구역 안에 있다"고 가정한다.
   *
   * 필요한 이유: 경보는 정릉동 반경 안에서만 뜨는 게 맞는 동작인데(그게 타겟
   * 알림의 전제다), 그러면 정릉동 밖에서는 경보 플로우를 시연할 방법이 없어진다.
   * 회의 데모·원격 확인용 스위치다.
   *
   * 기본값은 false — 정직한 동작이 기본이어야 하고, 데모 편의가 기본이 되면
   * 아무도 진짜 동작을 안 보게 된다.
   */
  forceInAlertArea: boolean;
  setForceInAlertArea: (on: boolean) => void;
};

export const useDebugStore = create<DebugState>((set) => ({
  forceInAlertArea: false,
  setForceInAlertArea: (on) => set({ forceInAlertArea: on }),
}));
