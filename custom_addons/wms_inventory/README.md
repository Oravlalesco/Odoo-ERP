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
- **Estado actual**: **INV-003 — Operational Block Matching Query API**.
- **Persistencia (INV-002)**:
  - Scopes: `LOCATION`, `PRODUCT_LOCATION`, `LOT`, `PACKAGE`, `OWNER_LOCATION`.
  - Tipos: `CYCLE_COUNT`, `INVESTIGATION`, `HOLD`, `CUSTOMS`.
  - Inmutabilidad server-side (`create()` con metadata server-owned, `write()` directo y `unlink()` prohibidos, `action_release()` restringido a Supervisor/Admin).
- **Matching API de Solo Lectura (INV-003)**:
  - `_get_matching_domain(...)`: Construcción determinista con `odoo.fields.Domain`.
  - `get_matching_blocks(...)`: Búsqueda ORM en una sola consulta de todos los bloqueos activos aplicables.
  - `is_blocked(...)`: Verificación booleana ultra rápida con `search_count(limit=1)`.
  - Semántica jerárquica: `LOCATION` y `PACKAGE` cubren ancestros/descendientes (`parent_of`).
  - Sin alteración de disponibilidad ni reservas nativas de Odoo (`_get_available_quantity()`).

---

## Hoja de Ruta del Dominio de Inventario

| Tarea | Capacidad | Estado |
|---|---|---|
| **INV-001** | Bootstrap WMS Inventory Core (Scaffold & Dependencies) | ✅ Merged |
| **INV-002** | Operational Inventory Block Core (`wms.inventory.block`) | ✅ Merged |
| **INV-003** | Operational Block Matching Query API | ✅ Current |
| **INV-004+** | Availability / Allocation Enforcement (Diferido) | ⏸ Siguiente |
| **INV-005+** | Operational Event Journal (`wms.inventory.event`) | ⏸ Diferido |
| **INV-006+** | Audit Log (`wms.audit.log`) | ⏸ Diferido |
| **INV-007+** | Integration Outbox (`wms.outbox`) | ⏸ Diferido |

---

## Dependencias

- `wms_core`: Base y framework de seguridad/RBAC del WMS.
- `wms_warehouse_master`: Autoridad topológica WMS y semántica de ubicaciones (`wms_location_role`).
- `stock`: Módulo estándar de inventario de Odoo (`stock.quant`, `stock.move`, `stock.move.line`, `stock.location`).
