-- 1. Clientes con mayor prioridad de revisión comercial.
SELECT
    customer_id,
    segment,
    city,
    monthly_revenue,
    incidents,
    avg_usage_score,
    risk_level
FROM mart_customer_360
WHERE risk_level = 'high'
ORDER BY monthly_revenue DESC, incidents DESC;

-- 2. Adopción multproducto por segmento.
SELECT
    segment,
    COUNT(*) AS customers,
    ROUND(AVG(contracted_services), 2) AS avg_services,
    ROUND(AVG(monthly_revenue), 2) AS avg_monthly_revenue
FROM mart_customer_360
GROUP BY segment
ORDER BY avg_monthly_revenue DESC;

-- 3. Salud operativa por línea de negocio.
SELECT
    business_line,
    services,
    monthly_revenue,
    avg_usage_score,
    incidents,
    active_rate
FROM mart_business_line_kpi
ORDER BY monthly_revenue DESC;

-- 4. Controles de calidad que requieren atención.
SELECT check_name, passed
FROM data_quality_results
WHERE NOT passed;
