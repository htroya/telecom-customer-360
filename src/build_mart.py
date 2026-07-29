from __future__ import annotations

import argparse
import json
import logging
import random
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import duckdb
import polars as pl

LOGGER = logging.getLogger("telecom_customer_360")
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PipelineConfig:
    database: Path
    export_dir: Path
    customers: int = 1_000
    seed: int = 42
    reference_date: date = date(2026, 7, 1)


def _customer_id(index: int) -> str:
    return f"C{index:06d}"


def generate_sources(config: PipelineConfig) -> dict[str, pl.DataFrame]:
    """Generate deterministic, relationally consistent telecom source systems."""
    if config.customers < 10:
        raise ValueError("customers must be at least 10")

    rng = random.Random(config.seed)
    cities = ["Quito", "Guayaquil", "Cuenca", "Loja", "Ambato"]
    segments = ["hogar", "pyme", "corporativo"]
    lines = ["telefonia_fija", "internet", "television"]
    plans = {
        "telefonia_fija": ["Basico", "Ilimitado", "Empresarial"],
        "internet": ["Fibra 100", "Fibra 300", "Fibra 600"],
        "television": ["Familiar", "Premium", "Deportes"],
    }

    customers: list[dict] = []
    services: list[dict] = []
    usage: list[dict] = []
    incidents: list[dict] = []
    payments: list[dict] = []
    service_index = 1
    incident_index = 1

    for index in range(1, config.customers + 1):
        customer_id = _customer_id(index)
        segment = segments[index % len(segments)]
        city = cities[(index * 7) % len(cities)]
        tenure_months = 3 + (index * 11) % 120
        join_date = config.reference_date - timedelta(days=tenure_months * 30)
        customers.append(
            {
                "customer_id": customer_id,
                "segment": segment,
                "city": city,
                "join_date": join_date,
                "tenure_months": tenure_months,
                "digital_consent": index % 9 != 0,
            }
        )

        service_count = 1 + index % 3
        customer_fee = 0.0
        customer_risk = (index * 17) % 100
        for offset in range(service_count):
            line = lines[(index + offset) % len(lines)]
            service_id = f"S{service_index:07d}"
            service_index += 1
            monthly_fee = round(18 + ((index * 7 + offset * 13) % 95), 2)
            customer_fee += monthly_fee
            active = customer_risk < 92 or offset == 0
            quality_score = round(max(20.0, 98 - customer_risk * 0.55 - offset * 2), 2)
            services.append(
                {
                    "service_id": service_id,
                    "customer_id": customer_id,
                    "business_line": line,
                    "plan_name": plans[line][(index + offset) % 3],
                    "monthly_fee": monthly_fee,
                    "start_date": join_date + timedelta(days=offset * 45),
                    "active": active,
                    "quality_score": quality_score,
                }
            )

            for month_offset in range(6):
                period = date(2026, month_offset + 1, 1)
                usage_index = round(
                    max(5.0, min(100.0, quality_score - rng.uniform(-8, 12))),
                    2,
                )
                usage.append(
                    {
                        "service_id": service_id,
                        "period": period,
                        "usage_index": usage_index,
                        "availability_pct": round(
                            max(
                                91.0,
                                min(
                                    100.0,
                                    99.8 - customer_risk * 0.04 - rng.uniform(0, 1.2),
                                ),
                            ),
                            3,
                        ),
                    }
                )

            incident_count = (customer_risk + offset * 5) // 28
            for incident_offset in range(incident_count):
                opened_at = datetime(2026, 1 + incident_offset % 6, 5 + index % 20, tzinfo=UTC)
                severity = ["low", "medium", "high", "critical"][
                    min(3, (customer_risk + incident_offset * 9) // 28)
                ]
                resolution_hours = round(2 + customer_risk * 0.22 + incident_offset * 1.5, 2)
                sla_hours = {"low": 48, "medium": 24, "high": 12, "critical": 4}[severity]
                incidents.append(
                    {
                        "incident_id": f"I{incident_index:08d}",
                        "service_id": service_id,
                        "severity": severity,
                        "opened_at": opened_at,
                        "resolved_at": opened_at + timedelta(hours=resolution_hours),
                        "resolution_hours": resolution_hours,
                        "sla_breached": resolution_hours > sla_hours,
                    }
                )
                incident_index += 1

        for month_offset in range(6):
            period = date(2026, month_offset + 1, 1)
            late_days = max(0, (customer_risk + month_offset * 7) % 24 - 12)
            billed = round(customer_fee, 2)
            paid_ratio = 1.0 if late_days < 10 else 0.82
            payments.append(
                {
                    "customer_id": customer_id,
                    "period": period,
                    "billed_amount": billed,
                    "paid_amount": round(billed * paid_ratio, 2),
                    "late_days": late_days,
                    "paid_on_time": late_days == 0,
                }
            )

    return {
        "customers": pl.DataFrame(customers),
        "services": pl.DataFrame(services),
        "usage": pl.DataFrame(usage),
        "incidents": pl.DataFrame(incidents),
        "payments": pl.DataFrame(payments),
    }


def validate_sources(sources: dict[str, pl.DataFrame]) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    required = {
        "customers": {"customer_id", "segment", "city"},
        "services": {"service_id", "customer_id", "business_line", "monthly_fee"},
        "usage": {"service_id", "period", "usage_index"},
        "incidents": {"incident_id", "service_id", "severity"},
        "payments": {"customer_id", "period", "billed_amount"},
    }
    for name, columns in required.items():
        frame = sources[name]
        missing = sorted(columns - set(frame.columns))
        checks.append(
            {
                "check_name": f"{name}.required_columns",
                "passed": not missing,
                "observed_value": ",".join(missing) if missing else "complete",
            }
        )
        if missing:
            raise ValueError(f"{name} is missing columns: {missing}")

    duplicate_customers = (
        sources["customers"].group_by("customer_id").len().filter(pl.col("len") > 1).height
    )
    orphan_services = sources["services"].join(
        sources["customers"].select("customer_id"),
        on="customer_id",
        how="anti",
    ).height
    invalid_fees = sources["services"].filter(pl.col("monthly_fee") <= 0).height
    invariants = {
        "customers.unique_key": duplicate_customers,
        "services.orphan_customer": orphan_services,
        "services.non_positive_fee": invalid_fees,
    }
    for name, failures in invariants.items():
        checks.append(
            {
                "check_name": name,
                "passed": failures == 0,
                "observed_value": str(failures),
            }
        )
        if failures:
            raise ValueError(f"Data quality check failed: {name}={failures}")
    return checks


def _load_sources(connection: duckdb.DuckDBPyConnection, sources: dict[str, pl.DataFrame]) -> None:
    for name, frame in sources.items():
        relation = f"{name}_input"
        connection.register(relation, frame.to_arrow())
        connection.execute(
            f"CREATE OR REPLACE TABLE raw_{name} AS SELECT * FROM {relation}"
        )


def _export_marts(
    connection: duckdb.DuckDBPyConnection,
    export_dir: Path,
) -> dict[str, int]:
    marts = [
        "mart_customer_360",
        "mart_business_line_kpi",
        "mart_retention_priority",
        "mart_city_segment_performance",
    ]
    counts: dict[str, int] = {}
    for mart in marts:
        target = (export_dir / f"{mart}.parquet").as_posix().replace("'", "''")
        connection.execute(
            f"COPY {mart} TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        counts[mart] = connection.execute(f"SELECT COUNT(*) FROM {mart}").fetchone()[0]
    return counts


def build(
    database: Path,
    export_dir: Path,
    customers: int = 1_000,
    seed: int = 42,
) -> dict[str, object]:
    config = PipelineConfig(
        database=database,
        export_dir=export_dir,
        customers=customers,
        seed=seed,
    )
    config.database.parent.mkdir(parents=True, exist_ok=True)
    config.export_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid4())
    started_at = datetime.now(UTC)
    timer = perf_counter()
    sources = generate_sources(config)
    checks = validate_sources(sources)

    with duckdb.connect(str(config.database)) as connection:
        connection.execute("BEGIN TRANSACTION")
        try:
            _load_sources(connection, sources)
            connection.execute((ROOT / "sql" / "customer_360.sql").read_text(encoding="utf-8"))
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS etl_run (
                    run_id VARCHAR,
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    status VARCHAR,
                    source_rows BIGINT,
                    duration_seconds DOUBLE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS data_quality_result (
                    run_id VARCHAR,
                    check_name VARCHAR,
                    passed BOOLEAN,
                    observed_value VARCHAR,
                    checked_at TIMESTAMPTZ
                )
                """
            )
            for check in checks:
                connection.execute(
                    "INSERT INTO data_quality_result VALUES (?, ?, ?, ?, ?)",
                    [
                        run_id,
                        check["check_name"],
                        check["passed"],
                        check["observed_value"],
                        datetime.now(UTC),
                    ],
                )
            mart_rows = _export_marts(connection, config.export_dir)
            duration = round(perf_counter() - timer, 4)
            source_rows = sum(frame.height for frame in sources.values())
            connection.execute(
                "INSERT INTO etl_run VALUES (?, ?, ?, ?, ?, ?)",
                [run_id, started_at, datetime.now(UTC), "SUCCEEDED", source_rows, duration],
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    manifest = {
        "run_id": run_id,
        "status": "SUCCEEDED",
        "generated_at": datetime.now(UTC).isoformat(),
        "configuration": {
            **asdict(config),
            "database": str(config.database),
            "export_dir": str(config.export_dir),
            "reference_date": config.reference_date.isoformat(),
        },
        "source_rows": {name: frame.height for name, frame in sources.items()},
        "mart_rows": mart_rows,
        "quality_checks": checks,
    }
    (config.export_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Plataforma Customer 360 de telecomunicaciones")
    parser.add_argument("--database", type=Path, default=Path("data/telecom.duckdb"))
    parser.add_argument("--exports", type=Path, default=Path("data/exports"))
    parser.add_argument("--customers", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    LOGGER.info("Starting Customer 360 pipeline")
    result = build(args.database, args.exports, args.customers, args.seed)
    LOGGER.info("Pipeline completed: %s", json.dumps(result["mart_rows"]))


if __name__ == "__main__":
    main()
