-- Web-push registration/location must not wait behind a multi-minute prediction.
-- Runs only on new jobs; ownership, quotas, leases and RPC grants stay unchanged.
begin;
create or replace function cbh_private.route_webpush_job()
returns trigger language plpgsql set search_path='' as $$
begin
  if (new.method='GET' and new.path='/phase3/webpush/public-key')
     or (new.method='POST' and new.path in (
       '/phase3/webpush/subscription','/phase3/webpush/location',
       '/phase3/webpush/enter','/phase3/webpush/test'))
     or (new.method='DELETE' and new.path='/phase3/webpush/subscription')
     or (new.method='GET' and split_part(new.path,'?',1)='/phase1/cases')
     or (new.method='POST' and new.path ~ '^/phase1/cases/[\w-]+/close$')
     or (new.method='POST' and new.path ~ '^/phase0/personas/[\w-]+/confirm$')
     or (new.method='DELETE' and new.path ~ '^/phase[01]/(personas|cases)/[\w-]+$') then
    new.lane := 'read';
  end if;
  return new;
end $$;
revoke all on function cbh_private.route_webpush_job() from public,anon,authenticated;
create or replace trigger route_webpush_before_insert
before insert on cbh_private.jobs for each row execute function cbh_private.route_webpush_job();
commit;
select 'lifecycle_read_lane_ready' as result;
-- Rollback: drop trigger route_webpush_before_insert on cbh_private.jobs;
