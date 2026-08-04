CREATE OR REPLACE TABLE dim_customer AS
SELECT DISTINCT customer_id, segment, city
FROM raw_services;

CREATE OR REPLACE TABLE dim_service_plan AS
SELECT
    ROW_NUMBER() OVER (ORDER BY business_line, plan_name) AS plan_key,
    business_line,
    plan_name
FROM (
    SELECT DISTINCT business_line, plan_name
    FROM raw_services
);

CREATE OR REPLACE TABLE dim_date AS
SELECT DISTINCT
    snapshot_date AS date_key,
    YEAR(snapshot_date) AS year,
    QUARTER(snapshot_date) AS quarter,
    MONTH(snapshot_date) AS month,
    MONTHNAME(snapshot_date) AS month_name
FROM raw_services;

CREATE OR REPLACE TABLE fact_service_snapshot AS
SELECT
    r.service_id,
    r.customer_id,
    p.plan_key,
    r.snapshot_date AS date_key,
    r.monthly_fee,
    r.usage_score,
    r.incidents,
    r.active,
    r.tenure_months
FROM raw_services r
JOIN dim_service_plan p USING (business_line, plan_name);

CREATE OR REPLACE TABLE mart_customer_360 AS
SELECT
    c.customer_id,
    c.segment,
    c.city,
    COUNT(*) AS contracted_services,
    ROUND(SUM(f.monthly_fee), 2) AS monthly_revenue,
    ROUND(AVG(f.usage_score), 2) AS avg_usage_score,
    SUM(f.incidents) AS incidents,
    SUM(CASE WHEN f.active THEN 1 ELSE 0 END) AS active_services,
    CASE
        WHEN SUM(f.incidents) >= 3 OR AVG(f.usage_score) < 35 THEN 'high'
        WHEN SUM(f.incidents) >= 1 OR AVG(f.usage_score) < 60 THEN 'medium'
        ELSE 'low'
    END AS risk_level
FROM dim_customer c
JOIN fact_service_snapshot f USING (customer_id)
GROUP BY c.customer_id, c.segment, c.city;

CREATE OR REPLACE TABLE mart_business_line_kpi AS
SELECT
    p.business_line,
    COUNT(*) AS services,
    ROUND(SUM(f.monthly_fee), 2) AS monthly_revenue,
    ROUND(AVG(f.usage_score), 2) AS avg_usage_score,
    SUM(f.incidents) AS incidents,
    ROUND(AVG(CASE WHEN f.active THEN 1 ELSE 0 END), 4) AS active_rate
FROM fact_service_snapshot f
JOIN dim_service_plan p USING (plan_key)
GROUP BY p.business_line
ORDER BY monthly_revenue DESC;

CREATE OR REPLACE TABLE data_quality_results AS
SELECT 'fact_row_count_positive' AS check_name, COUNT(*) > 0 AS passed FROM fact_service_snapshot
UNION ALL
SELECT 'service_id_unique', COUNT(*) = COUNT(DISTINCT service_id) FROM fact_service_snapshot
UNION ALL
SELECT 'customer_fk_complete', COUNT(*) = COUNT(c.customer_id)
FROM fact_service_snapshot f LEFT JOIN dim_customer c USING (customer_id)
UNION ALL
SELECT 'plan_fk_complete', COUNT(*) = COUNT(p.plan_key)
FROM fact_service_snapshot f LEFT JOIN dim_service_plan p USING (plan_key)
UNION ALL
SELECT 'monthly_fee_non_negative', COUNT(*) = 0 FROM fact_service_snapshot WHERE monthly_fee < 0
UNION ALL
SELECT 'usage_score_in_range', COUNT(*) = 0 FROM fact_service_snapshot WHERE usage_score NOT BETWEEN 0 AND 100;
