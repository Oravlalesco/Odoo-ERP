# WMS Work Engine

Módulo del dominio de Trabajo Dirigido y Ejecución (Work Execution) para el Warehouse Management System (WMS).

---

## Propósito y Límites Arquitectónicos (Fase 7 — Work Engine / ADR-002 / ADR-003)

`wms_work` establece la frontera técnica y el ownership del **Dominio de Work Execution** en el Kernel WMS.

### 1. `stock.picking ≠ wms.work` (ADR-002, ADR-003)
- **ADR-002**: `stock.picking` es un documento logístico de Nivel A (intención/registro logístico upstream) y **no es una unidad de trabajo ejecutable**.
- **ADR-003**: Las unidades de trabajo físico son modeladas explícitamente como `wms.work` y `wms.work.line`.
- Queda **estrictamente prohibido sobrecargar `stock.picking`** con atributos operacionales de ejecución (colas, asignación a operario/recurso, timers de lease, estados de heartbeat o lógica de RF).
- La ejecución física en piso se desacopla de los documentos logísticos mediante la transformación de intenciones en unidades de trabajo dirigidas.

### 2. Foundations Reutilizadas
`wms_work` se apoya en el conjunto de fundamentos provistos por Odoo 19 y los módulos anteriores del Kernel WMS:

- **Odoo 19 Upstream Pinned**:
  - `stock.picking`: Registro y agrupación logística de Nivel A.
  - `stock.move` y `stock.move.line`: Intención de movimiento y detalle de ejecución física confirmada.
  - `stock.quant`: Fuente única de verdad del inventario en mano.
  - `stock.package`: Identidad y contención física de Handling Units.
  - `stock.location` y `stock.warehouse`: Jerarquía y topología espacial del almacén.
- **WMS Core (`wms_core`)**:
  - Framework central de seguridad RBAC (`group_wms_operator`, `group_wms_supervisor`, `group_wms_manager`).
- **Warehouse Master (`wms_warehouse_master`)**:
  - Autoridad topológica (`wms.zone`, `wms.activity.area`, `wms.storage.type`) y semántica de ubicaciones (`wms_location_role`, `wms_zone_id`, `wms_storage_type_id`).
- **WMS Inventory (`wms_inventory`)**:
  - Bloqueos dimensionales de inventario (`wms.inventory.block`), journal operacional append-only (`wms.inventory.event`), outbox transaccional (`wms.outbox`) y boundary de persistencia atómica `_append_events_with_outbox()` (ADR-019).
- **WMS Handling Unit (`wms_handling_unit`)**:
  - Metadatos de ciclo de vida (`hu_state`, `hu_class`), secuencias GS1 SSCC-18 (`wms.sscc.sequence`) y primitives transaccionales de mutación física (`_wms_pack_physical()`, `_wms_unpack_physical()`, `_wms_split_physical()`, `_wms_merge_physical()`).

### 3. Modelos Core de Persistencia (`wms.work` y `wms.work.line` — WORK-002)
- **`wms.work` (Encabezado de Trabajo Dirigido)**:
  - Identificador único global: `reference` asignado determinísticamente mediante secuencia (`seq_wms_work`, prefijo `WORK/`, padding 8).
  - Almacén y compañía: `warehouse_id` requerido con `check_company=True` y `company_id` derivado indexado.
  - Catálogo de estados canónicos (Work Execution v1.2): `draft`, `ready`, `assigned`, `in_progress`, `completed`, `exception`, `reclaimable`, `reconciliation_required`, `cancelled`.
  - Prioridad determinista: `priority` (0 a 100, default 50) e índice compuesto `(state, priority desc, deadline asc, id)`.
- **`wms.work.line` (Instrucción Física Unitaria)**:
  - Relación: `work_id` requerido con `ondelete="cascade"` y `check_company=True`.
  - Secuencia e integridad: `sequence` requerido con `UNIQUE(work_id, sequence)`.
  - Catálogo de 8 acciones: `pick`, `put`, `move`, `count`, `replenishment`, `load`, `inspect`, `pack`.
  - Dimensiones físicas: `source_location_id`, `dest_location_id`, `product_id`, `product_uom_id`, `lot_id`, `package_id`, `result_package_id`, `owner_id`, `quantity`.
  - Invariantes dimensionales: UOM estricta al conjunto `{product_id.uom_id} ∪ product_id.uom_ids`, lote coincidente con el producto, y cantidad no negativa.
- **Seguridad RBAC y Aislamiento Multi-Compañía**:
  - Roles WMS (`Operator`, `Supervisor`, `Manager`): Permiso de solo lectura (1, 0, 0, 0) para prevenir mutaciones CRUD directas no autorizadas.
  - System Admin: Permisos completos CRUD (1, 1, 1, 1).
  - Reglas globales multi-compañía para `wms.work` y `wms.work.line` (`company_id in company_ids`).

### 4. Capacidades Implementadas en WORK-003
- **Máquina de Estados de Preparación**:
  - Transiciones controladas: `DRAFT ──action_validate()──▶ READY ──action_cancel()──▶ CANCELLED`.
  - Primitive privada `_wms_transition_state(target_state)` con `FOR UPDATE SKIP LOCKED` y semántica atómica all-or-nothing.
  - Validación de líneas obligatorias para pasar a `READY`.
  - Inmutabilidad de cabecera y líneas fuera de `DRAFT`.
  - Idempotencia en re-ejecución de acciones sobre el estado objetivo.

### 5. Capacidades Deliberadamente Diferidas (WORK-004+)
Conforme al enfoque incremental del proyecto, las siguientes capacidades quedan explícitamente diferidas:
- Protocolo de atomic claim, lease temporal y heartbeat (WORK-004+, ADR-015, ADR-016).
- Protocolo ACCEPT como invariante de ejecución del dominio (Work Execution v1.2), con interacción offline acotada a trabajo previamente asignado (ADR-017) y reconciliación por expiración de lease (ADR-025).
- Detección de expiración de lease, auto-requeue (`RECLAIMABLE -> READY`) y reconciliación obligatoria (`RECONCILIATION_REQUIRED`, ADR-025).
- Comandos transaccionales idempotentes (ADR-010).
- Controllers HTTP y endpoints de API RF / Mobile (ADR-005).
- Queue Engine y Resource Engine (desacoplamiento de colas y recursos operacionales).
- Emisión de eventos operacionales específicos de Work, outbox y métricas de observabilidad (ADR-019, ADR-023).

---

## Hoja de Ruta del Dominio de Work Engine

| Tarea | Capacidad | Estado |
|---|---|---|
| **WORK-001** | Work Engine Bootstrap (Scaffold & Dependencies) | ✅ Merged |
| **WORK-002** | Work Core Data Models (`wms.work`, `wms.work.line`) | ✅ Merged |
| **WORK-003** | Work Preparation Lifecycle & State Machine | 🔧 Current |
| **WORK-004+** | Atomic Claim & Lease Protocol (ADR-015, ADR-016) | ⏸ Diferido |
| **WORK-005+** | Work Execution Commands & ADR-019 Integration | ⏸ Diferido |
| **WORK-006+** | Lease Expiration, Reclaim & Reconciliation (ADR-025) | ⏸ Diferido |
| **WORK-007+** | Work Engine API & RF Protocol Integration (ADR-005, ADR-017) | ⏸ Diferido |

---

## Dependencias

- `wms_core`: Base y framework de seguridad/RBAC del WMS.
- `wms_warehouse_master`: Autoridad topológica WMS y semántica de ubicaciones (`wms_location_role`).
- `wms_inventory`: Bloqueos de inventario, diario de eventos y outbox transaccional.
- `wms_handling_unit`: Handling Units sobre `stock.package`, metadatos HU, SSCC y primitives físicas.
- `stock`: Módulo estándar de inventario y movimientos de Odoo (`stock.picking`, `stock.move`, `stock.move.line`, `stock.quant`, `stock.location`).
