# Programa D — Outbound (Fases 18–26)

> El flujo de salida completo: desde la liberación de pedidos hasta la carga en transporte.

---

## Fases

### Fase 18 — Outbound Orchestration
**Órdenes y release.** Control de liberación de pedidos al WMS con throttling, priorización y cutoff.

### Fase 19 — Allocation
**Selección de stock.** Motor de asignación de inventario con estrategias FIFO, FEFO, LIFO, closest, full pallet, least fragmentation.

### Fase 20 — Wave Planning
**Agrupación operacional.** Motor de olas que agrupa pedidos por carrier, ruta, zona, cutoff y prioridad.

### Fase 21 — Picking
**Todos los modelos de picking.** Discrete, batch, wave, cluster, zone, pick & pass, case, piece, full pallet, two-step, multi-order.

### Fase 22 — Consolidation
**Unificación de picks.** Reunión de partes de un pedido provenientes de diferentes zonas.

### Fase 23 — Packing
**Empaque y cartonización.** Estaciones de empaque, selección de contenedor, verificación, pesaje, SSCC, etiquetado.

### Fase 24 — Staging
**Preparación de carga.** Organización por ruta, carrier, dock y secuencia de carga.

### Fase 25 — Loading
**Carga dirigida por RF.** Validación scan-by-scan de cada HU contra el embarque asignado.

### Fase 26 — Shipping
**Cierre de despacho.** Cierre de shipment, actualización de inventario, generación de manifest, eventos de integración.

→ Detalle completo en:
- [01-dominios/10-outbound.md](../01-dominios/10-outbound.md) (Allocation, Waves, Picking, Consolidation)
- [01-dominios/11-packing-shipping.md](../01-dominios/11-packing-shipping.md) (Packing, Staging, Loading, Shipping)

---

*Documento derivado de las Fases 18-26 del [Plan Maestro](../plan.md).*
