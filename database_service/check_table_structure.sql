-- 连接到数据库
\c financial_ai;

-- 查看表结构
\d theme_master_28_fields;

-- 查看表创建语句
SELECT pg_get_tabledef('theme_master_28_fields');
