\c stock_data;

-- 查看所有表
\dt

-- 查看表结构（如果有theme_master表）
\dt+ theme_master;

-- 查看字段详细信息
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    character_maximum_length,
    column_default
FROM information_schema.columns 
WHERE table_name = 'theme_master'
ORDER BY ordinal_position;

-- 查看表创建时间等信息
SELECT 
    schemaname,
    tablename,
    tableowner,
    tablespace,
    hasindexes,
    hasrules,
    hastriggers
FROM pg_tables 
WHERE tablename = 'theme_master';

-- 查看索引
SELECT 
    indexname,
    indexdef
FROM pg_indexes 
WHERE tablename = 'theme_master';
