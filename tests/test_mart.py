import json
from pathlib import Path

import duckdb

from src.build_mart import PipelineConfig, build, generate_sources, validate_sources


def test_source_generator_is_relationally_consistent(tmp_path: Path) -> None:
    sources = generate_sources(
        PipelineConfig(tmp_path / "db.duckdb", tmp_path / "exports", customers=50)
    )
    checks = validate_sources(sources)
    assert all(check["passed"] for check in checks)
    assert sources["services"].height > sources["customers"].height
    assert sources["usage"].height == sources["services"].height * 6


def test_customer_360_builds_governed_dimensional_platform(tmp_path: Path) -> None:
    database = tmp_path / "telecom.duckdb"
    exports = tmp_path / "exports"
    manifest = build(database, exports, customers=250)

    assert manifest["status"] == "SUCCEEDED"
    assert manifest["mart_rows"]["mart_customer_360"] == 250
    assert (exports / "run_manifest.json").exists()
    assert (exports / "mart_retention_priority.parquet").exists()

    persisted = json.loads((exports / "run_manifest.json").read_text(encoding="utf-8"))
    assert persisted["run_id"] == manifest["run_id"]

    with duckdb.connect(str(database)) as connection:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        risk_levels = connection.execute(
            "SELECT COUNT(DISTINCT risk_level) FROM mart_customer_360"
        ).fetchone()[0]
        failed_checks = connection.execute(
            "SELECT COUNT(*) FROM data_quality_result WHERE NOT passed"
        ).fetchone()[0]
        run_status = connection.execute(
            "SELECT status FROM etl_run ORDER BY started_at DESC LIMIT 1"
        ).fetchone()[0]

    assert {
        "dim_customer",
        "dim_service",
        "fact_usage",
        "fact_incident",
        "fact_payment",
        "mart_customer_360",
        "mart_retention_priority",
    } <= tables
    assert risk_levels >= 3
    assert failed_checks == 0
    assert run_status == "SUCCEEDED"
