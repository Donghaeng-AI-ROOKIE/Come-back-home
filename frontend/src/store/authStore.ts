/** 인증/역할 — role 클레임이 RootNavigator의 마운트 트리를 결정한다 (spec §2.3). */
import { create } from 'zustand';
import type { Role } from '../types/domain';

type AuthState = {
  token: string | null;
  role: Role | null;
  user: string | null;
  login: (role: Role) => void;
  logout: () => void;
};

const USER_LABEL: Record<Role, string> = {
  citizen: '김OO',
  guardian: '이OO',
  operator: '관제 담당',
};

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  role: null,
  user: null,
  login: (role) => set({ token: `demo-token-${role}`, role, user: USER_LABEL[role] }),
  logout: () => set({ token: null, role: null, user: null }),
}));
