from pathlib import Path

import duckdb
import polars as pl
import pytest

from src.build_mart import build, evaluate_quality, generate_services


def test_synthetic_dataset_is_deterministic() -> None:
    first = generate_services(customers=50, seed=7)
    second = generate_services(customers=50, seed=7)
    assert first.equals(second)
    assert not first.equals(generate_services(customers=50, seed=8))


def test_generator_rejects_empty_population() -> None:
    with pytest.raises(ValueError, match="mayor que cero"):
        generate_services(customers=0)


def test_quality_checks_detect_invalid_values() -> None:
    invalid = generate_services(customers=10).with_columns(pl.lit(-1.0).alias("monthly_fee"))
    assert evaluate_quality(invalid)["monthly_fee_non_negative"] is False


def test_customer_360_builds_star_schema_exports_and_reports(tmp_path: Path) -> None:
    database = tmp_path / "telecom.duckdb"
    exports = tmp_path / "exports"
    reports = tmp_path / "reports"
    metrics = build(database, exports, customers=250, seed=42, report_dir=reports)

    assert metrics["customers"] == 250
    assert metrics["services"] > 250
    assert metrics["quality_checks"] == 13
    assert metrics["failed_quality_checks"] == 0
    assert {
        "customer_360.csv",
        "business_line_kpi.csv",
        "service_snapshot.csv",
    } == {path.name for path in exports.iterdir()}
    assert (reports / "findings.md").exists()
    assert "dataset sintético" in (reports / "findings.md").read_text(encoding="utf-8")
    assert "<svg" in (reports / "dashboard_preview.svg").read_text(encoding="utf-8")

    with duckdb.connect(str(database)) as connection:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        risk_levels = connection.execute(
            "SELECT COUNT(DISTINCT risk_level) FROM mart_customer_360"
        ).fetchone()[0]
        failed = connection.execute(
            "SELECT COUNT(*) FROM data_quality_results WHERE NOT passed"
        ).fetchone()[0]

    assert {
        "dim_customer",
        "dim_service_plan",
        "dim_date",
        "fact_service_snapshot",
        "mart_customer_360",
        "mart_business_line_kpi",
        "data_quality_results",
    } <= tables
    assert risk_levels >= 2
    assert failed == 0
