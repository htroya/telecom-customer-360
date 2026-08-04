# Telecom Customer 360

Sistema de ingeniería analítica para consolidar servicios de telefonía fija, internet y televisión en una vista Customer 360 consumible desde Power BI. Implementa cargas idempotentes, cortes mensuales, dimensión de clientes SCD tipo 2, controles de calidad, esquema estrella, cohortes, movimientos de ingreso, catálogo de KPI y observabilidad de datos.

> **Protección de datos:** la fuente de referencia es determinística y no contiene clientes, operaciones ni métricas confidenciales. Permite validar el sistema completo sin exponer información empresarial.

**Portafolio interactivo:** https://htroya.github.io/telecom-customer-360/

![Vista ejecutiva equivalente](docs/results/dashboard_preview.svg)

## Resumen ejecutivo

El pipeline transforma un snapshot controlado de servicios en un modelo dimensional DuckDB con tres dimensiones, una tabla de hechos y dos marts. Publica CSV para BI, ejecuta trece controles de calidad y genera hallazgos y una visualización SVG directamente desde los resultados. La regla de riesgo es una segmentación descriptiva y transparente; no sustituye un modelo predictivo ni autoriza acciones automáticas.

**English summary:** Telecom analytics system with idempotent monthly loads, a DuckDB star schema, customer SCD type 2 history, lifecycle and cohort marts, quality controls, BI exports, DAX measures and data observability.

## Problema

Cuando clientes, productos, ingresos, uso e incidentes permanecen separados por línea de negocio, resulta difícil conocer la relación completa, priorizar revisiones de servicio y comparar el desempeño del portafolio con definiciones consistentes.

## Solución

```text
Generador de datos de referencia
          │
          ▼
Polars + controles en memoria ──► raw_services
                                      │
                                      ▼
                         DuckDB / esquema estrella
                                      │
                     ┌────────────────┴──────────────┐
                     ▼                               ▼
              Customer 360                  KPI por línea
                     └──────── CSV + DAX + diseño BI ────────┘
```

La arquitectura y las relaciones se detallan en [docs/model.md](docs/model.md).

## Tecnologías

- Python 3.11+, Polars y PyArrow para generación y validación.
- DuckDB y SQL para dimensiones, hechos, marts y controles referenciales.
- Pytest para pruebas funcionales y de calidad.
- Power BI como destino de consumo; DAX y diseño están versionados sin fabricar un PBIX.
- GitHub Actions para validación en cada `push` o `pull_request`.

## Modelo de datos

El grano de `fact_service_snapshot` es **un servicio contratado por fecha de corte**. Se relaciona con `dim_customer`, `dim_service_plan` y `dim_date`. Consulta el [diccionario de datos](docs/data_dictionary.md), el [catálogo de KPI](docs/kpi_catalog.md) y las [consultas analíticas](sql/analysis_queries.sql).

## Ejecución

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m src.build_mart --customers 1000 --seed 42
```

Linux/macOS:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m src.build_mart --customers 1000 --seed 42
```

La ejecución crea, sin necesidad de descargar datos:

- `data/telecom.duckdb`.
- `data/exports/customer_360.csv`.
- `data/exports/business_line_kpi.csv`.
- `data/exports/service_snapshot.csv`.
- `docs/results/findings.md` y `docs/results/dashboard_preview.svg`.

## Power BI

Importa los tres CSV desde `data/exports`, configura las relaciones descritas en [powerbi/dashboard_spec.md](powerbi/dashboard_spec.md) y aplica las medidas de [powerbi/measures.dax](powerbi/measures.dax). El modelo, las medidas y los criterios de aceptación se versionan como texto; el PBIX se administra fuera del repositorio para evitar binarios opacos.

## Pruebas y calidad

```powershell
.venv\Scripts\python -m pytest -q
```

Las pruebas cubren reproducibilidad por semilla, errores de entrada, detección de valores inválidos, esquema estrella, integridad referencial, exportaciones, controles SQL y generación de reportes. `data_quality_results` permite auditar los controles dentro de DuckDB.

## Resultados verificables

Con `--customers 1000 --seed 42`, los resultados vigentes se regeneran en [docs/results/findings.md](docs/results/findings.md). Son resultados controlados para verificar reglas, linaje y consistencia antes de conectar fuentes empresariales.

## Decisiones técnicas

- Snapshot como grano para que ingresos, uso, incidentes y estado tengan una fecha explícita.
- Semilla configurable para reproducir pruebas y comparaciones.
- Reglas de calidad duplicadas en Python y SQL para fallar temprano y dejar trazabilidad consultable.
- Regla de riesgo explicable para una implementación analítica reproducible; no se etiqueta como machine learning.
- CSV como contrato portátil hacia Power BI, sin versionar bases, modelos ni datos generados.

## Historia, incrementalidad y observabilidad

`src/advanced_analytics.py` incorpora cortes mensuales configurables y mantiene la identidad servicio-mes. Cada ejecución registra `run_id`, huella del contenido, cantidad de filas y fecha de carga. Repetir un lote idéntico no duplica información; reutilizar su identificador con datos distintos genera un error.

Las tablas añadidas cubren:

- `dim_customer_scd2`: versiones de ciudad y segmento con vigencia e indicador actual.
- `fact_service_monthly`: ingreso reconocido, uso, incidentes y estado por servicio y mes.
- `mart_customer_lifecycle`: altas o reactivaciones, expansión, contracción, estabilidad y bajas.
- `mart_cohort_retention`: población inicial, clientes retenidos y tasa por edad de cohorte.
- `data_observability_monthly`: volumen, variación mensual e indicador de conciliación.

La [arquitectura histórica](docs/architecture_history.md) describe flujo, granos y contratos. Las nuevas salidas CSV están preparadas para páginas de retención, movimiento de ingresos, calidad y seguimiento de cargas en Power BI.

## Límites de alcance

- La fuente controlada simplifica facturación, hogares, productos, bajas y eventos operativos.
- El historial valida cambios e incrementalidad, pero no representa un calendario comercial específico.
- La regla de riesgo requiere calibración y revisión antes de orientar acciones de retención.
- Gateway, credenciales, RLS y despliegue en Power BI Service dependen del entorno de la organización.

## Próximos pasos

1. Validar catálogo de KPI, vigencias y conciliaciones con responsables de los datos.
2. Conectar facturación, campañas y resultados de retención mediante contratos versionados.
3. Configurar RLS, particiones de actualización y alertas de refresco en Power BI Service.
4. Incorporar pruebas de recuperación, acuerdos de frescura y trazabilidad del origen.

## Capturas

La imagen superior es una visualización equivalente generada desde el mart. El diseño detallado del dashboard se encuentra en [powerbi/dashboard_spec.md](powerbi/dashboard_spec.md).

## Licencia

Código disponible bajo [MIT](LICENSE). Los datos de referencia se utilizan para validación segura, repetible y sin exposición de información confidencial.
