-- Supabase 后台导入服务权限修复。
-- 本迁移不关闭 RLS；service_role 是 Supabase 内置的 BYPASSRLS 角色，
-- 但仍需要明确的表级权限才能访问被所有者收紧权限的表。

grant select, insert, update, delete
on table
    public.wechat_accounts,
    public.articles,
    public.article_stats,
    public.user_stats,
    public.import_runs,
    public.sync_runs
to service_role;

-- 保持生产后台模式：前端角色不直接访问业务表。
revoke all privileges
on table
    public.wechat_accounts,
    public.articles,
    public.article_stats,
    public.user_stats,
    public.import_runs,
    public.sync_runs
from anon, authenticated;

-- 确认 RLS 仍处于开启状态。
alter table public.wechat_accounts enable row level security;
alter table public.articles enable row level security;
alter table public.article_stats enable row level security;
alter table public.user_stats enable row level security;
alter table public.import_runs enable row level security;
alter table public.sync_runs enable row level security;

-- 执行后可在 SQL Editor 中运行以下查询检查 service_role 的 RLS 绕过属性：
-- select rolname, rolbypassrls from pg_roles where rolname = 'service_role';
