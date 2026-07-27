from pathlib import Path

import duckdb

from src.build_mart import build


def test_customer_360_builds_dimensional_model_and_exports(tmp_path: Path) -> None:
    database = tmp_path / "telecom.duckdb"
    exports = tmp_path / "exports"
    metrics = build(database, exports, customers=250)
    assert metrics["customers"] == 250
    assert metrics["services"] > 250
    assert (exports / "customer_360.csv").exists()
    assert (exports / "business_line_kpi.csv").exists()
    with duckdb.connect(str(database)) as connection:
        risk_levels = connection.execute(
            "SELECT COUNT(DISTINCT risk_level) FROM mart_customer_360"
        ).fetchone()[0]
    assert risk_levels >= 2
