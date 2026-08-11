/**
 * 인증/역할 — role 클레임이 RootNavigator의 마운트 트리를 결정한다 (spec §2.3).
 *
 * ## 왜 실제 계정인가
 * 예전에는 역할 버튼을 누르면 `demo-token-citizen` 을 만들어 넣었고, 모든 기기가
 * 같은 `demo-citizen` 사용자로 서버에 붙었다. 그래서 누가 앱을 켜도 남의 산책
 * 횟수·제보 수·등급이 그대로 보였다. 이제 아이디마다 다른 `user_id` 를 받고,
 * 산책·제보 기록이 그 값으로 갈린다.
 *
 * ## 기기에 남기는 것
 * **토큰과 식별자만 남긴다 — 비밀번호는 남기지 않는다.** 서버가 토큰을 지우면
 * (로그아웃) 남은 값은 아무 힘이 없다.
 */
import { safeStorage } from './safeStorage';
import { Platform } from 'react-native';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import * as authApi from '../api/auth';
import type { Role } from '../types/domain';

type AuthState = {
  token: string | null;
  role: Role | null;
  /** 화면에 보여줄 이름 = 아이디. 실명을 받지 않는다. */
  user: string | null;
  /** 서버 기록의 주인. 산책·제보 API 가 이 값을 쓴다. */
  userId: string | null;
  /** 저장된 토큰을 확인하는 중 — 이 동안 로그인 화면을 깜빡이지 않게 한다. */
  restoring: boolean;

  signIn: (loginId: string, password: string) => Promise<void>;
  signUp: (loginId: string, password: string, role: Role) => Promise<void>;
  signOut: () => void;
  /** 역할 전환 — 앱의 화면 트리가 역할로 갈리므로 이걸 바꾸면 트리가 통째로 바뀐다. */
  switchRole: (role: Role) => Promise<void>;
  /** 앱 시작 시 1회 — 저장된 토큰이 아직 유효한지 서버에 묻는다. */
  restore: () => Promise<void>;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      role: null,
      user: null,
      userId: null,
      restoring: true,

      signIn: async (loginId, password) => {
        const r = await authApi.login(loginId, password);
        set({ token: r.token, role: r.role, user: r.login_id, userId: r.user_id, restoring: false });
      },

      signUp: async (loginId, password, role) => {
        const r = await authApi.signup(loginId, password, role);
        set({ token: r.token, role: r.role, user: r.login_id, userId: r.user_id, restoring: false });
      },

      switchRole: async (role) => {
        const token = get().token;
        if (!token) return;
        const r = await authApi.changeRole(token, role);
        set({ role: r.role, user: r.login_id, userId: r.user_id });
        // 역할이 바뀌면 화면 트리가 통째로 갈린다(보호자↔시민). 그 자리에서
        // 갈아끼우면 내비게이션 상태가 어긋나 흰 화면이 되는 경우가 있다
        // (현장 제보 08-11). 웹에서는 한 번 새로 띄워 확실하게 만든다 —
        // 토큰은 저장돼 있으므로 다시 로그인할 필요는 없다.
        if (Platform.OS === 'web' && typeof window !== 'undefined') {
          setTimeout(() => window.location.reload(), 60);
        }
      },

      signOut: () => {
        const token = get().token;
        // 서버에서도 지운다 — 기기에서만 지우면 남은 토큰이 계속 유효하다.
        if (token) authApi.logout(token).catch(() => {});
        set({ token: null, role: null, user: null, userId: null, restoring: false });
      },

      restore: async () => {
        const token = get().token;
        if (!token) {
          set({ restoring: false });
          return;
        }
        try {
          const r = await authApi.me(token);
          set({ role: r.role, user: r.login_id, userId: r.user_id, restoring: false });
        } catch {
          // 서버가 토큰을 모른다 = 로그아웃 상태. 네트워크 실패도 같은 취급인데,
          // 남은 토큰으로 남의 기록을 보여주는 쪽보다 다시 로그인하는 쪽이 낫다.
          set({ token: null, role: null, user: null, userId: null, restoring: false });
        }
      },
    }),
    {
      name: 'auth-v2',
      storage: createJSONStorage(() => safeStorage),
      // 비밀번호는 애초에 상태에 없다. 토큰·식별자만 남긴다.
      partialize: (s) => ({ token: s.token, role: s.role, user: s.user, userId: s.userId }),
    },
  ),
);
