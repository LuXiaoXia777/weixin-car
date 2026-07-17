-- 区分“微信统计日期”与“实际采集时间”。
-- 重复导入时 upsert 会刷新 collected_at，保留最新采集时间。

alter table public.articles
    add column if not exists collected_at timestamptz not null default now();
alter table public.article_stats
    add column if not exists collected_at timestamptz not null default now();
alter table public.user_stats
    add column if not exists collected_at timestamptz not null default now();
alter table public.account_daily_stats
    add column if not exists collected_at timestamptz not null default now();
alter table public.article_channel_stats
    add column if not exists collected_at timestamptz not null default now();

-- 旧兼容表并非所有生产环境都存在，仅在已建表时补充字段。
do $$
begin
    if to_regclass('public.account_content_stats') is not null then
        alter table public.account_content_stats
            add column if not exists collected_at timestamptz not null default now();
    end if;
    if to_regclass('public.article_channels') is not null then
        alter table public.article_channels
            add column if not exists collected_at timestamptz not null default now();
    end if;
end;
$$;

create index if not exists idx_account_daily_stats_latest
    on public.account_daily_stats(account_id, stat_date desc, collected_at desc);
create index if not exists idx_article_stats_latest
    on public.article_stats(stat_date desc, collected_at desc);
