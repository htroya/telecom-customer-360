# Telecom Customer 360

Plataforma analítica para consolidar telefonía fija, internet y televisión en una vista única de cliente. El repositorio contiene la carga mensual, el historial SCD tipo 2, el modelo dimensional en DuckDB, los controles de calidad, los marts de ciclo de vida y cohortes, las consultas SQL y el contrato de consumo para Power BI.

> **Tratamiento de datos:** las fuentes incluidas son deterministas y no contienen clientes, operaciones ni métricas confidenciales. Sirven para ejecutar todos los controles y revisar el comportamiento del sistema antes de conectar orígenes corporativos.

**Sitio del portafolio:** https://htroya.github.io/telecom-customer-360/

![Vista ejecutiva construida desde los resultados](docs/results/dashboard_preview.svg)

## Qué resuelve

En una operación de telecomunicaciones, la información de cliente, plan, ingreso, uso, incidentes y estado suele quedar separada por línea de negocio. Esa fragmentación impide responder con una definición común preguntas básicas: qué servicios tiene cada cliente, cómo cambia el ingreso mensual, qué cohortes permanecen activas y dónde se deteriora la calidad del servicio.

Esta solución reúne esos procesos sin borrar su historia. Cada corte mensual conserva el grano servicio-mes, mantiene las versiones del cliente y publica salidas que pueden auditarse desde el dato de origen hasta la medida del tablero.

## Capacidades implementadas

| Capacidad | Implementación | Evidencia en el repositorio |
|---|---|---|
| Vista Customer 360 | Consolidación de servicios, líneas activas, ingreso, uso e incidentes por cliente | `mart_customer_360` y [`sql/customer_360.sql`](sql/customer_360.sql) |
| Modelo dimensional | Dimensiones de cliente, plan y fecha; hecho por servicio y corte | [`docs/model.md`](docs/model.md) y [`docs/data_dictionary.md`](docs/data_dictionary.md) |
| Historia de clientes | SCD tipo 2 con vigencia, versión e indicador de fila actual | `dim_customer_scd2` en [`src/advanced_analytics.py`](src/advanced_analytics.py) |
| Carga idempotente | Registro de lote, huella SHA-256 y rechazo de un `run_id` reutilizado con otro contenido | `ingestion_run` y pruebas de repetición segura |
| Ciclo de vida | Altas, reactivaciones, expansión, contracción, estabilidad y bajas | `mart_customer_lifecycle` |
| Retención por cohorte | Población inicial, clientes retenidos y tasa por edad de cohorte | `mart_cohort_retention` |
| Observabilidad | Volumen mensual, variación y conciliación de ingreso | `data_observability_monthly` |
| Consumo BI | CSV versionables, catálogo KPI, consultas y medidas DAX | [`powerbi/dashboard_spec.md`](powerbi/dashboard_spec.md) y [`powerbi/measures.dax`](powerbi/measures.dax) |
| Verificación automática | Integridad, reglas de entrada, historia, lotes y artefactos | [`tests/`](tests) y GitHub Actions |

## Arquitectura

```text
Fuentes de clientes, planes, servicios, uso e incidentes
                           │
                           ▼
              Polars: tipado y calidad temprana
                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
      snapshot vigente              historia mensual
            │                             │
            ▼                             ▼
   DuckDB / esquema estrella   SCD2 + hecho servicio-mes
            │                             │
            └──────────────┬──────────────┘
                           ▼
      Customer 360 · ciclo de vida · cohortes · KPI
                           │
               ┌───────────┴───────────┐
               ▼                       ▼
         CSV y consultas          Power BI / DAX
```

La [arquitectura histórica](docs/architecture_history.md) explica el flujo incremental, los contratos entre capas y las decisiones de modelado.

## Granos y relaciones

No se mezclan procesos con granos distintos:

| Objeto | Grano | Uso principal |
|---|---|---|
| `raw_services` | un servicio en el corte recibido | trazabilidad de entrada |
| `fact_service_snapshot` | un servicio contratado por fecha de corte | ingreso, uso, incidentes y estado |
| `fact_service_monthly` | un servicio por mes | movimientos e historia |
| `dim_customer_scd2` | una versión de cliente por período de vigencia | cambios de ciudad y segmento |
| `mart_customer_360` | un cliente en el corte | lectura transversal de cartera |
| `mart_business_line_kpi` | línea de negocio en el corte | comparación de telefonía, internet y TV |
| `mart_customer_lifecycle` | cliente por mes | clasificación de movimientos de ingreso |
| `mart_cohort_retention` | cohorte por edad en meses | permanencia de clientes |

Las claves y definiciones de columna se mantienen en el [diccionario de datos](docs/data_dictionary.md). Las medidas de negocio están centralizadas en el [catálogo KPI](docs/kpi_catalog.md).

## Flujo de carga

1. Genera o recibe servicios tipados con identificadores estables.
2. Valida nulos, duplicados, dominios, rangos, fechas y coherencia económica.
3. Materializa el snapshot y sus dimensiones en DuckDB.
4. Registra cada lote mediante `run_id`, huella del contenido y cantidad de filas.
5. Construye la historia mensual y deriva las versiones SCD2.
6. Clasifica movimientos de ingreso y calcula retención por cohorte.
7. Ejecuta controles SQL de integridad y conciliación.
8. Publica tablas de consumo, resultados y especificaciones del modelo BI.

Si el mismo lote llega de nuevo con igual contenido, la carga no duplica filas. Si el identificador ya existe con una huella distinta, el proceso se detiene para evitar una sustitución silenciosa.

## Controles de calidad

El sistema falla antes de publicar si encuentra condiciones que comprometen las métricas. Entre los controles cubiertos están:

- identificadores obligatorios vacíos o duplicados;
- líneas de negocio, estados y planes fuera del dominio previsto;
- ingresos o consumos incompatibles con la regla de negocio;
- servicios sin correspondencia en dimensiones;
- ventanas SCD2 superpuestas o sin una única versión vigente;
- meses incompletos en la historia recibida;
- diferencias entre el detalle y los totales agregados;
- reutilización conflictiva de un identificador de lote.

`data_quality_results` conserva el resultado de los controles SQL dentro de la misma base analítica. `data_observability_monthly` permite revisar cambios de volumen y conciliaciones entre períodos.

## Ejecución local

Requiere Python 3.11 o posterior.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m src.build_mart --customers 1000 --seed 42
```

En Linux o macOS:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m src.build_mart --customers 1000 --seed 42
```

La carga principal admite rutas independientes para base, exportaciones y reportes:

```powershell
.venv\Scripts\python -m src.build_mart `
  --database data/telecom.duckdb `
  --exports data/exports `
  --reports docs/results `
  --customers 1000 `
  --seed 42
```

## Salidas

| Salida | Contenido |
|---|---|
| `data/telecom.duckdb` | dimensiones, hechos, marts y resultados de calidad |
| `data/exports/customer_360.csv` | vista consolidada para análisis de cartera |
| `data/exports/business_line_kpi.csv` | indicadores por línea de negocio |
| `data/exports/service_snapshot.csv` | detalle trazable del corte |
| `customer_lifecycle.csv` | movimientos mensuales del cliente |
| `cohort_retention.csv` | retención por cohorte y edad |
| `data_observability_monthly.csv` | controles operativos por período |
| [`docs/results/findings.md`](docs/results/findings.md) | lectura ejecutiva de los resultados |
| [`docs/results/dashboard_preview.svg`](docs/results/dashboard_preview.svg) | vista generada desde el mart |

Las salidas derivadas pueden regenerarse; no se versionan bases locales ni archivos temporales.

## Power BI

La integración con Power BI no depende de un PBIX opaco dentro del repositorio. El contrato queda descrito como texto revisable:

- [`powerbi/dashboard_spec.md`](powerbi/dashboard_spec.md): páginas, relaciones, filtros, navegación y criterios de aceptación;
- [`powerbi/measures.dax`](powerbi/measures.dax): medidas de clientes, servicios, ingreso, variación y calidad;
- [`sql/analysis_queries.sql`](sql/analysis_queries.sql): consultas de contraste para validar el tablero;
- [`docs/kpi_catalog.md`](docs/kpi_catalog.md): definición, grano, fórmula y precauciones de lectura.

Antes de publicar en Power BI Service deben definirse gateway, credenciales, actualización incremental, RLS, propietarios y alertas de refresco según el entorno de destino.

## Pruebas y CI

```powershell
.venv\Scripts\python -m pytest -q
```

La matriz automatizada comprueba:

- validación de parámetros y dominios;
- construcción completa del esquema estrella;
- integridad referencial entre hechos y dimensiones;
- conciliación de filas e ingreso;
- presencia y contenido de exportaciones y reportes;
- historia mensual sin huecos ni ventanas inválidas;
- idempotencia por `run_id` y detección de conflicto;
- SCD2 con una sola versión actual;
- cohortes y movimientos bajo escenarios conocidos.

El flujo de GitHub Actions ejecuta las pruebas ante cambios en la rama o en una solicitud de integración.

## Operación y diagnóstico

| Situación | Señal | Respuesta prevista |
|---|---|---|
| lote repetido sin cambios | misma huella y `run_id` | omitir la segunda escritura |
| lote repetido con otro contenido | huella incompatible | detener y revisar el origen |
| pérdida de un mes | control de continuidad fallido | completar o justificar el período antes de publicar |
| claves sin dimensión | control referencial fallido | corregir catálogo o regla de asignación |
| variación abrupta de volumen | indicador de observabilidad | contrastar extracción y calendario comercial |
| diferencia de ingreso | conciliación fallida | revisar tipo, duplicados y transformación |

## Decisiones de diseño

- El snapshot conserva una fecha explícita para no tratar valores cambiantes como atributos permanentes.
- La historia servicio-mes se mantiene separada de la vista consolidada para evitar doble conteo.
- SCD tipo 2 permite explicar con qué ciudad y segmento se atribuyó cada período.
- La huella del lote protege contra reenvíos y sustituciones accidentales.
- Los controles se ejecutan en Python y SQL: los primeros detienen temprano; los segundos dejan evidencia junto al modelo.
- CSV actúa como frontera portátil para BI, mientras DuckDB conserva las relaciones y la lógica dimensional.
- La clasificación de riesgo del snapshot es descriptiva; no autoriza acciones ni se presenta como predicción.

## Estructura del repositorio

```text
src/                     carga, validación e historia analítica
sql/                     modelo dimensional y consultas de contraste
powerbi/                 especificación del tablero y medidas DAX
docs/                    arquitectura, diccionario y catálogo KPI
docs/results/            hallazgos y visualizaciones generadas
tests/                   pruebas funcionales, históricas y de calidad
portfolio-site/          sitio público y CV descargable
.github/workflows/       pruebas y publicación de GitHub Pages
```

## Alcance y evolución

La fuente controlada simplifica facturación, hogares, productos, bajas y eventos operativos. Para conectar fuentes corporativas todavía deben acordarse contratos, zonas horarias, calendario de cierre, tratamiento de hechos tardíos, retención, RLS y responsables de cada indicador.

Las siguientes ampliaciones previstas son:

1. incorporar facturación, campañas y resultados de retención mediante contratos versionados;
2. añadir captura de cambios y particiones de actualización por período;
3. establecer alertas de frescura, volumen y conciliación con responsables asignados;
4. configurar seguridad por fila y despliegue gobernado del modelo semántico;
5. medir resultados de las intervenciones sin confundir asociación con causalidad.

## Licencia

Código disponible bajo [MIT](LICENSE). Los datos incluidos se usan para validación segura sin exposición de información confidencial.
