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

### 4. Bloqueos Operacionales y Matching API (`wms.inventory.block`)
- **Estado actual**: **INV-005 — Operational Block Batch Matching API**.
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
  - `get_unblocked_available_quantity(...)`: Calcula la cantidad disponible para un candidato exacto aplicando la guardia de bloqueos.
  - Short-circuit: Si existe bloqueo activo (`is_blocked == True`) -> Retorna `0.0` sin consultar `stock.quant`.
  - Validación de coherencia: `location_id.company_id` debe coincidir con `company_id` o ser compartida (`False`), de lo contrario lanza `AccessError`.
  - Si no está bloqueado -> Retorna la disponibilidad nativa calculada con `strict=True` y `allow_negative=False`.
  - No altera ni sobrescribe métodos de Stock nativos (`_get_available_quantity`, `_get_reserve_quantity`, `_gather`, `_action_assign`).
- **Matching API Batch sobre Quants (INV-005)**:
  - `get_blocked_quants(...)`: Identifica en batch cuáles `stock.quant` están bloqueados dentro de un conjunto transitorio de 0..N candidatos.
  - Rendimiento anti-N+1: Exactamente 1 búsqueda ORM amplia sobre `wms.inventory.block` para todo el batch.
  - Evaluación exacta en memoria: Matriz Python que protege contra falsos positivos por producto cruzado (cross-product false positives).
  - Jerarquía in-memory: Validación de ancestros mediante `candidate.parent_path.startswith(block.parent_path)` para ubicaciones y paquetes.
  - Cero persistencia: `wms.inventory.block` jamás almacena `quant_id` ni crea tablas de mapeo intermedias.
  - Cero mutación de cantidades o reservas: no calcula availability agregada ni invoca `_action_assign()`.

---

## Hoja de Ruta del Dominio de Inventario

| Tarea | Capacidad | Estado |
|---|---|---|
| **INV-001** | Bootstrap WMS Inventory Core (Scaffold & Dependencies) | ✅ Merged |
| **INV-002** | Operational Inventory Block Core (`wms.inventory.block`) | ✅ Merged |
| **INV-003** | Operational Block Matching Query API (Single Candidate) | ✅ Merged |
| **INV-004** | Operational Block Availability Guard (Single Candidate) | ✅ Merged |
| **INV-005** | Operational Block Batch Matching API (`get_blocked_quants`) | ✅ Current |
| **INV-006+** | Aggregate Block-Aware Availability Engine (Diferido) | ⏸ Siguiente |
| **INV-007+** | Operational Event Journal (`wms.inventory.event`) | ⏸ Diferido |
| **INV-008+** | Audit Log (`wms.audit.log`) | ⏸ Diferido |
| **INV-009+** | Integration Outbox (`wms.outbox`) | ⏸ Diferido |

---

## Dependencias

- `wms_core`: Base y framework de seguridad/RBAC del WMS.
- `wms_warehouse_master`: Autoridad topológica WMS y semántica de ubicaciones (`wms_location_role`).
- `stock`: Módulo estándar de inventario de Odoo (`stock.quant`, `stock.move`, `stock.move.line`, `stock.location`).
