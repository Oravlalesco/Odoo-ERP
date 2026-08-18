# NFR-001 — WMS Workload Model y SLOs

> Definición formal de los volúmenes esperados y los objetivos de nivel de servicio. Sin este documento, no se puede dimensionar infraestructura ni validar performance.

---

## Contexto

### El Problema de Ambigüedad

La documentación v1.0 contenía dos afirmaciones contradictorias:

```text
Documento A: "250 operadores generando transacciones cada 3-5 segundos"
             → 50-83 req/s solo en RF

Documento B: "5-10 TPS"
```

No podemos diseñar infraestructura con esa ambigüedad. Este documento la resuelve.

---

## Escenarios de Carga

### Variables Base

| Variable | Valor |
|---|---|
| RF devices registrados | 500 |
| RF activos simultáneamente | 250 (típico), 400 (peak) |
| Intervalo entre acciones RF | 3-5 segundos por operador |
| Bodegas | 2-3 |
| SKUs activos | 10,000-50,000 |
| Ubicaciones | 20,000-100,000 |

### Escenarios

| Escenario | RF activos | Picks/min | Confirmations/s | Integration msg/s | Orders/hr | Inventory events/day |
|---|---|---|---|---|---|---|
| **NORMAL** | 150 | 100 | 30 | 10 | 5,000 | 500K |
| **PEAK** | 250 | 300 | 80 | 20 | 20,000 | 2M |
| **STRESS** | 400 | 500 | 130 | 40 | 35,000 | 3.5M |
| **EXTREME** | 500 | 800 | 200 | 60 | 50,000 | 5M |

### Desglose de PEAK (escenario de diseño)

```text
250 operadores activos:

80 → Picking      (scan + confirm cada 4s)     = 20 TPS
50 → Putaway      (scan + confirm cada 6s)     = 8 TPS
30 → Replenishment (scan + confirm cada 8s)    = 4 TPS
20 → Packing      (scan + confirm cada 3s)     = 7 TPS
15 → Loading      (scan + confirm cada 5s)     = 3 TPS
15 → Counting     (scan + confirm cada 10s)    = 2 TPS
10 → Receiving    (scan + confirm cada 5s)     = 2 TPS
30 → Heartbeats   (cada 30s)                   = 8 TPS

Total RF TPS: ~54 TPS

+ Integration: 20 msg/s
+ Backoffice: 5 req/s
+ Wave planning: burst 50 work creates/s

Total system TPS peak: ~130 TPS
```

---

## SLOs — Service Level Objectives

### Operaciones RF (críticas)

| Operación | p50 | p95 | p99 | Máximo |
|---|---|---|---|---|
| Claim Work | 15ms | 35ms | 50ms | 200ms |
| Scan Location (validación) | 10ms | 30ms | 50ms | 100ms |
| Scan Product (validación) | 10ms | 30ms | 50ms | 100ms |
| Confirm Pick | 30ms | 100ms | 200ms | 500ms |
| Confirm Put | 30ms | 100ms | 200ms | 500ms |
| Heartbeat | 5ms | 15ms | 20ms | 50ms |
| Next Work (request + assignment) | 20ms | 50ms | 100ms | 300ms |

### Operaciones de Planificación

| Operación | p50 | p95 | p99 |
|---|---|---|---|
| Allocation (por orden) | 50ms | 300ms | 500ms |
| Wave Release (100 orders) | 1s | 3s | 5s |
| Replenishment Trigger | 30ms | 100ms | 200ms |

### Operaciones de Integración

| Operación | p50 | p95 | p99 |
|---|---|---|---|
| Inbound Order (API) | 100ms | 300ms | 500ms |
| Inventory Query (API) | 50ms | 200ms | 500ms |
| Outbox processing | 200ms | 500ms | 1s |

### Disponibilidad

| Componente | SLO |
|---|---|
| RF API | 99.9% (8.7h downtime/año) |
| Backoffice | 99.5% (43.8h downtime/año) |
| Integration API | 99.5% |
| Database | 99.95% (4.4h downtime/año) |

---

## Dimensionamiento Estimado

### Para escenario PEAK

| Componente | Sizing |
|---|---|
| **wms-rf pods** | 8-12 pods (2 CPU, 4GB RAM cada uno) |
| **odoo-backoffice pods** | 2-4 pods (2 CPU, 4GB RAM) |
| **wms-api pods** | 2-4 pods (1 CPU, 2GB RAM) |
| **wms-worker pods** | 4-8 pods (2 CPU, 4GB RAM) |
| **PostgreSQL** | Primary: 8 CPU, 32GB RAM, SSD. 2 replicas |
| **Redis** | 2 pods, 2GB RAM cada uno |
| **RabbitMQ** | 3 nodes cluster, 2GB RAM cada uno |

### Almacenamiento

| Componente | Sizing |
|---|---|
| PostgreSQL data | 200GB-500GB (depende de retención) |
| WAL archive | 100GB+ |
| Filestore | 50GB-200GB |
| Logs (30 días) | 100GB |
| RabbitMQ | 20GB |

---

## Performance Testing

### Herramientas Recomendadas

| Herramienta | Propósito |
|---|---|
| **Locust** | Load testing de APIs RF |
| **pgbench** | Benchmark de PostgreSQL |
| **k6** | Load testing de APIs de integración |
| **Custom harness** | Simulación de 250 operadores RF concurrentes |

### Tests Mínimos Antes de Producción

| Test | Criterio de éxito |
|---|---|
| 250 RF concurrentes, 30 min | Todos los SLOs se mantienen |
| 500 RF concurrentes, 10 min (stress) | p99 < 1s, sin errores de datos |
| Wave de 5,000 órdenes | Release < 30s |
| Concurrent allocation race | 0 double-bookings |
| Pod failure during peak | Recovery < 60s, 0 data loss |
| PostgreSQL failover | RTO < 30s |

---

*Documento nuevo para v1.1. Resuelve la ambigüedad de volúmenes y define SLOs medibles.*
