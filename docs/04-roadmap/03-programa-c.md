# Programa C — Inbound & Internal Logistics (Fases 10–17)

> Primera funcionalidad operacional completa: desde la interfaz RF hasta la recepción, calidad, almacenamiento, cross dock, movimientos internos, reposición y slotting.

---

## Fases

### Fase 10 — RF Framework
**Cliente operacional.** Interface RF propia para operación dirigida en piso. API dedicada, pantallas simples, scan-driven.

→ Detalle en [02-operaciones/01-rf-mobile.md](../02-operaciones/01-rf-mobile.md)

### Fase 11 — Inbound & Receiving
**ASN → Recepción.** Flujo completo: aviso anticipado, arrival, dock assignment, descarga, recepción, verificación, discrepancias.

→ Detalle en [01-dominios/07-inbound.md](../01-dominios/07-inbound.md)

### Fase 12 — Quality
**Quality / Hold / Quarantine.** Inspección configurable, estados de calidad, generación automática de work según resultado.

→ Detalle en [01-dominios/07-inbound.md](../01-dominios/07-inbound.md) (sección Quality)

### Fase 13 — Putaway
**Location determination.** Motor de determinación de ubicación con múltiples variables y reglas configurables.

→ Detalle en [01-dominios/08-putaway.md](../01-dominios/08-putaway.md)

### Fase 14 — Cross Dock
**Inbound → Outbound.** Evaluación automática de matching entre inbound y demanda outbound urgente.

→ Detalle en [01-dominios/08-putaway.md](../01-dominios/08-putaway.md) (sección Cross Dock)

### Fase 15 — Internal Movements
**Reubicaciones y movimientos.** Movimientos internos dirigidos por el sistema o solicitados manualmente.

### Fase 16 — Replenishment
**Reserva → Pick Face.** Motor de reposición con estrategias Min/Max, demand-driven, wave-driven, top off y emergency.

→ Detalle en [01-dominios/09-internal-logistics.md](../01-dominios/09-internal-logistics.md)

### Fase 17 — Slotting
**Optimización de almacenamiento.** Análisis de ubicación óptima de SKUs basado en velocidad, afinidad, estacionalidad.

→ Detalle en [01-dominios/09-internal-logistics.md](../01-dominios/09-internal-logistics.md) (sección Slotting)

---

*Documento derivado de las Fases 10-17 del [Plan Maestro](../plan.md).*
