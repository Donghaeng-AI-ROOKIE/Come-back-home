-- Receipt-only tips must not queue behind inference. The endpoint enforces
-- durable saving and delegates all model/map work to its bounded worker.
begin;
create or replace function cbh_private.route_tip_receipt_job()
returns trigger language plpgsql set search_path='' as $$
begin
  if new.method='POST' and new.path ~ '^/phase3/cases/[\w-]+/tips$'
     and new.body->'background_analysis'='true'::jsonb then
    new.lane := 'read';
  end if;
  return new;
end $$;
revoke all on function cbh_private.route_tip_receipt_job() from public,anon,authenticated;
create or replace trigger route_tip_receipt_before_insert
before insert on cbh_private.jobs for each row execute function cbh_private.route_tip_receipt_job();
commit;
select 'tip_receipt_read_lane_ready' as result;
-- Rollback: drop trigger route_tip_receipt_before_insert on cbh_private.jobs;
