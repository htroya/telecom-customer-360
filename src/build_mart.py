from __future__ import annotations

import argparse
import random
from datetime import date
from html import escape
from pathlib import Path

import duckdb
import polars as pl


SNAPSHOT_DATE = date(2026, 6, 30)
BUSINESS_LINES = {
    "telefonia_fija": ("Voz Hogar", 18.0),
    "internet": ("Fibra Conecta", 32.0),
    "television": ("TV Entretenimiento", 24.0),
}


def generate_services(customers: int = 1_000, seed: int = 42) -> pl.DataFrame:
    """Create a deterministic, synthetic service snapshot for portfolio use."""
    if customers < 1:
        raise ValueError("customers debe ser mayor que cero")

    rng = random.Random(seed)
    lines = list(BUSINESS_LINES)
    cities = ["Quito", "Guayaquil", "Cuenca", "Loja"]
    segments = ["hogar", "pyme", "corporativo"]
    rows: list[dict] = []
    service_id = 1

    for customer in range(1, customers + 1):
        segment = segments[customer % len(segments)]
        city = cities[(customer * 5) % len(cities)]
        for line_index in range(1 + customer % 3):
            business_line = lines[(customer + line_index) % len(lines)]
            plan_name, base_fee = BUSINESS_LINES[business_line]
            tenure_months = 1 + (customer * 7 + line_index * 11) % 120
            incidents = int(rng.random() < 0.34) + int(rng.random() < 0.10)
            usage_score = max(
                0.0,
                min(100.0, 42.0 + tenure_months * 0.32 - incidents * 14 + rng.uniform(-14, 14)),
            )
            active = not (incidents >= 2 and usage_score < 35) and rng.random() >= 0.035
            rows.append(
                {
                    "service_id": service_id,
                    "customer_id": f"C{customer:05d}",
                    "snapshot_date": SNAPSHOT_DATE,
                    "segment": segment,
                    "city": city,
                    "business_line": business_line,
                    "plan_name": plan_name,
                    "monthly_fee": round(base_fee + (customer % 9) * 2.75, 2),
                    "usage_score": round(usage_score, 2),
                    "incidents": incidents,
                    "active": active,
                    "tenure_months": tenure_months,
                }
            )
            service_id += 1

    return pl.DataFrame(rows)


def evaluate_quality(frame: pl.DataFrame) -> dict[str, bool]:
    required = [
        "service_id",
        "customer_id",
        "snapshot_date",
        "segment",
        "city",
        "business_line",
        "plan_name",
    ]
    customer_conflicts = (
        frame.group_by("customer_id")
        .agg(pl.col("segment").n_unique(), pl.col("city").n_unique())
        .filter((pl.col("segment") > 1) | (pl.col("city") > 1))
        .height
    )
    return {
        "row_count_positive": frame.height > 0,
        "service_id_unique": frame["service_id"].n_unique() == frame.height,
        "required_fields_not_null": frame.select(required).null_count().sum_horizontal().item() == 0,
        "monthly_fee_non_negative": frame.filter(pl.col("monthly_fee") < 0).is_empty(),
        "usage_score_in_range": frame.filter(~pl.col("usage_score").is_between(0, 100)).is_empty(),
        "incidents_non_negative": frame.filter(pl.col("incidents") < 0).is_empty(),
        "customer_attributes_consistent": customer_conflicts == 0,
    }


def _write_findings(connection: duckdb.DuckDBPyConnection, path: Path) -> None:
    overview = connection.execute(
        """
        SELECT
            COUNT(*) AS customers,
            ROUND(SUM(monthly_revenue), 2) AS monthly_revenue,
            ROUND(AVG(contracted_services), 2) AS services_per_customer,
            SUM(CASE WHEN risk_level = 'high' THEN 1 ELSE 0 END) AS high_risk_customers
        FROM mart_customer_360
        """
    ).fetchone()
    leading_line = connection.execute(
        """
        SELECT business_line, monthly_revenue
        FROM mart_business_line_kpi
        ORDER BY monthly_revenue DESC
        LIMIT 1
        """
    ).fetchone()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Hallazgos reproducibles\n\n"
        "> Todos los valores proceden del dataset sintético generado por este repositorio; "
        "no representan clientes ni resultados de una empresa real.\n\n"
        f"- La muestra contiene **{overview[0]:,} clientes** y "
        f"**USD {overview[1]:,.2f}** de ingreso mensual simulado.\n"
        f"- El promedio es **{overview[2]:.2f} servicios por cliente**.\n"
        f"- **{overview[3]:,} clientes** cumplen la regla demostrativa de riesgo alto y "
        "serían candidatos a revisión, no a una acción automática.\n"
        f"- **{leading_line[0]}** concentra el mayor ingreso mensual simulado "
        f"(**USD {leading_line[1]:,.2f}**).\n\n"
        "Estas observaciones son descriptivas. Antes de usarlas en producción se deben "
        "validar definiciones, costos, sesgos y reglas de contacto con responsables de negocio.\n",
        encoding="utf-8",
    )


def _write_dashboard_svg(connection: duckdb.DuckDBPyConnection, path: Path) -> None:
    rows = connection.execute(
        """
        SELECT business_line, monthly_revenue, active_rate
        FROM mart_business_line_kpi
        ORDER BY monthly_revenue DESC
        """
    ).fetchall()
    max_revenue = max(row[1] for row in rows)
    bars: list[str] = []
    for index, (line, revenue, active_rate) in enumerate(rows):
        y = 185 + index * 75
        width = int(430 * revenue / max_revenue)
        bars.extend(
            [
                f'<text x="70" y="{y}" class="label">{escape(line.replace("_", " ").title())}</text>',
                f'<rect x="250" y="{y - 22}" width="{width}" height="28" rx="6" fill="#246BFD"/>',
                f'<text x="{265 + width}" y="{y}" class="value">USD {revenue:,.0f} · {active_rate:.1%} activos</text>',
            ]
        )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="500" viewBox="0 0 1100 500">
  <style>
    .title {{ font: 700 28px Arial, sans-serif; fill: #17233D; }}
    .subtitle {{ font: 16px Arial, sans-serif; fill: #526078; }}
    .label {{ font: 600 16px Arial, sans-serif; fill: #17233D; }}
    .value {{ font: 14px Arial, sans-serif; fill: #34405A; }}
    .note {{ font: 13px Arial, sans-serif; fill: #6B7280; }}
  </style>
  <rect width="1100" height="500" fill="#F7F9FC"/>
  <rect x="35" y="30" width="1030" height="430" rx="18" fill="white" stroke="#D9E1EF"/>
  <text x="70" y="85" class="title">Customer 360 · vista ejecutiva</text>
  <text x="70" y="117" class="subtitle">Ingreso mensual y tasa de servicios activos por línea</text>
  {''.join(bars)}
  <text x="70" y="430" class="note">Vista equivalente generada desde datos sintéticos reproducibles. No es una captura de Power BI.</text>
</svg>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def build(
    database: Path,
    export_dir: Path,
    customers: int = 1_000,
    seed: int = 42,
    report_dir: Path | None = None,
) -> dict[str, int]:
    database.parent.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    frame = generate_services(customers, seed=seed)
    checks = evaluate_quality(frame)
    failed_checks = [name for name, passed in checks.items() if not passed]
    if failed_checks:
        raise ValueError(f"Controles de calidad fallidos: {', '.join(failed_checks)}")

    sql = (Path(__file__).resolve().parents[1] / "sql" / "customer_360.sql").read_text(encoding="utf-8")
    with duckdb.connect(str(database)) as connection:
        connection.register("services_input", frame.to_arrow())
        connection.execute("CREATE OR REPLACE TABLE raw_services AS SELECT * FROM services_input")
        connection.execute(sql)
        customer_rows = connection.execute("SELECT COUNT(*) FROM mart_customer_360").fetchone()[0]
        sql_failed_checks = connection.execute(
            "SELECT COUNT(*) FROM data_quality_results WHERE NOT passed"
        ).fetchone()[0]
        for table_name, file_name in [
            ("mart_customer_360", "customer_360.csv"),
            ("mart_business_line_kpi", "business_line_kpi.csv"),
            ("fact_service_snapshot", "service_snapshot.csv"),
        ]:
            target = (export_dir / file_name).as_posix().replace("'", "''")
            connection.execute(f"COPY {table_name} TO '{target}' (HEADER, DELIMITER ',')")
        if report_dir is not None:
            _write_findings(connection, report_dir / "findings.md")
            _write_dashboard_svg(connection, report_dir / "dashboard_preview.svg")

    return {
        "customers": customer_rows,
        "services": frame.height,
        "quality_checks": len(checks) + 6,
        "failed_quality_checks": sql_failed_checks,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Customer 360 de telecomunicaciones")
    parser.add_argument("--database", type=Path, default=Path("data/telecom.duckdb"))
    parser.add_argument("--exports", type=Path, default=Path("data/exports"))
    parser.add_argument("--reports", type=Path, default=Path("docs/results"))
    parser.add_argument("--customers", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(build(args.database, args.exports, args.customers, args.seed, args.reports))
