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

### 7. Extensiones WMS Deliberadamente Diferidas (HU-003C2+)
- Etiqueta logística GS1 en formato ZPL para impresoras térmicas directas (HU-003C2).
- Políticas de impresión/reimpresión y auditoría de eventos de impresión (HU-003C3).
- Motor de operaciones de empaque atómicas (`pack`, `unpack`, `split`, `merge`).
- Máquina de estados de ciclo de vida ejecutable.
- Integración con Work y tareas dirigidas (`current_work_id`, `last_work_id`).
- Eventos operacionales de inventario y Outbox atómico (ADR-019).

---

## Hoja de Ruta del Dominio de Handling Units

| Tarea | Capacidad | Estado |
|---|---|---|
| **HU-001** | Bootstrap WMS Handling Units (Scaffold & Dependencies) | ✅ Merged |
| **HU-002** | Stock Package WMS Core Metadata (`hu_state`, `hu_class`) | ✅ Merged |
| **HU-003A** | SSCC-18 Allocation Core (`wms.sscc.sequence`, `next_sscc()`) | ✅ Merged |
| **HU-003A.1** | Global SSCC Namespace Guard (`UNIQUE(GCP, extension)`) | ✅ Merged |
| **HU-003B** | Package SSCC Assignment (`stock.package.assign_sscc()`) | ✅ Merged |
| **HU-003C1** | GS1 Logistic Label PDF — SSCC-only GS1-128 (`qweb-pdf`, A6) | ✅ Current |
| **HU-003C2** | GS1 Logistic Label ZPL — SSCC-only | ⏸ Diferido |
| **HU-003C3** | Print/Reprint Policy & Audit | ⏸ Diferido |
| **HU-004+** | HU Operation Engine (`pack`, `unpack`, `split`, `merge`) | ⏸ Diferido |
| **HU-005+** | Multi-level Hierarchy & Nesting Validations | ⏸ Diferido |

---

## Dependencias

- `wms_core`: Base y framework de seguridad/RBAC del WMS.
- `wms_warehouse_master`: Autoridad topológica WMS y semántica de ubicaciones (`wms_location_role`).
- `wms_product_logistics`: Perfiles logísticos de producto y tipos de HU permitidos/por defecto (`allowed_hu_type_ids`, `default_hu_type_id`).
- `stock`: Módulo estándar de inventario y paquetes de Odoo (`stock.package`, `stock.package.type`, `stock.quant`, `stock.location`).
