# Especificación del dashboard Power BI

## Modelo

Importar `service_snapshot.csv`, `customer_360.csv` y `business_line_kpi.csv`. Para un modelo completo, cargar dimensiones desde DuckDB o Power Query y relacionarlas 1:* con filtro unidireccional hacia `fact_service_snapshot`. Marcar `dim_date` como tabla de fechas. Evitar relaciones bidireccionales.

## Página 1 — Resumen ejecutivo

- Tarjetas: Ingreso mensual, Clientes, Servicios, Servicios por cliente y Tasa activa.
- Barras horizontales: ingreso y tasa activa por línea de negocio.
- Matriz: segmento × línea con ingreso, servicios, uso e incidentes.
- Segmentadores: fecha, ciudad, segmento y línea.
- Nota visible: “Datos sintéticos; resultados de referencia reproducibles”.

## Página 2 — Customer 360

- Tabla buscable por cliente con segmento, ciudad, servicios, ingreso, uso, incidentes y riesgo.
- Distribución de clientes por nivel de riesgo.
- Dispersión: ingreso mensual vs. uso; tamaño por servicios y color por riesgo.
- Tooltip con líneas y planes del cliente.

## Página 3 — Calidad y operación

- Semáforo de controles aprobados/fallidos desde `data_quality_results`.
- Incidentes y uso por línea.
- Tasa activa por segmento y ciudad.
- Fecha/hora de actualización y parámetros de fuente.

## Diseño y accesibilidad

- Fondo claro, azul `#246BFD`, texto `#17233D`, alerta `#C2413B`.
- Contraste mínimo 4.5:1, títulos descriptivos y texto alternativo.
- Formato monetario `USD #,##0.00`; porcentajes con un decimal.
- No usar rojo/verde como único medio para comunicar estado.

## Validación manual pendiente

Power BI Desktop no forma parte del pipeline automatizado. El PBIX debe crearse manualmente, validar filtros y totales contra DuckDB, ejecutar Performance Analyzer y documentar refresh/RLS antes de publicación.
