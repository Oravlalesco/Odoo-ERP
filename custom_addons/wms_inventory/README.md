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

### 4. Scaffold Inicial (INV-001)
- **Estado actual**: **INV-001 — Bootstrap WMS Inventory Core**.
- Esta etapa inicial establece exclusivamente el scaffold del módulo, declarando dependencias con `wms_core`, `wms_warehouse_master` y `stock`, sin introducir modelos de datos ni modificaciones sobre tablas estándar.

---

## Capacidades Funcionales Diferidas (Tareas Posteriores)

Las siguientes capacidades forman parte del diseño del dominio de inventario pero quedan diferidas a tareas posteriores:

| Capacidad | Descripción | Estado |
|---|---|---|
| **Operational Block** (`wms.inventory.block`) | Bloqueos operacionales sobre dimensiones lógicas de inventario. El contrato de scopes se define en una tarea posterior. | ⏸ Diferido (INV-002+) |
| **Operational Event Journal** (`wms.inventory.event`) | Registro inmutable de eventos operacionales WMS. | ⏸ Diferido |
| **Audit Log** (`wms.audit.log`) | Trazabilidad y auditoría de mutaciones operativas. | ⏸ Diferido |
| **Integration Outbox** (`wms.outbox`) | Patrón Outbox transaccional para mensajería asíncrona hacia ERP/TMS. | ⏸ Diferido |
| **Políticas de Disponibilidad** | Motores y reglas de cálculo de disponibilidad de inventario. | ⏸ Diferido |

---

## Dependencias

- `wms_core`: Base y framework de seguridad/RBAC del WMS.
- `wms_warehouse_master`: Autoridad topológica WMS y semántica de ubicaciones (`wms_location_role`).
- `stock`: Módulo estándar de inventario de Odoo (`stock.quant`, `stock.move`, `stock.move.line`, `stock.location`).
