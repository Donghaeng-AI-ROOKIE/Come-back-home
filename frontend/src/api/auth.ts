/**
 * 계정 API — 아이디/비밀번호.
 *
 * 비밀번호는 이 파일을 지나 서버로만 간다. 기기에 저장하지 않고(authStore 는
 * 토큰만 남긴다) 로그에도 찍지 않는다.
 */
import { api, USE_MOCK } from './config';

export type AuthResult = {
  token: string;
  user_id: string;
  login_id: string;
  role: 'citizen' | 'guardian';
};

const MOCK_TOKEN_PREFIX = 'mock-auth:';

function mockAuthResult(loginId: string, role: AuthResult['role']): AuthResult {
  const safeLoginId = loginId.trim() || `${role}@preview.local`;
  return {
    token: `${MOCK_TOKEN_PREFIX}${role}:${encodeURIComponent(safeLoginId)}`,
    user_id: `mock-${role}-${encodeURIComponent(safeLoginId)}`,
    login_id: safeLoginId,
    role,
  };
}

function parseMockToken(token: string): AuthResult | null {
  if (!token.startsWith(MOCK_TOKEN_PREFIX)) return null;
  const [role, encodedLoginId] = token.slice(MOCK_TOKEN_PREFIX.length).split(':', 2);
  if ((role !== 'citizen' && role !== 'guardian') || !encodedLoginId) return null;
  return mockAuthResult(decodeURIComponent(encodedLoginId), role);
}

function mockLoginRole(loginId: string): AuthResult['role'] {
  return /guardian|protector|보호자/i.test(loginId) ? 'guardian' : 'citizen';
}

export function signup(loginId: string, password: string, role: 'citizen' | 'guardian') {
  if (USE_MOCK) return Promise.resolve(mockAuthResult(loginId, role));
  return api<AuthResult>('/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ login_id: loginId, password, role }),
  });
}

export function login(loginId: string, password: string) {
  if (USE_MOCK) return Promise.resolve(mockAuthResult(loginId, mockLoginRole(loginId)));
  return api<AuthResult>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ login_id: loginId, password }),
  });
}

/** 저장해 둔 토큰이 아직 유효한가 — 앱 재시작 때 확인한다. */
export function me(token: string) {
  if (USE_MOCK) {
    const result = parseMockToken(token);
    return result ? Promise.resolve(result) : Promise.reject(new Error('미리보기 토큰이 올바르지 않습니다.'));
  }
  return api<AuthResult>('/auth/me', { headers: { Authorization: `Bearer ${token}` } });
}

export function logout(token: string) {
  if (USE_MOCK) return Promise.resolve({ ok: true });
  return api<{ ok: boolean }>('/auth/logout', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
}

/** 로그인한 계정의 역할 변경 — 보호자↔시민. 기록은 user_id 에 붙어 그대로 남는다. */
export function changeRole(token: string, role: 'citizen' | 'guardian') {
  if (USE_MOCK) {
    const current = parseMockToken(token);
    return current
      ? Promise.resolve(mockAuthResult(current.login_id, role))
      : Promise.reject(new Error('미리보기 토큰이 올바르지 않습니다.'));
  }
  return api<AuthResult>('/auth/role', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ role }),
  });
}
