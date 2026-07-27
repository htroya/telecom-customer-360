from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import polars as pl


def generate_services(customers: int = 1_000) -> pl.DataFrame:
    lines = ["telefonia_fija", "internet", "television"]
    cities = ["Quito", "Guayaquil", "Cuenca", "Loja"]
    segments = ["hogar", "pyme", "corporativo"]
    rows: list[dict] = []
    service_id = 1
    for customer in range(1, customers + 1):
        for line_index in range(1 + customer % 3):
            rows.append(
                {
                    "service_id": service_id,
                    "customer_id": f"C{customer:05d}",
                    "segment": segments[customer % len(segments)],
                    "city": cities[customer % len(cities)],
                    "business_line": lines[(customer + line_index) % len(lines)],
                    "monthly_fee": 18.0 + ((customer * 7 + line_index) % 80),
                    "usage_score": float((customer * 13 + line_index * 17) % 101),
                    "incidents": (customer + line_index) % 4,
                    "active": (customer + line_index) % 11 != 0,
                }
            )
            service_id += 1
    return pl.DataFrame(rows)


def build(database: Path, export_dir: Path, customers: int = 1_000) -> dict[str, int]:
    database.parent.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    frame = generate_services(customers)
    sql = (Path(__file__).resolve().parents[1] / "sql" / "customer_360.sql").read_text(encoding="utf-8")
    with duckdb.connect(str(database)) as connection:
        connection.register("services_input", frame.to_arrow())
        connection.execute("CREATE OR REPLACE TABLE raw_services AS SELECT * FROM services_input")
        connection.execute(sql)
        customer_rows = connection.execute("SELECT COUNT(*) FROM mart_customer_360").fetchone()[0]
        connection.execute(
            f"COPY mart_customer_360 TO '{(export_dir / 'customer_360.csv').as_posix()}' (HEADER, DELIMITER ',')"
        )
        connection.execute(
            f"COPY mart_business_line_kpi TO '{(export_dir / 'business_line_kpi.csv').as_posix()}' (HEADER, DELIMITER ',')"
        )
    return {"customers": customer_rows, "services": frame.height}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Customer 360 de telecomunicaciones")
    parser.add_argument("--database", type=Path, default=Path("data/telecom.duckdb"))
    parser.add_argument("--exports", type=Path, default=Path("data/exports"))
    parser.add_argument("--customers", type=int, default=1_000)
    args = parser.parse_args()
    print(build(args.database, args.exports, customers=args.customers))
