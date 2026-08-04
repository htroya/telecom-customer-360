from pathlib import Path

import duckdb
import pytest

from src.advanced_analytics import build_advanced_marts, evaluate_history_quality, generate_history


def test_history_is_deterministic_and_has_complete_months() -> None:
    first = generate_history(customers=80, months=8, seed=17)
    second = generate_history(customers=80, months=8, seed=17)
    assert first.equals(second)
    assert first["snapshot_date"].n_unique() == 8
    assert all(evaluate_history_quality(first, expected_months=8).values())


def test_history_rejects_invalid_window() -> None:
    with pytest.raises(ValueError, match="al menos 2"):
        generate_history(customers=20, months=1)


def test_advanced_marts_include_scd2_cohorts_and_idempotency(tmp_path: Path) -> None:
    database = tmp_path / "history.duckdb"
    exports = tmp_path / "exports"
    history = generate_history(customers=120, months=10, seed=9)

    first = build_advanced_marts(database, exports, history, run_id="2026-08-history")
    second = build_advanced_marts(database, exports, history, run_id="2026-08-history")

    assert first["skipped"] is False
    assert second["skipped"] is True
    assert first["scd_versions"] >= 120
    assert {path.name for path in exports.iterdir()} == {
        "customer_lifecycle.csv",
        "cohort_retention.csv",
        "customer_scd2.csv",
        "observability_monthly.csv",
    }

    with duckdb.connect(str(database)) as connection:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        runs = connection.execute("SELECT COUNT(*) FROM ingestion_run").fetchone()[0]
        movements = connection.execute(
            "SELECT COUNT(DISTINCT revenue_movement) FROM mart_customer_lifecycle"
        ).fetchone()[0]
        current_versions = connection.execute(
            "SELECT COUNT(*) FROM dim_customer_scd2 WHERE is_current"
        ).fetchone()[0]

    assert runs == 1
    assert movements >= 3
    assert current_versions == 120
    assert {
        "fact_service_monthly",
        "dim_customer_scd2",
        "mart_customer_lifecycle",
        "mart_cohort_retention",
        "data_observability_monthly",
    } <= tables
