/** Only the publishable/anon key belongs in the web bundle. Never a service key. */
import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js';
import { safeStorage } from '../store/safeStorage';
import type { AuthResult } from './auth';

export const CLOUD_TRANSPORT = process.env.EXPO_PUBLIC_TRANSPORT === 'supabase';
let singleton: SupabaseClient | null = null;
export function supabase() {
  if (singleton) return singleton;
  const url = process.env.EXPO_PUBLIC_SUPABASE_URL;
  const key = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) throw new Error('로그인 서버 연결을 준비 중입니다.');
  if (key.startsWith('sb_secret_')) throw new Error('서버 전용 키는 앱에 사용할 수 없습니다.');
  if (!/^https:\/\/[a-z0-9]+\.supabase\.co\/?$/.test(url)) throw new Error('로그인 서버 주소를 확인해 주세요.');
  singleton = createClient(url, key, {
    auth: { storage: safeStorage, persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    global: { fetch: (input, init) => fetch(input, {
      ...init, signal: init?.signal ?? AbortSignal.timeout(15_000),
    }) },
  });
  return singleton;
}

function result(session: Session): AuthResult {
  return { token: session.access_token, user_id: session.user.id,
    login_id: session.user.email ?? '',
    role: session.user.user_metadata?.role === 'guardian' ? 'guardian' : 'citizen' };
}
export async function cloudMe(): Promise<AuthResult> {
  const { data, error } = await supabase().auth.getSession();
  if (error || !data.session) throw new Error('다시 로그인해 주세요.');
  return result(data.session);
}
export async function cloudLogin(email: string, password: string) {
  const { data, error } = await supabase().auth.signInWithPassword({ email: email.trim(), password });
  if (error) throw new Error(error.message);
  return result(data.session);
}
export async function cloudSignup(email: string, password: string, role: AuthResult['role']) {
  const { data, error } = await supabase().auth.signUp({email: email.trim(), password, options:{data:{role}}});
  if (error) throw new Error(error.message);
  // Do not claim login succeeded or disable confirmation when email verification is required.
  if (!data.session) throw new Error('가입 확인 메일을 보냈습니다. 메일에서 확인한 뒤 로그인해 주세요.');
  return result(data.session);
}
export async function cloudLogout() {
  const { error } = await supabase().auth.signOut({ scope: 'local' });
  if (error) throw error;
  return {ok: true};
}
export async function cloudRole(role: AuthResult['role']) {
  const { error } = await supabase().auth.updateUser({ data: { role } });
  if (error) throw error;
  // This metadata selects a screen only. The worker derives all access from user UUID.
  return cloudMe();
}
