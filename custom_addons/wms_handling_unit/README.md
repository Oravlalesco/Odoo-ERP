# WMS Handling Unit Core

Módulo del dominio de Unidades de Manipulación (Handling Units) y GS1 para el Warehouse Management System (WMS).

---

## Propósito y Límites Arquitectónicos (Fase 6 — Handling Units / ADR-013)

`wms_handling_unit` implementa el **Dominio de Handling Units y GS1** del Kernel WMS.

### 1. `stock.package` como Fundamento Físico de la HU
- **ADR-013**: La Handling Unit **es `stock.package` extendido** de Odoo 19.
- Queda **estrictamente prohibido crear `wms.handling.unit`** como entidad paralela o sombra de paquetes.
- Toda operación de empaquetado, anidamiento, escaneo, movimiento y pesaje opera directamente sobre la identidad de `stock.package`.

### 2. Capacidades Nativas Upstream en Odoo 19 Pinned
El modelo estándar `stock.package` de Odoo 19 ya provee de forma nativa:
- **Jerarquía y Anidamiento**: `parent_package_id`, `child_package_ids` y jerarquía indexada `parent_path`.
- **Contenido Físico**: `quant_ids` (quants directos) y `contained_quant_ids` (quants en toda la jerarquía de paquetes hijos).
- **Identidad y Referencia**: `name` como identificador/código de barra del paquete.
- **Validación SSCC**: `valid_sscc` (computado booleano que valida si `name` cumple el algoritmo checksum GS1 SSCC-18). No asumir la existencia de un campo nativo `sscc`.
- **Tipo de Paquete**: `package_type_id` vinculado a `stock.package.type` (dimensiones `height`, `width`, `packaging_length`, peso base `base_weight`, peso máximo `max_weight`, `barcode`, `storage_category_capacity_ids`).
- **Ubicación y Compañía**: `location_id` y `company_id` computados determinísticamente a partir del contenido o paquetes contenidos; `company_id` puede ser `False` en paquetes multi-compañía o ubicaciones compartidas.
- **Propietario y Pesaje**: `owner_id`, `shipping_weight` y fecha de empaque `pack_date`.

### 3. Metadata Operativa WMS (`stock.package` — HU-002)
- **Estado de Ciclo de Vida (`hu_state`)**:
  - Valores: `EMPTY` (Vacía), `OPEN` (Abierta), `CLOSED` (Cerrada), `IN_TRANSIT` (En tránsito), `SHIPPED` (Despachada), `RETURNED` (Devuelta), `DISPOSED` (Dada de baja).
  - Opcional, indexado, sin default (`hu_state = False` significa que el ciclo de vida WMS todavía no ha sido inicializado sobre ese paquete).
- **Clasificación Operacional (`hu_class`)**:
  - Valores: `PALLET` (Pallet), `CASE` (Caja), `TOTE` (Tote), `CONTAINER` (Contenedor), `MIXED` (Mixta).
  - Opcional, indexado, sin default (`hu_class = False` significa clasificación no asignada).
- **Sin Sincronizaciones Automáticas**: Las operaciones nativas de Odoo (agregar/retirar quants, cambiar `package_type_id`) no auto-mutan `hu_state` ni auto-infieren `hu_class`. La gobernanza de transiciones queda reservada para futuros comandos WMS explícitos.

### 4. Asignador de Secuencias GS1 SSCC-18 (`wms.sscc.sequence` — HU-003A + HU-003A.1)
- **Modelo Asignador (`wms.sscc.sequence`)**:
  - Campos: `name`, `active`, `company_id`, `gs1_company_prefix` (GCP de 4 a 12 dígitos ASCII), `extension_digit` (0-9), `sequence_id` (Many2one a `ir.sequence`).
  - Constraint de Unicidad Global de Base de Datos: `UNIQUE(gs1_company_prefix, extension_digit)` (impide que dos compañías dentro de la misma base de datos Odoo administren independientemente el mismo namespace GCP + extensión).
  - Reutilización de Contador: `ir.sequence` actúa como contador transaccional puro (`prefix=False`, `suffix=False`, `use_date_range=False`, `number_increment > 0`).
  - API Pública `next_sscc()`: Genera identificadores SSCC-18 válidos (`extension + GCP + serial + check_digit`) calculando el dígito verificador módulo-10 con `get_barcode_check_digit` y validando con `check_barcode_encoding`.
  - Seguridad RBAC: `group_wms_operator` y `group_wms_supervisor` tienen permiso de lectura y ejecución de `next_sscc()`, mientras que `group_wms_manager` y `base.group_system` tienen permisos completos CRUD.

### 5. Asignación Explícita de SSCC a Paquetes (`stock.package.assign_sscc` — HU-003B)
- **Método Público `assign_sscc(sscc_sequence_id)`**:
  - Argumento estricto: `sscc_sequence_id` (entero positivo ID del asignador).
  - Idempotencia: Si el paquete ya posee `valid_sscc=True`, devuelve `name` de inmediato sin consumir secuencia ni acceder al allocator.
  - Guard de Compañía: Exige `package.company_id` resuelto y coincidencia exacta con `allocator.company_id`.
  - Guard de Colisión: Verifica que no existan paquetes visibles con el mismo SSCC generado antes de escribir `name`.
  - RBAC de Intersección: Requiere simultáneamente permiso de escritura sobre `stock.package` (`stock.group_stock_user`) y lectura sobre `wms.sscc.sequence` (`wms_core.group_wms_operator`/supervisor/manager).

### 6. Etiqueta Logística GS1 PDF (`report.wms_handling_unit.report_gs1_logistic_label` — HU-003C1)
- **Acción y Formato de Reporte**:
  - Acción: `action_report_gs1_logistic_label` (tipo `qweb-pdf` sobre `stock.package`).
  - Formato: A6 (105 x 148 mm, Portrait) mediante `paperformat_gs1_logistic_label_a6`.
  - Contenido mínimo canónico: Título de dato (`SSCC`), símbolo de código de barras **GS1-128** (FNC1 + AI `00` + SSCC-18) e Interpretación Legible por Humanos (**HRI**: `(00)<18 dígitos>`).
  - Eligibility Guard: Exige `package.valid_sscc == True` en todos los paquetes del recordset; rechazo atómico con `ValidationError` ante cualquier paquete inválido (sin auto-asignaciones implícitas).
  - Seguridad: Acción disponible para `wms_core.group_wms_operator` (y roles superiores heredados). Modelo técnico `models.AbstractModel` read-only y libre de efectos secundarios.

### 7. Empaque Físico Transaccional (`stock.package._wms_pack_physical` — HU-004A)
- **Primitive Físico Privado `_wms_pack_physical(quant_id, quantity, correlation_id=None)`**:
  - Primer consumidor end-to-end de ADR-019 (mutación física + journal + outbox en una sola transacción PostgreSQL).
  - Mutación física: Reutiliza el mecanismo nativo de relocalización directa de quants de Odoo 19 (`_get_inventory_move_values` + `_action_done()`), preservando la trazabilidad nativa de `stock.move`, `stock.move.line` y `stock.package.history`.
  - Transición de ciclo de vida: `EMPTY -> OPEN`, `OPEN -> OPEN`, adopción de paquete vacío (`False -> OPEN`).
  - Guards estrictos: Scope top-level plano (rechaza anidamiento), validaciones UoM, quants sueltos sin reservas, productos tracked/serial, bloqueos de inventario (`wms.inventory.block`) y tipos de HU permitidos por perfil logístico PLM (`wms.product.logistics`).
  - Persistencia atómica de eventos: Registra `wms.inventory.event` (`PACK`) y `wms.outbox` (`inventory.hu.packed`, schema v1) compartiendo el mismo `correlation_id` mediante `_append_events_with_outbox()`.
  - Frontera de privilegios (Narrow Sudo): Guards y registro de eventos operan en el entorno del operador original (`operator_id` no superuser); la mutación física de stock y transición de `hu_state` ejecutan bajo narrow sudo.

### 8. Desempaque Físico Transaccional (`stock.package._wms_unpack_physical` — HU-004B)
- **Primitive Físico Privado `_wms_unpack_physical(quant_id, quantity, correlation_id=None)`**:
  - Segundo consumidor end-to-end de ADR-019 (mutación física + journal + outbox en una sola transacción PostgreSQL del llamador).
  - Mutación física: Reutiliza el mecanismo nativo de relocalización directa de quants de Odoo 19 (`_get_inventory_move_values` con `package_id=self` y `package_dest_id=False` + `_action_done()`), moviendo el stock de la HU a inventario suelto (*loose*) en la misma ubicación física.
  - Cero registros `stock.package.history`: Al extraer stock a loose (`result_package_id=False`), Odoo nativo no genera entradas de historial de paquete.
  - Cleanup nativo de quant: Ejecuta `quant._quant_tasks()` y nunca vuelve a leer el quant tras la limpieza (para evitar errores por fusión o eliminación de fila).
  - Transición de ciclo de vida: `OPEN -> OPEN` mientras la HU conserve quants (`contained_quant_ids`), y `OPEN -> EMPTY` cuando queda vacía.
  - Guards estrictos: Package hu_state `OPEN`, quant perteneciente a la HU (`quant.package_id == self`), ubicación interna, cero reservas, validaciones UoM, quants con tracking/serial=1.0, y bloqueos de inventario (`wms.inventory.block`).
  - PLM de Admisión: Las reglas PLM (`wms.product.logistics.allowed_hu_type_ids`) son exclusivas de admisión/empaque y no bloquean el desempaque de stock existente.
  - Persistencia atómica de eventos: Registra `wms.inventory.event` (`UNPACK`) y `wms.outbox` (`inventory.hu.unpacked`, schema v1 con payload canónico de 8 claves) compartiendo el mismo `correlation_id` mediante `_append_events_with_outbox()`.
  - Frontera de privilegios (Narrow Sudo): Guards y registro de eventos operan en el entorno del operador original (`operator_id` no superuser); la mutación física de stock y transición de `hu_state` ejecutan bajo narrow sudo.

### 9. División Física Transaccional (`stock.package._wms_split_physical` — HU-004C)
- **Primitive Físico Privado `_wms_split_physical(quant_id, quantity, destination_package_id, correlation_id=None)`**:
  - Tercer consumidor end-to-end de ADR-019 (mutación física paquete a paquete + 2 eventos + 1 outbox en una sola transacción PostgreSQL del llamador).
  - Mutación física directa: Reutiliza el mecanismo nativo de relocalización directa de quants de Odoo 19 (`_get_inventory_move_values` con `package_id=source` y `package_dest_id=destination` + `_action_done()`), transfiriendo stock de la HU fuente a una HU destino vacía en la misma ubicación física.
  - Generación de `stock.package.history`: Odoo nativo crea exactamente un nuevo registro de historial para la HU destino.
  - Preservación y transiciones de ciclo de vida: La HU fuente permanece en `OPEN` y retiene contenido positivo remanente (prohibido vaciado completo); la HU destino transiciona de `False/EMPTY -> OPEN`.
  - Locking pesimista ordenado: `SELECT id FROM stock_package WHERE id IN (...) ORDER BY id FOR UPDATE` previene deadlocks ABBA entre operaciones concurrentes.
  - Guards estrictos: Source `OPEN`, destination `EMPTY/False` sin contenido, quants sin reservas (`uom.is_zero(reserved_quantity)`), validaciones UoM, quants con tracking/serial=1.0, y bloqueos de inventario (`wms.inventory.block`).
  - PLM de Admisión en Destino: Las restricciones PLM (`wms.product.logistics.allowed_hu_type_ids`) y validación de compañía de tipo de paquete aplican exclusivamente a la HU destino; el tipo de la fuente no se reevalúa.
  - Persistencia atómica de eventos: Registra 2 eventos `wms.inventory.event` (`UNPACK` en fuente y `PACK` en destino) y 1 mensaje `wms.outbox` (`inventory.hu.split`, schema v1 con payload canónico de 10 claves) bajo el mismo `correlation_id` mediante `_append_events_with_outbox()`.
  - Frontera de privilegios (Narrow Sudo): Guards y registro de eventos operan en el entorno del operador original (`operator_id` no superuser); la mutación física de stock y transición de `hu_state` ejecutan bajo narrow sudo.

### 10. Consolidación Física Transaccional (`stock.package._wms_merge_physical` — HU-004D)
- **Primitive Físico Privado `_wms_merge_physical(destination_package_id, correlation_id=None)`**:
  - Cuarto consumidor end-to-end de ADR-019 (mutación física paquete a paquete multi-quant en batch + 2N eventos + 1 outbox en una sola transacción PostgreSQL del llamador).
  - Mutación física en batch: Reutiliza el mecanismo nativo `move_quants(package_dest_id=destination)` sobre el recordset de quants positivos de la fuente, generando exactamente un nuevo registro de `stock.package.history` para la HU destino y purgando residuos cero mediante `_quant_tasks()`.
  - Transiciones de ciclo de vida: La HU fuente transiciona de `OPEN -> EMPTY` tras el vaciado completo de quants; la HU destino permanece en `OPEN` acumulando el contenido previo y el consolidado.
  - Locking pesimista ordenado: `SELECT id FROM stock_package WHERE id IN (...) ORDER BY id FOR UPDATE` y locks sobre quants directos previenen deadlocks ABBA en operaciones concurrentes directas y cruzadas recíprocas (A -> B frente a B -> A).
  - Guards estrictos: Ambas HUs en `OPEN`, ambas con contenido físico previo no vacío, rechazo de quants negativos, ubicación única común interna, misma compañía resuelta, cero reservas activas, trazabilidad lote/serie y evaluación individual de los 5 scopes de `wms.inventory.block` sobre cada quant entrante en ambas HUs.
  - PLM de Admisión en Destino: Las restricciones PLM (`wms.product.logistics.allowed_hu_type_ids`) aplican exclusivamente a los productos entrantes contra el `package_type_id` de la HU destino; el tipo de la fuente no se reevalúa.
  - Persistencia atómica de eventos: Registra `2N` eventos `wms.inventory.event` (`UNPACK` en fuente y `PACK` en destino por cada quant transferido) y 1 mensaje `wms.outbox` (`inventory.hu.merged`, schema v1 con 7 claves raíz y 5 claves por línea) bajo el mismo `correlation_id` mediante `_append_events_with_outbox()`.
  - Frontera de privilegios (Narrow Sudo): Guards y registro de eventos operan en el entorno del operador original (`operator_id` no superuser); la mutación física de stock y transición de `hu_state` ejecutan bajo narrow sudo.

### 11. Extensiones WMS Deliberadamente Diferidas (HU-004E+ / HU-005+)
- Etiqueta logística GS1 en formato ZPL para impresoras térmicas directas (HU-003C2).
- Políticas de impresión/reimpresión y auditoría de eventos de impresión (HU-003C3).
- Operaciones de cierre, reapertura y despacho (`close`, `reopen`, `dispatch`).
- Integración con Work y tareas dirigidas (`current_work_id`, `last_work_id`).
- Validaciones de jerarquía multi-nivel y anidamiento dinámico (HU-005+).

---

## Hoja de Ruta del Dominio de Handling Units

| Tarea | Capacidad | Estado |
|---|---|---|
| **HU-001** | Bootstrap WMS Handling Units (Scaffold & Dependencies) | ✅ Merged |
| **HU-002** | Stock Package WMS Core Metadata (`hu_state`, `hu_class`) | ✅ Merged |
| **HU-003A** | SSCC-18 Allocation Core (`wms.sscc.sequence`, `next_sscc()`) | ✅ Merged |
| **HU-003A.1** | Global SSCC Namespace Guard (`UNIQUE(GCP, extension)`) | ✅ Merged |
| **HU-003B** | Package SSCC Assignment (`stock.package.assign_sscc()`) | ✅ Merged |
| **HU-003C1** | GS1 Logistic Label PDF — SSCC-only GS1-128 (`qweb-pdf`, A6) | ✅ Merged |
| **HU-003C2** | GS1 Logistic Label ZPL — SSCC-only | ⏸ Diferido |
| **HU-003C3** | Print/Reprint Policy & Audit | ⏸ Diferido |
| **HU-004A** | Physical Pack Core (`_wms_pack_physical()`, ADR-019) | ✅ Merged |
| **HU-004B** | Physical Unpack Core (`_wms_unpack_physical()`, ADR-019) | ✅ Merged |
| **HU-004C** | Physical Split Core (`_wms_split_physical()`, ADR-019) | ✅ Merged |
| **HU-004D** | Physical Merge Core (`_wms_merge_physical()`, ADR-019) | ✅ Merged |
| **HU-004E+** | HU Operation Engine (`close`, `reopen`, `dispatch`) | ⏸ Diferido |
| **HU-005+** | Multi-level Hierarchy & Nesting Validations | ⏸ Diferido |

---

## Dependencias

- `wms_core`: Base y framework de seguridad/RBAC del WMS.
- `wms_warehouse_master`: Autoridad topológica WMS y semántica de ubicaciones (`wms_location_role`).
- `wms_product_logistics`: Perfiles logísticos de producto y tipos de HU permitidos/por defecto (`allowed_hu_type_ids`, `default_hu_type_id`).
- `wms_inventory`: Journal de eventos de inventario (`wms.inventory.event`), outbox transaccional (`wms.outbox`), bloqueos de inventario (`wms.inventory.block`) y primitive de boundary atómico.
- `stock`: Módulo estándar de inventario y paquetes de Odoo (`stock.package`, `stock.package.type`, `stock.quant`, `stock.location`).
