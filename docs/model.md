# Arquitectura y modelo dimensional

## Flujo

```mermaid
flowchart LR
    A[Generador sintético<br/>seed + cantidad] --> B[Polars DataFrame]
    B --> C{Controles<br/>Python}
    C -->|aprobado| D[(raw_services)]
    C -->|fallo| X[Detener ejecución]
    D --> E[SQL DuckDB]
    E --> F[(Esquema estrella)]
    F --> G[Customer 360]
    F --> H[KPI línea de negocio]
    G --> I[CSV + Power BI]
    H --> I
    F --> J[Controles SQL]
```

## Estrella

```mermaid
erDiagram
    DIM_CUSTOMER ||--o{ FACT_SERVICE_SNAPSHOT : customer_id
    DIM_SERVICE_PLAN ||--o{ FACT_SERVICE_SNAPSHOT : plan_key
    DIM_DATE ||--o{ FACT_SERVICE_SNAPSHOT : date_key

    DIM_CUSTOMER {
      string customer_id PK
      string segment
      string city
    }
    DIM_SERVICE_PLAN {
      int plan_key PK
      string business_line
      string plan_name
    }
    DIM_DATE {
      date date_key PK
      int year
      int quarter
      int month
      string month_name
    }
    FACT_SERVICE_SNAPSHOT {
      int service_id PK
      string customer_id FK
      int plan_key FK
      date date_key FK
      decimal monthly_fee
      decimal usage_score
      int incidents
      boolean active
      int tenure_months
    }
```

El grano no debe mezclarse con eventos de uso ni pagos. En una implementación real, esos procesos tendrían hechos separados y dimensiones conformadas.
