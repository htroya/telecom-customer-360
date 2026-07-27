CREATE OR REPLACE TABLE dim_customer AS
SELECT DISTINCT customer_id, segment, city
FROM raw_services;

CREATE OR REPLACE TABLE fact_services AS
SELECT
    service_id,
    customer_id,
    business_line,
    monthly_fee,
    usage_score,
    incidents,
    active
FROM raw_services;

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
        WHEN SUM(f.incidents) >= 5 OR AVG(f.usage_score) < 35 THEN 'high'
        WHEN SUM(f.incidents) >= 2 OR AVG(f.usage_score) < 60 THEN 'medium'
        ELSE 'low'
    END AS risk_level
FROM dim_customer c
JOIN fact_services f USING (customer_id)
GROUP BY c.customer_id, c.segment, c.city;

CREATE OR REPLACE TABLE mart_business_line_kpi AS
SELECT
    business_line,
    COUNT(*) AS services,
    ROUND(SUM(monthly_fee), 2) AS monthly_revenue,
    ROUND(AVG(usage_score), 2) AS avg_usage_score,
    SUM(incidents) AS incidents,
    ROUND(AVG(CASE WHEN active THEN 1 ELSE 0 END), 4) AS active_rate
FROM fact_services
GROUP BY business_line
ORDER BY monthly_revenue DESC;
