# Customer 360 para telecomunicaciones

## Problema presentado

La empresa analizaba telefonía fija, internet y televisión en silos, dificultando comprender el valor total, uso, incidentes y riesgo de cada cliente.

## Solución

El MVP integra las tres líneas de negocio con Polars, construye un modelo dimensional en DuckDB y publica dos marts SQL: visión Customer 360 y KPI por línea de negocio, listos para Power BI.

```text
Servicios -> Polars -> DuckDB dimensional -> Customer 360 + KPI -> CSV para BI
```

## Tecnologías

Python, Polars, DuckDB, SQL dimensional, Parquet/CSV y Pytest.

## Ejecución

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m src.build_mart
.venv/Scripts/pytest -q
```

## Resultado y conclusión

El proceso consolida clientes, servicios, ingresos, uso e incidentes; clasifica niveles de riesgo y exporta datasets de consumo. El modelo demuestra cómo unificar líneas de negocio y traducir datos operativos en decisiones comerciales.
