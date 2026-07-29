CREATE OR REPLACE TABLE dim_customer AS
SELECT
    ROW_NUMBER() OVER (ORDER BY customer_id) AS customer_key,
    customer_id,
    segment,
    city,
    join_date,
    tenure_months,
    digital_consent
FROM raw_customers;

CREATE OR REPLACE TABLE dim_service AS
SELECT
    ROW_NUMBER() OVER (ORDER BY service_id) AS service_key,
    service_id,
    customer_id,
    business_line,
    plan_name,
    monthly_fee,
    start_date,
    active,
    quality_score
FROM raw_services;

CREATE OR REPLACE TABLE fact_usage AS
SELECT
    s.service_key,
    c.customer_key,
    u.period,
    u.usage_index,
    u.availability_pct
FROM raw_usage u
JOIN dim_service s USING (service_id)
JOIN dim_customer c ON c.customer_id = s.customer_id;

CREATE OR REPLACE TABLE fact_incident AS
SELECT
    s.service_key,
    c.customer_key,
    i.incident_id,
    i.severity,
    i.opened_at,
    i.resolved_at,
    i.resolution_hours,
    i.sla_breached
FROM raw_incidents i
JOIN dim_service s USING (service_id)
JOIN dim_customer c ON c.customer_id = s.customer_id;

CREATE OR REPLACE TABLE fact_payment AS
SELECT
    c.customer_key,
    p.period,
    p.billed_amount,
    p.paid_amount,
    p.late_days,
    p.paid_on_time
FROM raw_payments p
JOIN dim_customer c USING (customer_id);

CREATE OR REPLACE TABLE mart_customer_360 AS
WITH service_metrics AS (
    SELECT
        c.customer_key,
        COUNT(*) AS contracted_services,
        SUM(CASE WHEN s.active THEN 1 ELSE 0 END) AS active_services,
        ROUND(SUM(CASE WHEN s.active THEN s.monthly_fee ELSE 0 END), 2) AS monthly_revenue,
        STRING_AGG(DISTINCT s.business_line, ', ' ORDER BY s.business_line) AS portfolio,
        ROUND(AVG(s.quality_score), 2) AS avg_quality_score
    FROM dim_customer c
    JOIN dim_service s USING (customer_id)
    GROUP BY c.customer_key
),
usage_metrics AS (
    SELECT
        customer_key,
        ROUND(AVG(usage_index), 2) AS avg_usage_index,
        ROUND(AVG(availability_pct), 3) AS avg_availability_pct
    FROM fact_usage
    GROUP BY customer_key
),
incident_metrics AS (
    SELECT
        customer_key,
        COUNT(*) AS incidents,
        SUM(CASE WHEN sla_breached THEN 1 ELSE 0 END) AS sla_breaches,
        ROUND(AVG(resolution_hours), 2) AS avg_resolution_hours
    FROM fact_incident
    GROUP BY customer_key
),
payment_metrics AS (
    SELECT
        customer_key,
        ROUND(SUM(paid_amount) / NULLIF(SUM(billed_amount), 0), 4) AS collection_rate,
        ROUND(AVG(late_days), 2) AS avg_late_days,
        SUM(CASE WHEN NOT paid_on_time THEN 1 ELSE 0 END) AS late_payments
    FROM fact_payment
    GROUP BY customer_key
),
scored AS (
    SELECT
        c.customer_id,
        c.segment,
        c.city,
        c.tenure_months,
        s.* EXCLUDE (customer_key),
        COALESCE(u.avg_usage_index, 0) AS avg_usage_index,
        COALESCE(u.avg_availability_pct, 0) AS avg_availability_pct,
        COALESCE(i.incidents, 0) AS incidents,
        COALESCE(i.sla_breaches, 0) AS sla_breaches,
        COALESCE(i.avg_resolution_hours, 0) AS avg_resolution_hours,
        COALESCE(p.collection_rate, 0) AS collection_rate,
        COALESCE(p.avg_late_days, 0) AS avg_late_days,
        COALESCE(p.late_payments, 0) AS late_payments,
        LEAST(
            100,
            ROUND(
                (100 - COALESCE(u.avg_usage_index, 0)) * 0.30
                + COALESCE(i.incidents, 0) * 6
                + COALESCE(i.sla_breaches, 0) * 10
                + (1 - COALESCE(p.collection_rate, 0)) * 35
                + COALESCE(p.avg_late_days, 0) * 1.2,
                2
            )
        ) AS risk_score
    FROM dim_customer c
    JOIN service_metrics s USING (customer_key)
    LEFT JOIN usage_metrics u USING (customer_key)
    LEFT JOIN incident_metrics i USING (customer_key)
    LEFT JOIN payment_metrics p USING (customer_key)
)
SELECT
    *,
    CASE
        WHEN risk_score >= 65 THEN 'critical'
        WHEN risk_score >= 45 THEN 'high'
        WHEN risk_score >= 25 THEN 'medium'
        ELSE 'low'
    END AS risk_level,
    ROUND(monthly_revenue * 12, 2) AS annualized_value
FROM scored;

CREATE OR REPLACE TABLE mart_business_line_kpi AS
SELECT
    s.business_line,
    COUNT(*) AS services,
    COUNT(DISTINCT s.customer_id) AS customers,
    ROUND(SUM(CASE WHEN s.active THEN s.monthly_fee ELSE 0 END), 2) AS monthly_revenue,
    ROUND(AVG(s.quality_score), 2) AS avg_quality_score,
    ROUND(AVG(u.availability_pct), 3) AS avg_availability_pct,
    COUNT(DISTINCT i.incident_id) AS incidents,
    SUM(CASE WHEN i.sla_breached THEN 1 ELSE 0 END) AS sla_breaches,
    ROUND(AVG(CASE WHEN s.active THEN 1.0 ELSE 0.0 END), 4) AS active_rate
FROM dim_service s
LEFT JOIN fact_usage u USING (service_key)
LEFT JOIN fact_incident i USING (service_key, customer_key)
GROUP BY s.business_line
ORDER BY monthly_revenue DESC;

CREATE OR REPLACE TABLE mart_retention_priority AS
SELECT
    customer_id,
    segment,
    city,
    monthly_revenue,
    annualized_value,
    risk_score,
    risk_level,
    incidents,
    sla_breaches,
    avg_late_days,
    CASE
        WHEN risk_score >= 45 AND annualized_value >= 1200 THEN 'P1 - proactive recovery'
        WHEN risk_score >= 45 THEN 'P2 - retention campaign'
        WHEN risk_score >= 25 AND contracted_services >= 2 THEN 'P3 - service review'
        ELSE 'P4 - monitor'
    END AS recommended_action
FROM mart_customer_360
ORDER BY
    CASE risk_level WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
    annualized_value DESC;

CREATE OR REPLACE TABLE mart_city_segment_performance AS
SELECT
    city,
    segment,
    COUNT(*) AS customers,
    ROUND(SUM(monthly_revenue), 2) AS monthly_revenue,
    ROUND(AVG(risk_score), 2) AS avg_risk_score,
    ROUND(AVG(collection_rate), 4) AS collection_rate,
    ROUND(AVG(avg_availability_pct), 3) AS availability_pct
FROM mart_customer_360
GROUP BY city, segment
ORDER BY monthly_revenue DESC;
