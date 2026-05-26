-- P1-3: post_market_job_status 状态表
-- 统一记录每日复盘各阶段任务状态，前端和调度层不再靠日志判断

create table if not exists post_market_job_status (
    id bigserial primary key,
    trade_date date not null,
    job_key text not null,
    status text not null,
    started_at timestamptz,
    finished_at timestamptz,
    error_code text,
    error_message text,
    diagnostics jsonb default '{}'::jsonb,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (trade_date, job_key)
);

create index if not exists idx_post_market_job_status_trade_date
on post_market_job_status (trade_date);

create index if not exists idx_post_market_job_status_job_key
on post_market_job_status (job_key);
