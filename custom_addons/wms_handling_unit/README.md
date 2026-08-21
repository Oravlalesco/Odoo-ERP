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

### 3. Integración con Perfil Logístico (PLM)
- `wms_product_logistics` expone sobre el perfil logístico del producto:
  - `allowed_hu_type_ids`: Tipos de HU permitidos para el producto (`Many2many` a `stock.package.type`).
  - `default_hu_type_id`: Tipo de HU por defecto (`Many2one` a `stock.package.type`).

### 4. Extensiones WMS Deliberadamente Diferidas (HU-002+)
En HU-001 (Pure Scaffold) no se introduce ningún modelo ni campo nuevo. Quedan diferidos para fases posteriores:
- Estados de ciclo de vida de HU (`hu_state`).
- Clasificación operacional de HU (`hu_class`), diferida a HU-002.
- Generador de secuencias SSCC-18 WMS (`wms.sscc.sequence`).
- Operaciones de empaque/desempaque atómicas (`pack`, `unpack`, `split`, `merge`).
- Integración con Work y tareas dirigidas (`current_work_id`, `last_work_id`).
- Eventos operacionales de inventario y Outbox atómico (ADR-019).

---

## Hoja de Ruta del Dominio de Handling Units

| Tarea | Capacidad | Estado |
|---|---|---|
| **HU-001** | Bootstrap WMS Handling Units (Scaffold & Dependencies) | ✅ Current |
| **HU-002+** | Stock Package WMS Core / Lifecycle Extension | ⏸ Siguiente |
| **HU-003+** | SSCC-18 Sequence Generator & GS1 Label Engine | ⏸ Diferido |
| **HU-004+** | HU Operation Engine (`pack`, `unpack`, `split`, `merge`) | ⏸ Diferido |
| **HU-005+** | Multi-level Hierarchy & Nesting Validations | ⏸ Diferido |

---

## Dependencias

- `wms_core`: Base y framework de seguridad/RBAC del WMS.
- `wms_warehouse_master`: Autoridad topológica WMS y semántica de ubicaciones (`wms_location_role`).
- `wms_product_logistics`: Perfiles logísticos de producto y tipos de HU permitidos/por defecto (`allowed_hu_type_ids`, `default_hu_type_id`).
- `stock`: Módulo estándar de inventario y paquetes de Odoo (`stock.package`, `stock.package.type`, `stock.quant`, `stock.location`).
