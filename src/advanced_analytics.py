from __future__ import annotations

import calendar
import hashlib
from datetime import date
from pathlib import Path

import duckdb
import polars as pl

from src.build_mart import generate_services


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def generate_history(
    customers: int = 1_000,
    months: int = 18,
    seed: int = 42,
    start_year: int = 2025,
    start_month: int = 1,
) -> pl.DataFrame:
    """Construye cortes mensuales deterministas con cambios de segmento y ciudad."""
    if customers < 1 or months < 2:
        raise ValueError("customers debe ser positivo y months debe ser al menos 2")

    snapshots: list[pl.DataFrame] = []
    for offset in range(months):
        month_index = start_month - 1 + offset
        year = start_year + month_index // 12
        month = month_index % 12 + 1
        snapshot_date = _month_end(year, month)
        customer_number = pl.col("customer_id").str.slice(1).cast(pl.Int64)
        frame = generate_services(customers, seed=seed + offset).with_columns(
            pl.lit(snapshot_date).alias("snapshot_date"),
            pl.when((customer_number % 37 == 0) & (offset >= months // 2))
            .then(pl.lit("Cuenca"))
            .otherwise(pl.col("city"))
            .alias("city"),
            pl.when((customer_number % 53 == 0) & (offset >= months // 3))
            .then(pl.lit("corporativo"))
            .otherwise(pl.col("segment"))
            .alias("segment"),
        )
        snapshots.append(frame)
    return pl.concat(snapshots).sort(["snapshot_date", "service_id"])


def evaluate_history_quality(history: pl.DataFrame, expected_months: int) -> dict[str, bool]:
    key_count = history.select(["snapshot_date", "service_id"]).unique().height
    monthly = history.group_by("snapshot_date").agg(
        pl.len().alias("rows"),
        pl.col("monthly_fee").filter(pl.col("active")).sum().alias("revenue"),
    )
    return {
        "snapshot_service_key_unique": key_count == history.height,
        "complete_month_sequence": monthly.height == expected_months,
        "monthly_volume_positive": monthly.filter(pl.col("rows") <= 0).is_empty(),
        "monthly_revenue_non_negative": monthly.filter(pl.col("revenue") < 0).is_empty(),
        "customer_and_service_present": history.select(
            pl.col("customer_id").is_not_null().all() & pl.col("service_id").is_not_null().all()
        ).item(),
    }


def build_advanced_marts(
    database: Path,
    export_dir: Path,
    history: pl.DataFrame,
    run_id: str,
) -> dict[str, int | str | bool]:
    """Carga un lote idempotente y reconstruye marts históricos auditables."""
    if not run_id.strip():
        raise ValueError("run_id no puede estar vacío")
    checks = evaluate_history_quality(history, history["snapshot_date"].n_unique())
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"Controles históricos fallidos: {', '.join(failed)}")

    database.parent.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    content_hash = hashlib.sha256(history.write_csv().encode("utf-8")).hexdigest()

    with duckdb.connect(str(database)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ingestion_run (
                run_id VARCHAR PRIMARY KEY,
                content_hash VARCHAR NOT NULL,
                loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_rows BIGINT NOT NULL
            )
            """
        )
        existing = connection.execute(
            "SELECT content_hash FROM ingestion_run WHERE run_id = ?", [run_id]
        ).fetchone()
        if existing:
            if existing[0] != content_hash:
                raise ValueError("run_id ya existe con un contenido diferente")
            return {
                "run_id": run_id,
                "source_rows": history.height,
                "quality_checks": len(checks),
                "skipped": True,
            }

        connection.register("history_input", history.to_arrow())
        connection.execute(
            "CREATE TABLE IF NOT EXISTS service_history AS SELECT * FROM history_input WHERE 1=0"
        )
        connection.execute("INSERT INTO service_history SELECT * FROM history_input")
        connection.execute(
            "INSERT INTO ingestion_run(run_id, content_hash, source_rows) VALUES (?, ?, ?)",
            [run_id, content_hash, history.height],
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE fact_service_monthly AS
            SELECT
                snapshot_date,
                service_id,
                customer_id,
                business_line,
                plan_name,
                monthly_fee,
                CASE WHEN active THEN monthly_fee ELSE 0 END AS recognized_revenue,
                usage_score,
                incidents,
                active,
                tenure_months
            FROM service_history
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE dim_customer_scd2 AS
            WITH states AS (
                SELECT DISTINCT customer_id, snapshot_date, segment, city
                FROM service_history
            ), marked AS (
                SELECT *,
                    CASE WHEN segment IS DISTINCT FROM LAG(segment) OVER w
                           OR city IS DISTINCT FROM LAG(city) OVER w
                         THEN 1 ELSE 0 END AS changed
                FROM states
                WINDOW w AS (PARTITION BY customer_id ORDER BY snapshot_date)
            ), islands AS (
                SELECT *, SUM(changed) OVER (
                    PARTITION BY customer_id ORDER BY snapshot_date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS version_number
                FROM marked
            ), versions AS (
                SELECT customer_id, segment, city, version_number,
                       MIN(snapshot_date) AS valid_from
                FROM islands
                GROUP BY ALL
            )
            SELECT *,
                   LEAD(valid_from) OVER (PARTITION BY customer_id ORDER BY valid_from)
                       - INTERVAL 1 DAY AS valid_to,
                   LEAD(valid_from) OVER (PARTITION BY customer_id ORDER BY valid_from) IS NULL
                       AS is_current
            FROM versions
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_customer_lifecycle AS
            WITH monthly AS (
                SELECT snapshot_date, customer_id,
                       SUM(recognized_revenue) AS revenue,
                       SUM(incidents) AS incidents,
                       AVG(usage_score) AS usage_score,
                       COUNT(*) FILTER (WHERE active) AS active_services
                FROM fact_service_monthly
                GROUP BY 1, 2
            ), previous AS (
                SELECT *,
                       LAG(revenue, 1, 0) OVER w AS previous_revenue,
                       LAG(active_services, 1, 0) OVER w AS previous_active_services
                FROM monthly
                WINDOW w AS (PARTITION BY customer_id ORDER BY snapshot_date)
            )
            SELECT *,
                   CASE
                       WHEN previous_revenue = 0 AND revenue > 0 THEN 'new_or_reactivated'
                       WHEN previous_revenue > 0 AND revenue = 0 THEN 'churned'
                       WHEN revenue > previous_revenue THEN 'expansion'
                       WHEN revenue < previous_revenue THEN 'contraction'
                       ELSE 'stable'
                   END AS revenue_movement,
                   revenue - previous_revenue AS revenue_delta
            FROM previous
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_cohort_retention AS
            WITH first_active AS (
                SELECT customer_id, MIN(snapshot_date) AS cohort_month
                FROM mart_customer_lifecycle
                WHERE active_services > 0
                GROUP BY 1
            ), population AS (
                SELECT cohort_month, COUNT(*) AS cohort_customers
                FROM first_active GROUP BY 1
            )
            SELECT f.cohort_month,
                   DATE_DIFF('month', f.cohort_month, m.snapshot_date) AS month_number,
                   COUNT(*) FILTER (WHERE m.active_services > 0) AS retained_customers,
                   p.cohort_customers,
                   ROUND(retained_customers / p.cohort_customers, 4) AS retention_rate
            FROM first_active f
            JOIN mart_customer_lifecycle m USING (customer_id)
            JOIN population p USING (cohort_month)
            GROUP BY 1, 2, 4
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE data_observability_monthly AS
            WITH monthly AS (
                SELECT snapshot_date, COUNT(*) AS source_rows,
                       COUNT(DISTINCT customer_id) AS customers,
                       SUM(recognized_revenue) AS revenue
                FROM fact_service_monthly GROUP BY 1
            )
            SELECT *,
                   source_rows - LAG(source_rows) OVER (ORDER BY snapshot_date) AS row_delta,
                   ROUND((source_rows / NULLIF(LAG(source_rows) OVER (ORDER BY snapshot_date), 0)) - 1, 4)
                       AS row_change_rate,
                   revenue >= 0 AS revenue_reconciled
            FROM monthly
            """
        )

        exports = {
            "mart_customer_lifecycle": "customer_lifecycle.csv",
            "mart_cohort_retention": "cohort_retention.csv",
            "dim_customer_scd2": "customer_scd2.csv",
            "data_observability_monthly": "observability_monthly.csv",
        }
        for table, filename in exports.items():
            target = (export_dir / filename).as_posix().replace("'", "''")
            connection.execute(f"COPY {table} TO '{target}' (HEADER, DELIMITER ',')")
        scd_versions = connection.execute("SELECT COUNT(*) FROM dim_customer_scd2").fetchone()[0]
        lifecycle_rows = connection.execute("SELECT COUNT(*) FROM mart_customer_lifecycle").fetchone()[0]

    return {
        "run_id": run_id,
        "source_rows": history.height,
        "quality_checks": len(checks),
        "scd_versions": scd_versions,
        "lifecycle_rows": lifecycle_rows,
        "skipped": False,
    }

