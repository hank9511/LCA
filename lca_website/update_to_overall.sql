-- 将所有包含"life cycle"或相关关键词的过程更新为"总体环节"
-- 
-- 使用方法：
-- cd /Users/haizhou/Downloads/OpenLCA_1017_1113/lca_website
-- sqlite3 lca_website.db < update_to_overall.sql

-- 显示更新前的状态
.mode column
.headers on
.width 50 20 20

SELECT '===== 更新前的状态 =====' as info;
SELECT '' as info;

SELECT 
    process_name,
    lifecycle_stage as current_stage,
    'overall' as new_stage
FROM process_lifecycle_stage
WHERE 
    LOWER(process_name) LIKE '%life cycle%'
    OR LOWER(process_name) LIKE '%lifecycle%'
    OR LOWER(process_name) LIKE '%lca%'
    OR LOWER(process_name) LIKE '%system%'
    OR LOWER(process_name) LIKE '%overall%'
    OR LOWER(process_name) LIKE '%complete%'
    OR process_name LIKE '%全生命周期%'
    OR process_name LIKE '%整体%'
    OR process_name LIKE '%系统%';

SELECT '' as info;
SELECT '===== 开始更新 =====' as info;

-- 执行更新
UPDATE process_lifecycle_stage
SET 
    lifecycle_stage = 'overall',
    llm_reasoning = '自动更新为总体环节（基于关键词识别）'
WHERE 
    LOWER(process_name) LIKE '%life cycle%'
    OR LOWER(process_name) LIKE '%lifecycle%'
    OR LOWER(process_name) LIKE '%lca%'
    OR LOWER(process_name) LIKE '%system%'
    OR LOWER(process_name) LIKE '%overall%'
    OR LOWER(process_name) LIKE '%complete%'
    OR process_name LIKE '%全生命周期%'
    OR process_name LIKE '%整体%'
    OR process_name LIKE '%系统%';

-- 显示更新结果
SELECT '' as info;
SELECT '===== 更新完成 =====' as info;
SELECT '更新了 ' || changes() || ' 条记录' as result;

-- 显示当前的环节分布
SELECT '' as info;
SELECT '===== 当前环节分布 =====' as info;
SELECT '' as info;

SELECT 
    lifecycle_stage,
    COUNT(*) as count
FROM process_lifecycle_stage
GROUP BY lifecycle_stage
ORDER BY 
    CASE lifecycle_stage
        WHEN 'overall' THEN 1
        WHEN 'raw_material' THEN 2
        WHEN 'production' THEN 3
        WHEN 'transport' THEN 4
        WHEN 'use' THEN 5
        WHEN 'disposal' THEN 6
        WHEN 'recycling' THEN 7
        ELSE 8
    END;

SELECT '' as info;
SELECT '✅ 更新成功！现在请刷新浏览器查看可视化页面。' as info;

