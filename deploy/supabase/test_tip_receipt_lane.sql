\set ON_ERROR_STOP on
-- PostgreSQL-only local test stand-ins for Supabase auth (never apply to Supabase).
-- Run: docker run --rm -v "$PWD":/test postgres:17 ... psql -f /test/test_tip_receipt_lane.sql
create role anon;
create role authenticated;
create role service_role;
create schema auth;
create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as
  $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
insert into auth.users values('00000000-0000-0000-0000-000000000001');
\i /test/001_bridge.sql
\i /test/004_webpush_read_lane.sql
\i /test/005_lifecycle_read_lane.sql
\i /test/006_tip_receipt_read_lane.sql
do $$ begin
  assert not has_function_privilege('authenticated','cbh_private.route_tip_receipt_job()','execute');
end $$;
set role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',false);
-- Receipt-only tip: saved without model or map work, so it must not wait behind predictions.
select public.cbh_submit('20000000-0000-0000-0000-000000000001','POST','/phase3/cases/abc123/tips',
  '{"text":"합성 제보","background_analysis":true,"submission_id":"receipt-1"}');
-- Older clients without the flag still analyse inline and stay on the compute lane.
select public.cbh_submit('20000000-0000-0000-0000-000000000002','POST','/phase3/cases/abc123/tips',
  '{"text":"합성 제보"}');
select public.cbh_submit('20000000-0000-0000-0000-000000000003','POST','/phase3/cases/abc123/tips',
  '{"text":"합성 제보","background_analysis":false}');
-- Other routes keep their lanes.
select public.cbh_submit('20000000-0000-0000-0000-000000000004','POST','/phase2/cases/abc123/predict','{"background_analysis":true}');
select public.cbh_submit('20000000-0000-0000-0000-000000000005','GET','/phase3/alerts?target_cell=x',null);
select public.cbh_submit('20000000-0000-0000-0000-000000000006','POST','/phase3/webpush/location','{}');
reset role;
do $$ begin
  assert (select lane from cbh_private.jobs where id='20000000-0000-0000-0000-000000000001')='read';
  assert (select lane from cbh_private.jobs where id='20000000-0000-0000-0000-000000000002')='compute';
  assert (select lane from cbh_private.jobs where id='20000000-0000-0000-0000-000000000003')='compute';
  assert (select lane from cbh_private.jobs where id='20000000-0000-0000-0000-000000000004')='compute';
  assert (select lane from cbh_private.jobs where id='20000000-0000-0000-0000-000000000005')='read';
  assert (select lane from cbh_private.jobs where id='20000000-0000-0000-0000-000000000006')='read';
end $$;
select 'PASS: receipt-only tips on the read lane, other routes unchanged' as result;
