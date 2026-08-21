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

### 4. Bloqueos Operacionales de Inventario (`wms.inventory.block`)
- **Estado actual**: **INV-002 — Operational Inventory Block Core**.
- Registro lógico inmutable de bloqueo sobre dimensiones operacionales:
  - `LOCATION`: Bloqueo de ubicación completa (`location_id`).
  - `PRODUCT_LOCATION`: Bloqueo de producto en ubicación (`product_id`, `location_id`).
  - `LOT`: Bloqueo de lote específico (`product_id`, `lot_id`, con validación `product_id == lot_id.product_id`).
  - `PACKAGE`: Bloqueo de paquete / HU (`package_id`).
  - `OWNER_LOCATION`: Bloqueo de inventario consignado por propietario en ubicación (`owner_id`, `location_id`).
- **Tipos de bloqueo**: `CYCLE_COUNT` (Conteo cíclico), `INVESTIGATION` (Investigación), `HOLD` (Retención operacional), `CUSTOMS` (Aduana).
- **Inmutabilidad y ciclo de vida**:
  - `create()` impone server-side `blocked_by=env.user`, `blocked_at=now()`, `released_at=False`.
  - Edición directa (`write()`) y borrado (`unlink()`) estrictamente prohibidos (`UserError`).
  - Única mutación válida: `action_release()`, restringida a Supervisor WMS o System Admin, estableciendo `released_at=now()` con DB CHECK `released_at >= blocked_at`.
- **Multi-compañía**: `check_company=True` en dimensiones físicas y regla de registro global `[('company_id', 'in', company_ids)]`.

---

## Hoja de Ruta del Dominio de Inventario

| Tarea | Capacidad | Estado |
|---|---|---|
| **INV-001** | Bootstrap WMS Inventory Core (Scaffold & Dependencies) | ✅ Merged |
| **INV-002** | Operational Inventory Block Core (`wms.inventory.block`) | ✅ Current |
| **INV-003+** | Availability Engine & Block Matching (Diferido) | ⏸ Siguiente |
| **INV-004+** | Operational Event Journal (`wms.inventory.event`) | ⏸ Diferido |
| **INV-005+** | Audit Log (`wms.audit.log`) | ⏸ Diferido |
| **INV-006+** | Integration Outbox (`wms.outbox`) | ⏸ Diferido |

---

## Dependencias

- `wms_core`: Base y framework de seguridad/RBAC del WMS.
- `wms_warehouse_master`: Autoridad topológica WMS y semántica de ubicaciones (`wms_location_role`).
- `stock`: Módulo estándar de inventario de Odoo (`stock.quant`, `stock.move`, `stock.move.line`, `stock.location`).
