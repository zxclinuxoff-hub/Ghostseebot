-- GhostSee wheel/crash concurrency hardening.
-- Run this file in Supabase SQL Editor AFTER the existing wheel_schema.sql.

create or replace function public.gs_wheel_admin_add(p_tg_id bigint, p_amount integer)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare v_bonus integer;
begin
  insert into public.gs_wheel (tg_id, shards, bonus_spins, credits, spins_today, streak)
  values (p_tg_id, 0, 0, 0, 0, 0)
  on conflict (tg_id) do nothing;
  update public.gs_wheel
     set bonus_spins = greatest(0, coalesce(bonus_spins, 0) + p_amount)
   where tg_id = p_tg_id
   returning bonus_spins into v_bonus;
  return jsonb_build_object('bonus_spins', v_bonus);
end;
$$;

create or replace function public.gs_wheel_spend(p_tg_id bigint, p_kind text, p_n integer default 1)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v public.gs_wheel%rowtype;
  v_free integer := 0;
  v_paid integer := 0;
  v_today date := (now() at time zone 'utc')::date;
begin
  if p_n < 1 or p_n > 10 or p_kind not in ('free', 'credit', 'multi') then
    raise exception 'BAD_REQUEST' using errcode = '22023';
  end if;
  insert into public.gs_wheel (tg_id, shards, bonus_spins, credits, spins_today, day, streak)
  values (p_tg_id, 0, 0, 0, 0, v_today, 0)
  on conflict (tg_id) do nothing;
  select * into v from public.gs_wheel where tg_id = p_tg_id for update;
  if v.day is distinct from v_today then
    v.spins_today := 0;
    v.day := v_today;
  end if;
  if p_kind = 'free' then
    if coalesce(v.bonus_spins, 0) < 1 then raise exception 'NO_BONUS' using errcode = 'P0001'; end if;
    v.bonus_spins := v.bonus_spins - 1;
  elsif p_kind = 'credit' then
    if coalesce(v.credits, 0) < 1 then raise exception 'NO_CREDITS' using errcode = 'P0001'; end if;
    if v.spins_today >= 50 then raise exception 'DAILY_LIMIT' using errcode = 'P0001'; end if;
    v.credits := v.credits - 1;
    v.spins_today := v.spins_today + 1;
  else
    v_free := least(coalesce(v.bonus_spins, 0), p_n);
    v_paid := p_n - v_free;
    if coalesce(v.credits, 0) < v_paid then raise exception 'NO_CREDITS' using errcode = 'P0001'; end if;
    if v_paid > greatest(0, 50 - v.spins_today) then raise exception 'DAILY_LIMIT' using errcode = 'P0001'; end if;
    v.bonus_spins := v.bonus_spins - v_free;
    v.credits := v.credits - v_paid;
    v.spins_today := v.spins_today + v_paid;
  end if;
  update public.gs_wheel
     set bonus_spins = v.bonus_spins, credits = v.credits,
         spins_today = v.spins_today, day = v.day
   where tg_id = p_tg_id;
  return jsonb_build_object('free_used', v_free, 'paid_used', v_paid,
                            'bonus_spins', v.bonus_spins, 'credits', v.credits,
                            'spins_today', v.spins_today);
end;
$$;

-- Repair any legacy duplicate active rounds before enforcing the invariant.
with ranked as (
  select id, row_number() over (partition by tg_id order by id desc) as rn
  from public.gs_crash where status = 'active'
)
update public.gs_crash c set status = 'done'
from ranked r where c.id = r.id and r.rn > 1;

-- One active crash round per user, enforced by PostgreSQL even under simultaneous requests.
create unique index if not exists gs_crash_one_active_per_user
  on public.gs_crash (tg_id) where status = 'active';

create or replace function public.gs_crash_start(p_tg_id bigint, p_bet integer, p_point numeric, p_started_at timestamptz)
returns setof public.gs_crash
language plpgsql
security definer
set search_path = public
as $$
declare v public.gs_wheel%rowtype;
        v_free integer;
        v_row public.gs_crash%rowtype;
        v_today date := (now() at time zone 'utc')::date;
begin
  if p_bet < 1 or p_bet > 10 then raise exception 'BAD_BET' using errcode = '22023'; end if;
  insert into public.gs_wheel (tg_id, shards, bonus_spins, credits, spins_today, day, streak)
  values (p_tg_id, 0, 0, 0, 0, v_today, 0)
  on conflict (tg_id) do nothing;
  select * into v from public.gs_wheel where tg_id = p_tg_id for update;
  if exists (select 1 from public.gs_crash where tg_id = p_tg_id and status = 'active') then
    raise exception 'ROUND_ACTIVE' using errcode = 'P0001';
  end if;
  if coalesce(v.bonus_spins, 0) + coalesce(v.credits, 0) < p_bet then
    raise exception 'NO_SPINS' using errcode = 'P0001';
  end if;
  v_free := least(coalesce(v.bonus_spins, 0), p_bet);
  update public.gs_wheel
     set bonus_spins = v.bonus_spins - v_free,
         credits = v.credits - (p_bet - v_free)
   where tg_id = p_tg_id;
  insert into public.gs_crash (tg_id, bet, point, started_at, status, mult, payout)
  values (p_tg_id, p_bet, p_point, p_started_at,
          case when p_point <= 1 then 'crashed' else 'active' end,
          case when p_point <= 1 then 1 else null end, 0)
  returning * into v_row;
  return next v_row;
end;
$$;

revoke all on function public.gs_wheel_admin_add(bigint, integer) from public, anon, authenticated;
revoke all on function public.gs_wheel_spend(bigint, text, integer) from public, anon, authenticated;
revoke all on function public.gs_crash_start(bigint, integer, numeric, timestamptz) from public, anon, authenticated;
grant execute on function public.gs_wheel_admin_add(bigint, integer) to service_role;
grant execute on function public.gs_wheel_spend(bigint, text, integer) to service_role;
grant execute on function public.gs_crash_start(bigint, integer, numeric, timestamptz) to service_role;
