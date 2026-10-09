create extension if not exists pg_cron;
select cron.schedule('cbh-bridge-retention','* * * * *','select public.cbh_sweep()');
