-- Trend Hunter: Google Login Only (no payment gateway)
-- Supabase > SQL Editor > New Query > Run
-- Run once. New Google users are added by the trusted Render server.
-- Pending is a non-paying login record, NOT a paid/lifetime entitlement.
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

alter table public.th_memberships enable row level security;
-- Browser users cannot edit membership status; only Render's trusted backend writes.
revoke all on public.th_memberships from anon, authenticated;
-- No public RLS policies. Service-role backend may read/create profiles.
