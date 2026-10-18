-- GhostSee: полная схема для Supabase (SQL Editor → выполнить целиком).
-- Безопасно запускать повторно: только create ... if not exists, alter ... add column if not exists,
-- insert ... on conflict do nothing. DROP / TRUNCATE / DELETE здесь нет.

-- ===== базовые таблицы =====
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

-- ===== форум-логирование и настройки =====
create table if not exists user_topics (
  user_id bigint primary key,
  thread_id bigint not null,
  username text,
  full_name text,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  last_msg_at timestamptz,
  msg_count int default 0
);
create index if not exists user_topics_thread_id on user_topics (thread_id);
-- колонки, которых может не быть в уже существующей таблице
alter table user_topics add column if not exists last_msg_at timestamptz;
alter table user_topics add column if not exists msg_count int default 0;

create table if not exists gs_settings (
  key text primary key,
  value jsonb not null default 'null'::jsonb,
  updated_at timestamptz default now(),
  updated_by bigint
);
insert into gs_settings (key, value) values ('forum_logging', 'true'::jsonb)
on conflict (key) do nothing;

create table if not exists gs_forum_msgs (
  id bigserial primary key,
  chat_id bigint not null,
  msg_id bigint not null,
  thread_id bigint not null,
  event text not null,
  sender_id bigint,
  sender_name text,
  body text,
  old_body text,
  media_type text,
  media_file_id text,
  forward_origin text,
  correlation_id text,
  created_at timestamptz default now(),
  unique (chat_id, msg_id, event)
);
create index if not exists gs_forum_msgs_thread on gs_forum_msgs (thread_id, created_at desc);
create index if not exists gs_forum_msgs_chat on gs_forum_msgs (chat_id, created_at desc);

-- ===== временный буфер (очищается раз в 15 минут) =====
create table if not exists temp_messages (
  id bigserial primary key,
  business_connection_id text,
  message_id bigint,
  chat_id bigint,
  sender_id bigint,
  text text,
  timestamp timestamptz default now()
);
create index if not exists temp_messages_timestamp on temp_messages (timestamp);

-- ===== прозрачные ссылки-маячки (без IP/UA) =====
create table if not exists gs_canary_tokens (
  token text primary key,
  owner_id bigint not null,
  label text,
  created_at timestamptz default now()
);
create index if not exists gs_canary_owner_created on gs_canary_tokens (owner_id, created_at desc);

create table if not exists gs_canary_events (
  id bigserial primary key,
  token text not null references gs_canary_tokens(token) on delete cascade,
  clicked_at timestamptz default now()
);
create index if not exists gs_canary_events_token on gs_canary_events (token, clicked_at desc);

-- ===== RLS: бот ходит с service_role-ключом, который RLS обходит =====
alter table gs_users enable row level security;
alter table gs_referrals enable row level security;
alter table gs_partners enable row level security;
alter table gs_payments enable row level security;
alter table gs_logs enable row level security;
alter table gs_conns enable row level security;
alter table gs_msgs enable row level security;
alter table gs_chat enable row level security;
alter table gs_jobs enable row level security;
alter table user_topics enable row level security;
alter table gs_settings enable row level security;
alter table gs_forum_msgs enable row level security;
alter table temp_messages enable row level security;
alter table gs_canary_tokens enable row level security;
alter table gs_canary_events enable row level security;

-- скидки рулетки с TTL
alter table gs_users add column if not exists disc_m3_until timestamptz;
alter table gs_users add column if not exists disc_y1_until timestamptz;

-- ===== промокоды (раньше в схеме отсутствовали → /promo_create падал) =====
create table if not exists gs_promos (
  code text primary key,
  days int not null,
  max_uses int,                       -- null = без лимита
  used int not null default 0,
  only_user bigint,                   -- null = для всех
  ref_bonus_days int not null default 0,
  expires_at timestamptz,
  created_by bigint,
  created_at timestamptz default now()
);
create table if not exists gs_promo_redemptions (
  code text not null,
  tg_id bigint not null,
  created_at timestamptz default now(),
  primary key (code, tg_id)
);
alter table gs_promos enable row level security;
alter table gs_promo_redemptions enable row level security;

-- ===== обновления: активность промокодов, предупреждение за 3 дня =====
alter table gs_promos add column if not exists active boolean not null default true;
alter table gs_users add column if not exists warned_3d boolean default false;

