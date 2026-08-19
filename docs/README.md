# WMS Industrial — Architecture Blueprint v1.2

> Architecture Baseline Candidate del sistema WMS industrial construido sobre Odoo 19 Community.

| Propiedad | Valor |
|---|---|
| Document Version | 1.2 |
| Product Version | 0.1 (pre-development) |
| Odoo Baseline | 19.0 @ `95f76213d3f732f1d198c740a908e8037c376114` |
| Status | ARCHITECTURE BASELINE APPROVED |
| Implementation | NOT STARTED |

## Índice

### 🔭 Visión

| # | Documento | Contenido |
|---|---|---|
| 00.1 | [Objetivo del Producto](00-vision/01-objetivo-producto.md) | Visión, diferenciación, framework Odoo, capacidades objetivo |
| 00.2 | [Niveles Lógicos](00-vision/02-niveles-logicos.md) | Niveles A/B/C, 16 macrodominios, mapa de capacidades |

---

### 🧩 Dominios

| # | Documento | Contenido | Status |
|---|---|---|---|
| **00** | [**Odoo 19 Capability Matrix**](01-dominios/00-odoo19-capability-matrix.md) | **Qué reutilizar, extender y crear** | v1.2 |
| **00** | [**Product Logistics Master**](01-dominios/00-product-logistics-master.md) | **Perfil logístico del producto** | v1.2 |
| 01 | [Warehouse Master](01-dominios/01-warehouse-master.md) | Topología, zonas, racks, `wms_location_role` | v1.2 |
| 02 | [Inventory](01-dominios/02-inventory.md) | Stock, ledger, estados WMS, tres capas de registro | v1.2 |
| 03 | [Handling Units](01-dominios/03-handling-units.md) | HU sobre `stock.package`, SSCC, operaciones | v1.2 |
| 04 | [Work Execution](01-dominios/04-work-execution.md) | Work Engine + Lease + ACCEPT Protocol | v1.2 |
| 05 | [Resources](01-dominios/05-resources.md) | Operadores, equipos, colas, assignment | v1.0 |
| 06 | [Rule Engine](01-dominios/06-rule-engine.md) | **Typed Policy Engine** (sin safe_eval) | v1.1 |
| 07 | [Inbound](01-dominios/07-inbound.md) | Recepción, dock, calidad | v1.0 |
| 08 | [Putaway](01-dominios/08-putaway.md) | Almacenamiento dirigido, cross dock | v1.0 |
| 09 | [Internal Logistics](01-dominios/09-internal-logistics.md) | Replenishment, slotting | v1.0 |
| 10 | [Outbound](01-dominios/10-outbound.md) | Allocation, waves, picking, consolidation | v1.0 |
| 11 | [Packing & Shipping](01-dominios/11-packing-shipping.md) | Empaque, staging, loading, despacho | v1.0 |
| 12 | [Reverse Logistics](01-dominios/12-reverse-logistics.md) | Devoluciones | v1.0 |
| 13 | [Inventory Control](01-dominios/13-inventory-control.md) | Conteo cíclico | v1.0 |
| 14 | [Labor Management](01-dominios/14-labor-management.md) | Productividad | v1.0 |

---

### ⚙️ Operaciones

| # | Documento | Contenido | Status |
|---|---|---|---|
| 01 | [RF / Mobile](02-operaciones/01-rf-mobile.md) | RF propio + Offline + **ACCEPT Protocol** | v1.2 |
| 02 | [Exception Engine](02-operaciones/02-exception-engine.md) | 13 tipos de excepción | v1.0 |
| 03 | [Control Tower](02-operaciones/03-control-tower.md) | Dashboard operacional | v1.0 |

---

### 🏗️ Plataforma

| # | Documento | Contenido | Status |
|---|---|---|---|
| **00** | [**Transaction Architecture**](03-plataforma/00-transaction-architecture.md) | **Invariantes, boundaries, locking, idempotencia** | v1.2 |
| 01 | [Integración](03-plataforma/01-integracion.md) | API, inbox/outbox, sync vs async | v1.0 |
| 02 | [Kubernetes](03-plataforma/02-kubernetes.md) | K8s, HPA, PDB, runtime separation | v1.0 |
| 03 | [Observability](03-plataforma/03-observability.md) | Métricas técnicas y de negocio | v1.0 |
| 04 | [Seguridad](03-plataforma/04-seguridad.md) | RBAC, roles, scopes | v1.0 |
| 05 | [Auditoría](03-plataforma/05-auditoria.md) | Trazabilidad completa | v1.0 |
| 06 | [Disponibilidad](03-plataforma/06-disponibilidad.md) | Idempotencia, concurrencia, HA | v1.0 |
| **07** | [**DEV vs PROD**](03-plataforma/07-plataforma-dev-vs-prod.md) | **Diferencias infraestructura dev/prod** | v1.1 |
| **08** | [**NFR Workload Model**](03-plataforma/08-nfr-workload-model.md) | **Volúmenes, SLOs, dimensionamiento** | v1.2 |
| **09** | [**Odoo Baseline Registry**](03-plataforma/09-odoo-baseline-registry.md) | **Pin de imagen, source SHA, runtime digest** | v1.0 |

---

### 🗺️ Roadmap

| # | Documento | Contenido |
|---|---|---|
| 01 | [Programa A](04-roadmap/01-programa-a.md) | Fases 0-3: Arquitectura y plataforma |
| 02 | [Programa B](04-roadmap/02-programa-b.md) | Fases 4-9: Kernel WMS |
| 03 | [Programa C](04-roadmap/03-programa-c.md) | Fases 10-17: Inbound & Internal |
| 04 | [Programa D](04-roadmap/04-programa-d.md) | Fases 18-26: Outbound |
| 05 | [Programa E](04-roadmap/05-programa-e.md) | Fases 27-33: Enterprise |
| 06 | [Programa F](04-roadmap/06-programa-f.md) | Fases 34-43: Plataforma |
| 07 | [Programa G](04-roadmap/07-programa-g.md) | Fases 44-50: AI/ML |

> Integration Foundation, Security Baseline, Observability Baseline y Product Logistics Master pertenecen al Kernel (ADR-023/024).

---

### 📋 Decisiones

| # | Documento | Contenido | Status |
|---|---|---|---|
| 01 | [ADR](05-decisiones/01-adr.md) | **27 ADRs** (10 original + 14 v1.1 + 3 v1.2) | v1.2 |
| 02 | [Ficha de Fase](05-decisiones/02-ficha-fase-template.md) | Template + 8 secciones nuevas | v1.1 |

---

### 📎 Archive

| Documento | Contenido |
|---|---|
| [plan.md](plan.md) | ⚠️ **SUPERSEDED** — redirige a este README |
| [plan-v1.0.md](archive/plan-v1.0.md) | Documento original de 2,272 líneas (histórico) |

---

## Changelog v1.2

| Cambio | ARC | Impacto |
|---|---|---|
| `stock.package` confirmado como nombre correcto | ARC-001 | Corrige error en Capability Matrix, HU, Inventory, ADR-013 |
| `wms_location_role` en lugar de nuevos `usage` | ARC-002 | Previene romper lógica interna de Odoo (ADR-026) |
| IN_PROGRESS no auto-requeue offline | ARC-003 | Previene doble movimiento físico (ADR-025) |
| Idempotencia con `INSERT ON CONFLICT` | ARC-004 | Corrige race condition en procesamiento concurrente |
| Invariantes separadas de políticas WMS | ARC-005 | Reconoce que Odoo soporta quants negativos |
| Programa B alineado con v1.2 | ARC-006 | Elimina documentation drift |
| `pick_packaging_id` no `pick_uom_id` | ARC-007 | Separa UOM de Packaging correctamente |
| `wms.inventory.block` por scope | ARC-008 | Block por dimensiones lógicas, no por quant ID |
| Event Journal scoped a WMS ops | ARC-009 | No afirmamos reconstructibilidad prematura |
| CLAIMED simplificado a transitorio | ARC-010 | Menos estados = menos complejidad |
| Odoo version pinning | ARC-011 | Reproducibilidad (ADR-027) |
| NFR math corregida | ARC-012 | Heartbeat y sizing clarificados |

## Changelog v1.1

| Cambio | Impacto |
|---|---|
| Capability Matrix Odoo 19 | Reduce esfuerzo de Inventory, HU, Warehouse Master |
| `stock.quant` identity protection (ADR-011/012) | Previene corrupción silenciosa de inventario |
| `stock.quant.package` como base HU (ADR-013) | Reduce esfuerzo de Fase HU ~40% |
| Product Logistics Master (ADR-024) | Nuevo dominio en Kernel |
| Work Lease Protocol (ADR-015/016) | Corrige crash recovery, agrega heartbeat |
| Transaction Architecture | Invariantes, boundaries, SLOs por operación |
| RF Offline Protocol (ADR-017) | De bullet point a especificación técnica |
| Typed Policy Engine (ADR-018) | Elimina riesgo de safe_eval |
| Event Journal / Audit / Outbox separation (ADR-019) | Tres capas transaccionales distintas |
| DEV vs PROD separation (ADR-020/021/022) | Addons inmutables, filestore RWX, migration protocol |
| NFR Workload Model | Resuelve ambigüedad de volúmenes, define SLOs |
| Cross-cutting concerns (ADR-023) | Security/Observability/Performance desde Fase 3 |
| Phase Template + 8 secciones | Invariantes, TX boundary, idempotency, failure recovery |
| 14 nuevos ADR (011-024) | Estabilización arquitectónica |
