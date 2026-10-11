-- New project only. No change to auth.users, no public table access.
-- Apply in Supabase SQL editor as the project owner after local SQL tests.
begin;
create schema if not exists cbh_private;
revoke all on schema cbh_private from public, anon, authenticated;
create table if not exists cbh_private.jobs (
  id uuid primary key,
  owner_id uuid not null references auth.users(id) on delete cascade,
  method text not null check (method in ('GET','POST','PATCH','DELETE')),
  path text not null,
  body jsonb,
  state text not null default 'queued' check (state in ('queued','running','done','interrupted','expired')),
  lane text not null check (lane in ('read','compute')),
  created_at timestamptz not null default now(),
  lease_id uuid, lease_until timestamptz,
  status_code int, result jsonb,
  expires_at timestamptz not null default now() + interval '1 hour',
  forget_at timestamptz not null default now() + interval '7 days'
);
alter table cbh_private.jobs enable row level security;
revoke all on cbh_private.jobs from public, anon, authenticated;
create index if not exists cbh_jobs_claim on cbh_private.jobs(lane,created_at) where state='queued';
create index if not exists cbh_jobs_owner on cbh_private.jobs(owner_id,created_at);

create or replace function public.cbh_submit(p_id uuid, p_method text, p_path text, p_body jsonb default null)
returns uuid language plpgsql security definer set search_path = '' as $$
declare who uuid := auth.uid(); prev cbh_private.jobs; kind text;
begin
  if who is null then raise exception 'login required' using errcode='42501'; end if;
  if p_id is null or p_method not in ('GET','POST','PATCH','DELETE') or p_method is null
     or p_path is null or length(p_path)>2048 or p_path !~ '^/(phase[0-3]|walk|geo)/'
     or p_path ~ '[\\#]' or p_path like '%..%' or p_path like '%//%'
     or octet_length(coalesce(p_body::text,''))>65536
     or (p_body is not null and jsonb_typeof(p_body)<>'object')
     or (p_body is not null and (p_body ?| array['password','Authorization','authorization','api_key'])) then
    raise exception 'invalid request' using errcode='22023';
  end if;
  -- Serialize one user's admissions; prevents parallel requests bypassing quotas.
  perform pg_advisory_xact_lock(hashtextextended(who::text, 0));
  select * into prev from cbh_private.jobs where id=p_id;
  if found then
    if prev.owner_id<>who then raise exception 'request unavailable' using errcode='42501'; end if;
    if prev.state='expired' then raise exception 'request expired' using errcode='22023'; end if;
    if prev.method<>p_method or prev.path<>p_path or prev.body is distinct from p_body then
      raise exception 'request ID already used' using errcode='22023';
    end if;
    return p_id;
  end if;
  if (select count(*) from cbh_private.jobs where owner_id=who and state in ('queued','running'))>=8
     or (select count(*) from cbh_private.jobs where owner_id=who and created_at>now()-interval '1 minute')>=60
     or (select count(*) from cbh_private.jobs where state in ('queued','running'))>=200 then
    raise exception 'queue busy' using errcode='53300';
  end if;
  kind := case when p_method='GET' and
    (p_path ~ '^/walk/' or p_path ~ '^/phase0/' or p_path ~ '^/phase1/cases/' or p_path ~ '^/phase3/alerts')
    then 'read' else 'compute' end;
  insert into cbh_private.jobs(id,owner_id,method,path,body,lane)
    values(p_id,who,p_method,p_path,p_body,kind);
  return p_id;
end $$;

create or replace function public.cbh_result(p_id uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare j cbh_private.jobs;
begin
  if auth.uid() is null then raise exception 'login required' using errcode='42501'; end if;
  select * into j from cbh_private.jobs where id=p_id and owner_id=auth.uid();
  if not found then return null; end if;
  if j.expires_at<=now() then return jsonb_build_object('state','expired'); end if;
  return jsonb_build_object('state',j.state,'status_code',j.status_code,'result',j.result);
end $$;

-- Lease expiry means uncertain execution, NOT permission to run again.
create or replace function public.cbh_sweep()
returns void language plpgsql security definer set search_path='' as $$
begin
  update cbh_private.jobs set state='interrupted',status_code=503,
    result='{"detail":"서버 연결이 끊겨 완료 여부를 확인할 수 없습니다. 기록을 확인해 주세요."}'::jsonb
    where state='running' and lease_until<now();
  update cbh_private.jobs set state='expired',body=null,result=null,path='/expired',lease_id=null
    where expires_at<=now() and state<>'expired';
  delete from cbh_private.jobs where forget_at<=now();
end $$;

create or replace function public.cbh_claim(p_lane text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare j cbh_private.jobs;
begin
  perform public.cbh_sweep();
  select * into j from cbh_private.jobs where state='queued' and lane=p_lane
    order by created_at for update skip locked limit 1;
  if not found then return null; end if;
  update cbh_private.jobs set state='running',lease_id=gen_random_uuid(),lease_until=now()+interval '120 seconds'
    where id=j.id returning * into j;
  return to_jsonb(j);
end $$;
create or replace function public.cbh_heartbeat(p_id uuid,p_lease uuid)
returns boolean language plpgsql security definer set search_path='' as $$
begin
  update cbh_private.jobs set lease_until=now()+interval '120 seconds'
    where id=p_id and lease_id=p_lease and state='running' and lease_until>now();
  return found;
end $$;
create or replace function public.cbh_complete(p_id uuid,p_lease uuid,p_status int,p_result jsonb)
returns boolean language plpgsql security definer set search_path='' as $$
begin
  if p_status<100 or p_status>599 or octet_length(coalesce(p_result::text,''))>2097152 then
    raise exception 'invalid result' using errcode='22023';
  end if;
  update cbh_private.jobs set state='done',status_code=p_status,result=p_result,
    expires_at=least(expires_at,now()+interval '20 minutes')
    where id=p_id and lease_id=p_lease and state='running' and lease_until>now();
  if found then return true; end if;
  -- A lost acknowledgement may resend the SAME completion; never rerun the API.
  return exists(select 1 from cbh_private.jobs where id=p_id and lease_id=p_lease and state='done');
end $$;
revoke all on function public.cbh_submit(uuid,text,text,jsonb) from public,anon,authenticated;
revoke all on function public.cbh_result(uuid) from public,anon,authenticated;
revoke all on function public.cbh_sweep() from public,anon,authenticated;
revoke all on function public.cbh_claim(text) from public,anon,authenticated;
revoke all on function public.cbh_heartbeat(uuid,uuid) from public,anon,authenticated;
revoke all on function public.cbh_complete(uuid,uuid,int,jsonb) from public,anon,authenticated;
grant execute on function public.cbh_submit(uuid,text,text,jsonb),public.cbh_result(uuid) to authenticated;
grant execute on function public.cbh_claim(text),public.cbh_sweep(),public.cbh_heartbeat(uuid,uuid),
  public.cbh_complete(uuid,uuid,int,jsonb) to service_role;
commit;
-- Enable pg_cron and schedule cbh_sweep every minute BEFORE enabling the worker.
-- Worker shutdown must not stop retention. See 002_retention.sql.
