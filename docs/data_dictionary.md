# Diccionario de datos

## `dim_customer`

| Campo | Tipo lógico | Descripción |
|---|---|---|
| `customer_id` | texto, PK | Identificador sintético del cliente. |
| `segment` | texto | Hogar, pyme o corporativo. |
| `city` | texto | Ciudad sintética de residencia/operación. |

## `dim_service_plan`

| Campo | Tipo lógico | Descripción |
|---|---|---|
| `plan_key` | entero, PK | Clave sustituta del plan. |
| `business_line` | texto | Telefonía fija, internet o televisión. |
| `plan_name` | texto | Nombre sintético del plan. |

## `dim_date`

| Campo | Tipo lógico | Descripción |
|---|---|---|
| `date_key` | fecha, PK | Fecha del snapshot. |
| `year`, `quarter`, `month` | entero | Atributos calendario. |
| `month_name` | texto | Nombre del mes. |

## `fact_service_snapshot`

| Campo | Tipo lógico | Regla/uso |
|---|---|---|
| `service_id` | entero, PK | Servicio único en el corte. |
| `customer_id` | texto, FK | Relación con cliente. |
| `plan_key` | entero, FK | Relación con plan. |
| `date_key` | fecha, FK | Relación con fecha. |
| `monthly_fee` | decimal | Ingreso recurrente mensual simulado; no negativo. |
| `usage_score` | decimal | Índice sintético entre 0 y 100; no equivale a tráfico real. |
| `incidents` | entero | Incidentes sintéticos abiertos/observados en el corte. |
| `active` | booleano | Estado del servicio en la fecha de corte. |
| `tenure_months` | entero | Antigüedad sintética del servicio. |

## Marts

- `mart_customer_360`: una fila por cliente, con servicios, ingreso, uso, incidentes, activos y nivel de riesgo explicable.
- `mart_business_line_kpi`: una fila por línea de negocio, con servicios, ingreso, uso, incidentes y tasa activa.
- `data_quality_results`: una fila por control SQL y su resultado booleano.
