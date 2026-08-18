# Programa F — Plataforma Empresarial (Fases 34–43)

> Integración, control tower, analytics, observabilidad, seguridad, performance, HA, DR, pilot y rollout.

---

## Fases

### Fase 34 — Integration Platform
**ERP / TMS / OMS / Carriers.** API versionada, contratos, inbox/outbox, idempotencia.

→ Detalle en [03-plataforma/01-integracion.md](../03-plataforma/01-integracion.md)

### Fase 35 — Control Tower
**Monitor operacional.** Dashboard en tiempo real de todas las áreas del almacén.

→ Detalle en [02-operaciones/03-control-tower.md](../02-operaciones/03-control-tower.md)

### Fase 36 — Analytics & KPI
**Productividad y capacidad.** Reportes de throughput, utilización, precisión, tendencias.

### Fase 37 — Observability
**Técnica y negocio.** Métricas de plataforma (CPU, RAM, queries) y negocio (picks/hr, wave progress).

→ Detalle en [03-plataforma/03-observability.md](../03-plataforma/03-observability.md)

### Fase 38 — Security Hardening
**RBAC, secrets, network policy.** Endurecimiento de seguridad en todos los niveles.

→ Detalle en [03-plataforma/04-seguridad.md](../03-plataforma/04-seguridad.md)

### Fase 39 — Performance Engineering
**Carga y concurrencia.** Pruebas de carga, optimización de queries, índices, connection pooling.

### Fase 40 — High Availability
**Fallos controlados.** PostgreSQL HA, pod redundancy, PDB, graceful degradation.

→ Detalle en [03-plataforma/06-disponibilidad.md](../03-plataforma/06-disponibilidad.md)

### Fase 41 — Disaster Recovery
**Backup / Restore / Failover.** Procedimientos de recuperación ante desastres.

### Fase 42 — Pilot
**Una operación real.** Deployment controlado en una bodega piloto con volúmenes reales.

### Fase 43 — Production Rollout
**Rollout progresivo.** Despliegue gradual a todas las bodegas con plan de fallback.

---

*Documento derivado de las Fases 34-43 del [Plan Maestro](../plan.md).*
