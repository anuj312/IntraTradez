-- Trend Hunter Black Label — Razorpay Test Mode ONLY
-- Run in Supabase > SQL Editor AFTER SUPABASE_GOOGLE_ONLY_SETUP.sql.
-- All test purchases are recorded separately from public.th_memberships and
-- public.th_payment_orders; switching to production does NOT grant paid access.
create table if not exists public.th_test_memberships (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  full_name text not null default '',
  status text not null default 'pending' check (status in ('pending','active','blocked')),
  paid_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint test_active_requires_payment check (status <> 'active' or paid_at is not null)
);
create unique index if not exists th_test_memberships_email_idx on public.th_test_memberships (lower(email));

create table if not exists public.th_test_payment_orders (
  order_id text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  payment_id text unique,
  amount_paise integer not null check (amount_paise = 499900),
  currency text not null check (currency = 'INR'),
  status text not null default 'created' check (status in ('created','paid')),
  created_at timestamptz not null default now()
);
create index if not exists th_test_orders_user_idx on public.th_test_payment_orders (user_id);

alter table public.th_test_memberships enable row level security;
alter table public.th_test_payment_orders enable row level security;
revoke all on public.th_test_memberships from anon, authenticated;
revoke all on public.th_test_payment_orders from anon, authenticated;
-- No public access policies. Only the trusted Render backend can write with
-- the service-role credential (never expose this credential in the browser).
