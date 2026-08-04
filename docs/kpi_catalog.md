# Catálogo de KPI

| KPI | Definición | Fórmula | Grano/filtro | Advertencia |
|---|---|---|---|---|
| Ingreso mensual | Cargos mensuales del snapshot. | `SUM(monthly_fee)` | Fecha, cliente, plan | No incluye impuestos, descuentos ni cobro real. |
| Servicios | Servicios registrados. | `COUNT(service_id)` | Fecha y filtros activos | Es snapshot, no altas. |
| Clientes | Clientes distintos con al menos un servicio. | `DISTINCTCOUNT(customer_id)` | Fecha | No equivale a hogares. |
| Servicios por cliente | Profundidad promedio de relación. | Servicios / Clientes | Fecha y segmento | Revisar duplicados antes de interpretar. |
| Tasa activa | Proporción de servicios activos. | Activos / Servicios | Fecha y línea | Requiere definición operativa acordada. |
| Uso promedio | Promedio del índice sintético. | `AVERAGE(usage_score)` | Fecha, línea, segmento | Índice analítico sintético, no unidad física. |
| Incidentes | Suma de incidentes observados. | `SUM(incidents)` | Fecha y filtros | No mide severidad ni resolución. |
| Clientes alto riesgo | Clientes que cumplen regla descriptiva. | Conteo con `risk_level = high` | Cliente | No es una probabilidad ni decisión automática. |

Las definiciones deben aprobarse con negocio antes de reemplazar datos sintéticos por fuentes reales.
