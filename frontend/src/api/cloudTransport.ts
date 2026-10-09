import { ApiError } from './config';
import { cloudMe, supabase } from './supabase';
import { safeStorage } from '../store/safeStorage';

const pending = new Map<string, Promise<unknown>>();
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

/** One request ID survives page reload/timeouts. Retry resumes lookup, never execution. */
export async function cloudRequest<T>(path: string, init?: RequestInit & {timeoutMs?: number}): Promise<T> {
  const owner = (await cloudMe()).user_id;
  const method = (init?.method ?? 'GET').toUpperCase();
  const body = init?.body ? JSON.parse(String(init.body)) : null;
  if (path.startsWith('/auth/')) throw new ApiError(400,path,'비밀번호 요청은 작업 목록에 저장할 수 없습니다.');
  // Install the in-flight guard BEFORE asynchronous hashing. Otherwise a fast
  // first response can finish while the second click is still hashing its key.
  const identity = JSON.stringify([owner,method,path,body]);
  if (pending.has(identity)) return pending.get(identity) as Promise<T>;
  const promise = (async () => {
    const digest = await crypto.subtle.digest('SHA-256',new TextEncoder().encode(identity));
    const key = 'cbh-pending:'+Array.from(new Uint8Array(digest),n=>n.toString(16).padStart(2,'0')).join('');
    return run<T>(key,path,method,body,init?.timeoutMs ?? 30_000, init?.signal);
  })();
  pending.set(identity,promise);
  try { return await promise; } finally { pending.delete(identity); }
}

async function run<T>(key:string,path:string,method:string,body:unknown,timeout:number,signal?:AbortSignal|null): Promise<T> {
  const db = supabase();
  const saved = await safeStorage.getItem(key);
  const resume = Boolean(saved);
  // Old versions stored a bare UUID. They may still retrieve a result, but may
  // not resubmit it: without its creation time the deduplication retention is unknown.
  let id: string;
  let createdAt: number | null = null;
  if (saved) {
    try {
      const record = JSON.parse(saved);
      if (typeof record.id !== 'string' || !Number.isFinite(record.createdAt)) throw new Error('invalid pending record');
      id = record.id;
      createdAt = record.createdAt;
    } catch { id = saved; }
  } else {
    id = crypto.randomUUID();
    createdAt = Date.now();
    await safeStorage.setItem(key,JSON.stringify({id,createdAt}));
  }
  const until = Date.now()+timeout;
  // If submit was accepted but the reply was lost, a repeat uses the SAME UUID.
  // If the original row cannot be found after a reload, never silently invent a new ID.
  async function submit() {
    const { error } = await db.rpc('cbh_submit',{p_id:id,p_method:method,p_path:path,p_body:body});
    if (error && error.code && !['PGRST000','PGRST001','PGRST002'].includes(error.code)) {
      await safeStorage.removeItem(key);
      throw new ApiError(503,path,error.message);
    }
  }
  if (!resume) await submit();
  let recoveredSubmission = false;
  while (Date.now()<until && !signal?.aborted) {
    const { data, error } = await db.rpc('cbh_result',{p_id:id});
    // A disconnected browser can persist an ID before Supabase receives it.
    // Resend that SAME ID once only when the owner lookup confirms no row. A
    // competing/late original insert is deduplicated atomically by cbh_submit.
    // Limit recovery to two hours, well inside the server's seven-day ID retention.
    if (resume && !error && data === null && !recoveredSubmission) {
      const age = createdAt === null ? Infinity : Date.now()-createdAt;
      if (age < 0 || age > 2*60*60*1000) {
        throw new ApiError(503,path,'오래된 요청의 완료 여부를 확인할 수 없습니다. 기록을 확인해 주세요. 요청 '+id.slice(0,8));
      }
      recoveredSubmission = true;
      await submit();
      continue;
    }
    if (!error && data?.state === 'done') {
      await safeStorage.removeItem(key);
      if (data.status_code >= 400) throw new ApiError(data.status_code,path,
        data.result?.detail ?? '요청을 처리하지 못했습니다.');
      return data.result as T;
    }
    if (!error && ['interrupted','expired'].includes(data?.state)) {
      // Retain UUID so clicking the button again cannot repeat uncertain AI work.
      throw new ApiError(503,path,'완료 여부를 확인할 수 없습니다. 기록을 확인해 주세요. 요청 '+id.slice(0,8));
    }
    await sleep(method === 'GET' ? 1000 : 1500);
  }
  throw new ApiError(0,path,'처리가 지연되고 있습니다. 다시 누르면 같은 요청의 결과를 확인합니다. 요청 '+id.slice(0,8));
}
