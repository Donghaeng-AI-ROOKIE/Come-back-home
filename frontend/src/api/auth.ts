/**
 * 계정 API — 아이디/비밀번호.
 *
 * 비밀번호는 이 파일을 지나 서버로만 간다. 기기에 저장하지 않고(authStore 는
 * 토큰만 남긴다) 로그에도 찍지 않는다.
 */
import { api } from './config';

export type AuthResult = {
  token: string;
  user_id: string;
  login_id: string;
  role: 'citizen' | 'guardian';
};

export function signup(loginId: string, password: string, role: 'citizen' | 'guardian') {
  return api<AuthResult>('/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ login_id: loginId, password, role }),
  });
}

export function login(loginId: string, password: string) {
  return api<AuthResult>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ login_id: loginId, password }),
  });
}

/** 저장해 둔 토큰이 아직 유효한가 — 앱 재시작 때 확인한다. */
export function me(token: string) {
  return api<AuthResult>('/auth/me', { headers: { Authorization: `Bearer ${token}` } });
}

export function logout(token: string) {
  return api<{ ok: boolean }>('/auth/logout', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
}
