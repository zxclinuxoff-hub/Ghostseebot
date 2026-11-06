-- Колесо фортуны. Запусти в SQL Editor Supabase (безопасно запускать повторно).
create table if not exists gs_wheel (
  tg_id bigint primary key,
  shards int default 0,
  bonus_spins int default 0,
  spins_today int default 0,
  day date,
  vip_until timestamptz
);
create table if not exists gs_wheel_log (
  id bigserial primary key,
  tg_id bigint not null,
  prize text not null,
  paid boolean default true,
  charge_id text unique,
  note text,
  ts timestamptz default now()
);
create index if not exists gs_wheel_log_tg on gs_wheel_log (tg_id, id desc);
alter table gs_wheel enable row level security;
alter table gs_wheel_log enable row level security;
grant all on gs_wheel, gs_wheel_log to service_role;
grant usage, select on sequence gs_wheel_log_id_seq to service_role;

-- Обновление: серия дней, купленные прокруты (запусти, даже если таблицы уже созданы)
alter table gs_wheel add column if not exists credits int default 0;
alter table gs_wheel add column if not exists streak int default 0;
alter table gs_wheel add column if not exists last_visit date;

-- Самолётик (Crash)
create table if not exists gs_crash (
  id bigserial primary key,
  tg_id bigint not null,
  bet int not null,
  point numeric not null,
  started_at timestamptz not null default now(),
  status text not null default 'active',
  mult numeric,
  payout int
);
create index if not exists gs_crash_user on gs_crash (tg_id, status);
alter table gs_crash enable row level security;
grant all on gs_crash to service_role;
grant usage, select on sequence gs_crash_id_seq to service_role;
