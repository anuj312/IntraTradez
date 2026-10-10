-- Trend Hunter Black Label Lifetime Membership
-- Run once in Supabase Dashboard > SQL Editor.
-- Sensitive writes are exclusively from the trusted Render backend using
-- SUPABASE_SERVICE_ROLE_KEY; service_role must NEVER be exposed in the browser.
create table if not exists public.th_memberships (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  full_name text not null default '',
  status text not null default 'pending' check (status in ('pending','active','blocked')),
  paid_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint active_requires_payment check (status <> 'active' or paid_at is not null)
);
create unique index if not exists th_memberships_email_idx on public.th_memberships (lower(email));

create table if not exists public.th_payment_orders (
  order_id text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  payment_id text unique,
  amount_paise integer not null check (amount_paise = 499900),
  currency text not null check (currency = 'INR'),
  status text not null default 'created' check (status in ('created','paid')),
  created_at timestamptz not null default now()
);
create index if not exists th_payment_orders_user_idx on public.th_payment_orders (user_id);

alter table public.th_memberships enable row level security;
alter table public.th_payment_orders enable row level security;
-- No client policies: anon/authenticated clients cannot read or modify either table.
revoke all on public.th_memberships from anon, authenticated;
revoke all on public.th_payment_orders from anon, authenticated;
