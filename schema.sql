-- GhostSee (aiogram) — выполни целиком в Supabase → SQL Editor. Таблицы с префиксом gs_ (со старой версией не конфликтуют).
create table if not exists gs_users (
  tg_id bigint primary key,
  first_name text, username text,
  created_at timestamptz default now(),
  sub_until timestamptz,
  banned boolean default false,
  partner_code text,
  disc_m3 int default 0, disc_y1 int default 0,
  last_roulette timestamptz,
  settings jsonb default '{}'::jsonb,
  last_notice timestamptz,
  warned_exp boolean default false
);
create index if not exists gs_users_username on gs_users (lower(username));

create table if not exists gs_referrals (
  referred_id bigint primary key,
  referrer_id bigint not null,
  status text default 'pending',     -- pending | credited
  bonus_days int default 0,
  created_at timestamptz default now(),
  credited_at timestamptz
);
create index if not exists gs_ref_referrer on gs_referrals (referrer_id);

create table if not exists gs_partners (
  code text primary key,
  tg_id bigint not null,
  percent int not null default 10,
  paid int not null default 0,
  created_at timestamptz default now()
);

create table if not exists gs_payments (
  id bigserial primary key,
  tg_id bigint, plan text,
  stars int, base_stars int,
  charge_id text unique,
  partner_code text, partner_share int default 0,
  created_at timestamptz default now()
);

create table if not exists gs_logs (
  id bigserial primary key,
  ts timestamptz default now(),
  level text, event text, tg_id bigint,
  details jsonb
);
create index if not exists gs_logs_ts on gs_logs (ts desc);

create table if not exists gs_conns (
  id text primary key,
  owner_id bigint, user_chat_id bigint,
  enabled boolean default true,
  first_name text, last_name text, username text
);

create table if not exists gs_msgs (
  bc text, chat_id bigint, msg_id bigint,
  owner_id bigint, data jsonb,
  ts timestamptz default now(),
  primary key (bc, chat_id, msg_id)
);
create index if not exists gs_msgs_ts on gs_msgs (ts);

create table if not exists gs_chat (
  bc text, chat_id bigint, data jsonb default '{}'::jsonb,
  primary key (bc, chat_id)
);

create table if not exists gs_jobs (
  id bigserial primary key,
  run_at timestamptz, kind text, payload jsonb
);
create index if not exists gs_jobs_run on gs_jobs (run_at);

alter table gs_users enable row level security;
alter table gs_referrals enable row level security;
alter table gs_partners enable row level security;
alter table gs_payments enable row level security;
alter table gs_logs enable row level security;
alter table gs_conns enable row level security;
alter table gs_msgs enable row level security;
alter table gs_chat enable row level security;
alter table gs_jobs enable row level security;

-- Таблица для привязки юзера к топику форума
CREATE TABLE IF NOT EXISTS user_topics (
    user_id BIGINT PRIMARY KEY,
    thread_id INTEGER,
    username TEXT,
    full_name TEXT
);

-- Временный буфер для отслеживания удалений/правок (очищается раз в 15 минут)
CREATE TABLE IF NOT EXISTS temp_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_connection_id TEXT,
    message_id BIGINT,
    chat_id BIGINT,
    sender_id BIGINT,
    text TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
