-- Set processes whose names contain "life cycle" or related keywords to the overall stage
-- 
-- Usage:
-- cd /Users/haizhou/Downloads/OpenLCA_1017_1113/lca_website
-- sqlite3 lca_website.db < update_to_overall.sql

-- Show the state before the update
.mode column
.headers on
.width 50 20 20

SELECT '===== Status before update =====' as info;
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
    OR LOWER(process_name) LIKE '%complete%';

SELECT '' as info;
SELECT '===== Starting update =====' as info;

-- Apply the update
UPDATE process_lifecycle_stage
SET 
    lifecycle_stage = 'overall',
    llm_reasoning = 'Auto-updated to overall stage (keyword-based)'
WHERE 
    LOWER(process_name) LIKE '%life cycle%'
    OR LOWER(process_name) LIKE '%lifecycle%'
    OR LOWER(process_name) LIKE '%lca%'
    OR LOWER(process_name) LIKE '%system%'
    OR LOWER(process_name) LIKE '%overall%'
    OR LOWER(process_name) LIKE '%complete%';

-- Show the update result
SELECT '' as info;
SELECT '===== Update complete =====' as info;
SELECT 'Updated ' || changes() || ' record(s)' as result;

-- Show the current stage distribution
SELECT '' as info;
SELECT '===== Current stage distribution =====' as info;
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
SELECT '✅ Update successful! Please refresh the browser to view the visualization page.' as info;

