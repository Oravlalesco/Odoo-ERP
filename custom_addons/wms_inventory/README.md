# WMS Inventory Core

Módulo del dominio de inventario para el Warehouse Management System (WMS).

---

## Propósito y Límites Arquitectónicos (Fase 5 — Inventory Core / ADR-001, ADR-011, ADR-012, ADR-019, ADR-026)

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

### 4. Bloqueos Operacionales y Disponibilidad WMS (`wms.inventory.block` — INV-002..INV-006)
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

### 5. Journal Operacional de Inventario (`wms.inventory.event` — INV-008)
- **Persistencia Append-Only**:
  - Exactamente 13 campos funcionales: `company_id`, `occurred_at`, `event_type`, `product_id`, `lot_id`, `package_id`, `owner_id`, `source_location_id`, `dest_location_id`, `quantity`, `operator_id`, `warehouse_id`, `correlation_id`.
  - Catálogo inicial exacto de 7 `event_type`: `RECEIVE`, `MOVE`, `RELEASE`, `PUTAWAY`, `PICK`, `PACK`, `UNPACK`.
  - Cantidad normalizada a `product_id.uom_id` con DB CHECK `quantity > 0`.
  - Invariante de integridad: `lot_id.product_id == product_id`.
  - `package_id` referencia directamente `stock.package` (Handling Unit física según ADR-013).
  - Inmutabilidad server-side: `create()` directo, `write()` y `unlink()` bloqueados con `UserError`.
- **API Privada de Inserción Batch**:
  - `_append_events(vals_list, correlation_id=None)`: Asigna de forma server-owned `occurred_at` (mismo timestamp para todo el batch), `operator_id` (`env.user`) y `correlation_id` (UUID4 común o explícito), ejecutando una única creación multi-record ORM.
- **Límites de ADR-019**:
  - INV-008 crea la persistencia append-only del journal, pero **ADR-019 todavía no se considera satisfecho** hasta que exista el Outbox (INV-010) y el boundary de mutación cree Event + Outbox dentro de la misma transacción.
  - Cero hooks automáticos sobre `stock.quant` o `stock.move`. Los eventos se emitirán desde comandos operacionales WMS explícitos.

### 6. Bandeja de Salida Transaccional (`wms.outbox` — INV-010A)
- **Persistencia Domain-Neutral**:
  - Exactamente 12 campos funcionales: `company_id`, `message_id`, `created_at`, `event_name`, `schema_version`, `payload`, `correlation_id`, `status`, `attempt_count`, `next_attempt_at`, `published_at`, `last_error`.
  - Sin claves foráneas a modelos de dominio (`quant_id`, `stock_move_id`, `package_id`, `inventory_event_id`).
  - Unicidad global de DB sobre `message_id` (UUID4 server-owned) para deduplicación por consumidores downstream.
  - Validación estricta: `schema_version > 0`, `attempt_count >= 0`, `payload` tipo dict (JSON).
  - Inmutabilidad server-side: `create()` directo, `write()` y `unlink()` bloqueados con `UserError`.
- **API Privada de Inserción Batch**:
  - `_enqueue_messages(messages, correlation_id=None)`: Asigna de forma server-owned `created_at` (mismo timestamp para todo el batch), `correlation_id` (UUID4 común o explícito no vacío), `message_id` (UUID4 único por fila), e inicializa obligatoriamente en `status='PENDING'`, `attempt_count=0`, `next_attempt_at=False`, `published_at=False`, `last_error=False`. Ejecuta una única creación multi-record ORM sin `sudo`.
- **Frontera Arquitectónica y ADR-019**:
  - INV-010A implementa el núcleo de persistencia del Outbox como base para entrega at-least-once.
  - **ADR-019 no queda completado en este slice**: Se dispone de persistencia de eventos (INV-008) y de outbox (INV-010A), pero la frontera transaccional atómica que combine mutación física de stock + evento + outbox se implementará en INV-010B.
  - Cero dispatcher, locking, retry, DLQ o conexión a RabbitMQ en este slice (diferidos a infraestructura asíncrona).

---

## Hoja de Ruta del Dominio de Inventario

| Tarea | Capacidad | Estado |
|---|---|---|
| **INV-001** | Bootstrap WMS Inventory Core (Scaffold & Dependencies) | ✅ Merged |
| **INV-002** | Operational Inventory Block Core (`wms.inventory.block`) | ✅ Merged |
| **INV-003** | Operational Block Matching Query API (Single Candidate) | ✅ Merged |
| **INV-004** | Operational Block Availability Guard (Single Candidate, `strict=True`) | ✅ Merged |
| **INV-005** | Operational Block Batch Matching API (`get_blocked_quants`) | ✅ Merged |
| **INV-006** | Aggregate Block-Aware Availability Engine (`strict=False`) | ✅ Merged |
| **INV-007** | Location-Role Operational Eligibility & Allocation Integration | ⏸ Diferido |
| **INV-008** | Operational Event Journal Core (`wms.inventory.event`) | ✅ Merged |
| **INV-009** | Audit Log (`wms.audit.log`) | ⏸ Diferido |
| **INV-010A** | Transactional Outbox Persistence Core (`wms.outbox`) | 🔧 Current |
| **INV-010B** | Atomic Event + Outbox Boundary | ⏭ Siguiente Prerrequisito |


---

## Dependencias

- `wms_core`: Base y framework de seguridad/RBAC del WMS.
- `wms_warehouse_master`: Autoridad topológica WMS y semántica de ubicaciones (`wms_location_role`).
- `stock`: Módulo estándar de inventario de Odoo (`stock.quant`, `stock.move`, `stock.move.line`, `stock.location`, `stock.package`, `stock.lot`).
