# WMS Inventory Core

Módulo del dominio de inventario para el Warehouse Management System (WMS).

---

## Propósito y Límites Arquitectónicos (Fase 5 — Inventory Core / ADR-001, ADR-011, ADR-012, ADR-026)

`wms_inventory` implementa el **Dominio de Inventario** del Kernel WMS.

### 1. Única Fuente de Verdad del Inventario
- `stock.quant` de Odoo es la **única fuente de verdad** del inventario físico (ADR-001).
- No se crean balances paralelos, ni tablas sombra de quants, ni se almacena `quant_id` como referencia durable.
- Queda estrictamente prohibido introducir campos de estado mutables (`inventory_status`, `quality_status`) dentro de la identidad física de `stock.quant` (ADR-011, ADR-012).

### 2. Reutilización de Primitivas de Movimiento
- `stock.move` representa la **intención de movimiento** (movement intent).
- `stock.move.line` representa el **detalle del movimiento físico** (physical movement detail).
- Los modelos estándar de movimiento de Odoo son reutilizados e integrados, no sustituidos.

### 3. Roles Semánticos de Ubicación
- `wms_location_role` (aportado y gestionado por `wms_warehouse_master`) define la semántica operativa por ubicación (recepción, staging, picking, putaway, calidad, packing, despacho).
- El campo nativo `stock.location.usage` **no se extiende** con valores personalizados (ADR-026).

### 4. Bloqueos Operacionales y Disponibilidad WMS (`wms.inventory.block`)
- **Estado actual**: **INV-006 — Aggregate Block-Aware Availability Engine**.
- **Persistencia (INV-002)**:
  - Scopes: `LOCATION`, `PRODUCT_LOCATION`, `LOT`, `PACKAGE`, `OWNER_LOCATION`.
  - Tipos: `CYCLE_COUNT`, `INVESTIGATION`, `HOLD`, `CUSTOMS`.
  - Inmutabilidad server-side (`create()` con metadata server-owned, `write()` directo y `unlink()` prohibidos, `action_release()` restringido a Supervisor/Admin).
- **Matching API de Candidato Individual (INV-003)**:
  - `_get_matching_domain(...)`: Construcción determinista con `odoo.fields.Domain`.
  - `get_matching_blocks(...)`: Búsqueda ORM en una sola consulta de todos los bloqueos activos aplicables.
  - `is_blocked(...)`: Verificación booleana ultra rápida con `search_count(limit=1)`.
  - Semántica jerárquica: `LOCATION` y `PACKAGE` cubren ancestros/descendientes (`parent_of`).
- **Guardia de Disponibilidad de Candidato Exacto (INV-004)**:
  - `get_unblocked_available_quantity(...)`: Calcula la cantidad disponible para un candidato exacto (`strict=True`).
  - Short-circuit: Si existe bloqueo activo (`is_blocked == True`) -> Retorna `0.0` sin consultar `stock.quant`.
  - Validación de coherencia: `location_id.company_id` debe coincidir con `company_id` o ser compartida (`False`).
- **Matching API Batch sobre Quants (INV-005)**:
  - `get_blocked_quants(...)`: Identifica en batch cuáles `stock.quant` están bloqueados dentro de un conjunto transitorio de 0..N candidatos.
  - Rendimiento anti-N+1: Exactamente 1 búsqueda ORM amplia sobre `wms.inventory.block` para todo el batch y matching exacto en memoria.
  - Cero persistencia: `wms.inventory.block` no almacena `quant_id` ni crea tablas de mapeo.
- **Motor de Disponibilidad Agregada con Bloqueos (INV-006)**:
  - `get_aggregate_unblocked_available_quantity(...)`: Calcula la disponibilidad física agregada en todo el subárbol de una ubicación raíz (`strict=False`).
  - Descubrimiento nativo con company scoping: `_gather(..., strict=False)` con `allowed_company_ids=[company_id.id]`.
  - Filtrado batch: Aplica `get_blocked_quants(...)` (1 sola llamada) y excluye los quants bloqueados.
  - Aritmética nativa Odoo 19: Preserva la lógica de productos untracked (`sum(qty) - sum(res)` con tolerancia UoM) y tracked (agrupación por lote sumando solo grupos positivos).
  - Invariante de monotonicidad: `result = min(native_scoped_available, unblocked_available)`, garantizando que bloquear un quant (incluso con saldo negativo) jamás incremente la disponibilidad.
  - Cero llamadas a `_get_available_quantity()` en producción, cero mutación de reservas y cero integración de allocation/location-roles (diferidos).

---

## Hoja de Ruta del Dominio de Inventario

| Tarea | Capacidad | Estado |
|---|---|---|
| **INV-001** | Bootstrap WMS Inventory Core (Scaffold & Dependencies) | ✅ Merged |
| **INV-002** | Operational Inventory Block Core (`wms.inventory.block`) | ✅ Merged |
| **INV-003** | Operational Block Matching Query API (Single Candidate) | ✅ Merged |
| **INV-004** | Operational Block Availability Guard (Single Candidate, `strict=True`) | ✅ Merged |
| **INV-005** | Operational Block Batch Matching API (`get_blocked_quants`) | ✅ Merged |
| **INV-006** | Aggregate Block-Aware Availability Engine (`strict=False`) | ✅ Current |
| **INV-007+** | Location-Role Operational Eligibility & Allocation Integration (Diferido) | ⏸ Siguiente |
| **INV-008+** | Operational Event Journal (`wms.inventory.event`) | ⏸ Diferido |
| **INV-009+** | Audit Log (`wms.audit.log`) | ⏸ Diferido |
| **INV-010+** | Integration Outbox (`wms.outbox`) | ⏸ Diferido |

---

## Dependencias

- `wms_core`: Base y framework de seguridad/RBAC del WMS.
- `wms_warehouse_master`: Autoridad topológica WMS y semántica de ubicaciones (`wms_location_role`).
- `stock`: Módulo estándar de inventario de Odoo (`stock.quant`, `stock.move`, `stock.move.line`, `stock.location`).
