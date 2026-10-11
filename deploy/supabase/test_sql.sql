\set ON_ERROR_STOP on
-- PostgreSQL-only local test stand-ins for Supabase auth (never apply to Supabase).
create role anon;
create role authenticated;
create role service_role;
create schema auth;
create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as
  $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
insert into auth.users values('00000000-0000-0000-0000-000000000001'),('00000000-0000-0000-0000-000000000002');
\i /test/001_bridge.sql
-- Supabase's implicit PUBLIC execute grant must not leak worker methods.
do $$ begin
  assert not has_function_privilege('anon','public.cbh_submit(uuid,text,text,jsonb)','execute');
  assert not has_function_privilege('authenticated','public.cbh_claim(text)','execute');
  assert not has_function_privilege('authenticated','public.cbh_complete(uuid,uuid,int,jsonb)','execute');
  assert not has_table_privilege('authenticated','cbh_private.jobs','select');
  assert not has_table_privilege('anon','cbh_private.jobs','insert');
end $$;
set role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',false);
select public.cbh_submit('10000000-0000-0000-0000-000000000001','POST','/walk/sessions','{}');
select public.cbh_submit('10000000-0000-0000-0000-000000000001','POST','/walk/sessions','{}');
-- Same ID with different body must fail, not create another action.
do $$ begin
  begin
    perform public.cbh_submit('10000000-0000-0000-0000-000000000001','POST','/walk/sessions','{"area_label":"other"}');
    raise exception 'expected mismatch denial';
  exception when invalid_parameter_value then null; end;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000002',false);
do $$ begin
  assert public.cbh_result('10000000-0000-0000-0000-000000000001') is null;
  begin
    perform public.cbh_submit('10000000-0000-0000-0000-000000000001','POST','/walk/sessions','{}');
    raise exception 'expected ownership denial';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
-- Worker claims once. Network loss never makes the claimed request eligible again.
set role service_role;
select public.cbh_claim('compute')->>'id' as claimed;
do $$ begin assert public.cbh_claim('compute') is null; end $$;
reset role;
update cbh_private.jobs set lease_until=now()-interval '1 second';
set role service_role;
select public.cbh_sweep();
do $$ begin assert public.cbh_claim('compute') is null; end $$;
reset role;
do $$ begin assert (select state from cbh_private.jobs limit 1)='interrupted'; end $$;
-- Expiration removes request/result content even if no worker is running.
update cbh_private.jobs set expires_at=now()-interval '1 second';
select public.cbh_sweep();
do $$ begin
  assert (select body is null and result is null and path='/expired' from cbh_private.jobs limit 1);
end $$;
select 'PASS: owner isolation, worker privilege, idempotency, lease expiry, retention' as result;
