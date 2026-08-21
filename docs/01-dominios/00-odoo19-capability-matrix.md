# Odoo 19 Community — Capability Matrix (v1.2)

> Análisis detallado de lo que Odoo 19 Community ya posee, qué extenderemos y qué crearemos nuevo.

### Odoo Baseline (ADR-027)

| Propiedad | Valor |
|---|---|
| `odoo_version` | 19.0 |
| `upstream_repository` | odoo/odoo |
| `upstream_commit` | `95f76213d3f732f1d198c740a908e8037c376114` |
| `verified_at` | 2026-08-18 |
| `docker_image` | odoo:19.0 |
| `docker_digest` | TODO — fijar antes de primer desarrollo |
| `capability_matrix_version` | 1.2 |

> Cada actualización de upstream commit requiere re-verificación de esta matriz + regression testing.

## Contexto

### ¿Por qué esta matriz?

La documentación v1.0 subestimaba varias capacidades que Odoo 19 Community ya trae de fábrica. Esto generaba dos riesgos:

1. **Desarrollar lo que ya existe** — desperdiciar esfuerzo reconstruyendo funcionalidad disponible
2. **Romper lo que ya funciona** — modificar la identidad lógica de modelos internos sin entender las consecuencias

Esta matriz inspecciona los módulos `stock`, `stock_picking_batch`, `product`, UOM, packaging, locations, routes y reservations, y clasifica cada funcionalidad en una de cuatro categorías:

| Categoría | Significado |
|---|---|
| ✅ **Reutilizar** | Odoo ya lo tiene y lo usamos tal cual |
| 🔧 **Extender** | Odoo tiene la base, agregaremos campos o lógica |
| 🆕 **Crear WMS** | No existe en Odoo, lo construimos nosotros |
| ⚠️ **No tocar** | Funcionalidad interna de Odoo que no debemos modificar |

---

## 1. Inventario — `stock.quant`

### Modelo: `stock.quant`

La **fuente de verdad del inventario**. Cada quant representa una cantidad de un producto en una ubicación específica.

| Campo / Funcionalidad | Estado | Detalle |
|---|---|---|
| `product_id` | ✅ Reutilizar | Producto |
| `company_id` | ✅ Reutilizar | Compañía |
| `location_id` | ✅ Reutilizar | Ubicación |
| `lot_id` | ✅ Reutilizar | Lote / serial |
| `package_id` | ✅ Reutilizar | Paquete (HU) |
| `owner_id` | ✅ Reutilizar | **Ya existe** — propietario del inventario (3PL) |
| `quantity` | ✅ Reutilizar | Cantidad en mano |
| `reserved_quantity` | ✅ Reutilizar | **Ya existe** — cantidad reservada |
| `available_quantity` | ✅ Reutilizar | **Ya existe** — computed: quantity - reserved |
| `in_date` | ✅ Reutilizar | Fecha de entrada (para FIFO/FEFO) |
| `warehouse_id` | ✅ Reutilizar | **Ya existe** — bodega del quant |
| `storage_category_id` | ✅ Reutilizar | **Ya existe** — categoría de almacenamiento |
| `inventory_status` | ⚠️ **No agregar al quant** | Ver ADR-011/012 más abajo |
| `quality_status` | ⚠️ **No agregar al quant** | Ver ADR-011/012 más abajo |

### ⚠️ ADVERTENCIA CRÍTICA: Identidad Lógica del Quant

Odoo consolida quants usando `_merge_quants()` con el siguiente `GROUP BY`:

```sql
GROUP BY product_id, company_id, location_id, lot_id, package_id, owner_id
```

Si agregamos `inventory_status` o `quality_status` como campos del quant **sin** modificar `_merge_quants()` y toda la lógica interna de gathering, merging, reservations y movimientos:

```text
Quant A: product=SKU-1, location=A03, status=AVAILABLE, qty=100
Quant B: product=SKU-1, location=A03, status=QUARANTINE, qty=100
```

Odoo los consideraría el **mismo quant lógico** y podría fusionarlos → **catastrófico**.

### Decisión de Diseño (ADR-011 / ADR-012)

> **Inventory Status no vive inicialmente en `stock.quant`.**

Alternativas para implementar estados operacionales WMS:

| Necesidad | Solución propuesta | Dónde vive |
|---|---|---|
| Quality Hold | Mover a ubicación tipo `QUALITY_HOLD` o marcar el lote | `stock.location` (tipo) o `stock.lot` (campo) |
| Quarantine | Mover a ubicación tipo `QUARANTINE` | `stock.location` (tipo) |
| Damage | Mover a ubicación tipo `DAMAGE` | `stock.location` (tipo) |
| Operational Block | Bloqueo lógico por dimensiones (`wms.inventory.block`). Persistencia/RBAC (INV-002), Matching API (INV-003), Availability Guard (INV-004), Batch Matching (INV-005), Aggregate Block-Aware Availability (INV-006); Allocation/Reservation diferido. | 🆕 Crear WMS |
| Operational Event Journal | Journal operacional append-only (`wms.inventory.event`). Persistencia, schema 13 campos, 7 event types, RBAC y API privada `_append_events()` (INV-008). | 🆕 Crear WMS |
| Reservation Context | `stock.move` / `stock.move.line` / `wms.allocation` | Modelos existentes + nuevo |

Este enfoque **usa la mecánica de Odoo** (mover a ubicaciones especializadas) en vez de luchar contra ella.

---

## 2. Movimientos — `stock.move` / `stock.move.line`

| Campo / Funcionalidad | Estado | Detalle |
|---|---|---|
| `product_id` | ✅ Reutilizar | Producto |
| `product_uom_qty` / `quantity` | ✅ Reutilizar | Cantidades |
| `location_id` / `location_dest_id` | ✅ Reutilizar | Origen / destino |
| `lot_id` / `lot_name` | ✅ Reutilizar | Trazabilidad |
| `package_id` / `result_package_id` | ✅ Reutilizar | Paquete origen / destino |
| `owner_id` | ✅ Reutilizar | Propietario |
| `state` (draft/waiting/confirmed/assigned/done) | ✅ Reutilizar | Máquina de estados |
| `picking_id` | ✅ Reutilizar | Picking padre |
| `origin` | ✅ Reutilizar | Documento origen |
| `reference` | ✅ Reutilizar | Referencia legible |
| Reservation logic | ✅ Reutilizar | `_action_assign()` maneja reservas |
| Enlace a `wms.work` | 🆕 Crear WMS | Referencia al trabajo dirigido |

---

## 3. Pickings — `stock.picking` / `stock.picking.batch`

| Campo / Funcionalidad | Estado | Detalle |
|---|---|---|
| `stock.picking` completo | ✅ Reutilizar | Como **registro logístico** (Nivel A) |
| `stock.picking.type` (Receipt, Internal, Delivery) | ✅ Reutilizar | Tipos de operación |
| `stock.picking.batch` (batch + wave) | ✅ Reutilizar | Como agrupación logística |
| Wave views en `stock_picking_batch` | ✅ Reutilizar | Vistas de wave incluidas en Community |
| `stock.picking` como Work | ⚠️ **No usar** | ADR-002: `stock.picking ≠ wms.work` |

---

## 4. Paquetes / HU — `stock.package`

> **Nota v1.2**: En Odoo 19 el modelo es `stock.package` (clase Python `StockPackage`, `_name = 'stock.package'`). El `stock.quant` referencia packages via `package_id = fields.Many2one('stock.package', ...)`.

| Campo / Funcionalidad | Estado | Detalle |
|---|---|---|
| `name` (Package Reference) | ✅ Reutilizar | Identificador del paquete |
| `package_type_id` | ✅ Reutilizar | **Ya existe** — link a tipo de paquete |
| `parent_package_id` | ✅ Reutilizar | **Ya existe** — jerarquía padre (pack-in-pack) |
| `location_id` | ✅ Reutilizar | **Ya existe** — ubicación actual |
| `owner_id` | ✅ Reutilizar | **Ya existe** — propietario |
| `shipping_weight` | ✅ Reutilizar | **Ya existe** — peso de envío |
| `pack_date` | ✅ Reutilizar | **Ya existe** — fecha de empaque |
| `quant_ids` | ✅ Reutilizar | **Ya existe** — contenido (relación a quants) |
| `valid_sscc` | ✅ Reutilizar | **Ya existe** — campo computed `_compute_valid_sscc()` con encoder SSCC; `name` se usa como referencia SSCC |
| SSCC-18 Allocator (`wms.sscc.sequence`) | 🔧 HU-003A / HU-003A.1 | Modelo asignador GS1 SSCC-18 sobre `ir.sequence` transaccional con guard global |
| Package SSCC Binding (`assign_sscc()`) | 🔧 HU-003B | Asignación explícita e idempotente de SSCC a `stock.package.name` |
| GS1 Logistic Label PDF (`report_gs1_logistic_label`) | 🔧 HU-003C1 | Etiqueta logística GS1 PDF SSCC-only en GS1-128 (A6 105x148 mm) |
| GS1 Logistic Label ZPL | ⏸ HU-003C2 | Etiqueta logística GS1 en formato ZPL para térmicas (diferido) |
| Print/Reprint Policy & Audit | ⏸ HU-003C3 | Auditoría y políticas de reimpresión de etiquetas (diferido) |
| HU lifecycle (`hu_state`) | 🔧 HU-002 | Metadata persistida (`EMPTY..DISPOSED`, nullable); motor de transiciones diferido |
| `seal_number` | ⏸ Diferido | Número de sello (diferido) |
| `hu_class` | 🔧 HU-002 | Clasificación operacional (`PALLET`, `CASE`, `TOTE`, `CONTAINER`, `MIXED`) |
| Work references | ⏸ Diferido | Enlace a `wms.work` (diferido) |
| HU operation history | ⏸ Diferido | `stock.package.history` nativo reutilizado; modelo semántico WMS diferido |

### `stock.package.type`

| Campo / Funcionalidad | Estado | Detalle |
|---|---|---|
| `height`, `width`, `packaging_length` | ✅ Reutilizar | **Ya existen** — dimensiones (nota: el campo es `packaging_length`, no `length`) |
| `base_weight` | ✅ Reutilizar | **Ya existe** — peso tara |
| `max_weight` | ✅ Reutilizar | **Ya existe** — peso máximo |
| `storage_capacities` | ✅ Reutilizar | **Ya existe** — capacidades de almacenamiento |
| `package_use` | ✅ Reutilizar | **Ya existe** — Selection: `disposable` / `reusable` |
| Restricciones de tipo HU por producto | 🔧 Extender | Enlace M2M/M2O desde `wms.product.logistics` (`allowed_hu_type_ids`, `default_hu_type_id`). PLM-005B. |

**Conclusión**: No necesitamos reconstruir jerarquía, dimensiones ni catálogo de tipos de paquete. Solo agregar semántica y políticas de restricción WMS.

---

## 5. Ubicaciones — `stock.location`

| Campo / Funcionalidad | Estado | Detalle |
|---|---|---|
| Location hierarchy (parent/child) | ✅ Reutilizar | **Ya existe** |
| `barcode` | ✅ Reutilizar | **Ya existe** |
| `warehouse_id` | ✅ Reutilizar | **Ya existe** |
| `removal_strategy_id` (FIFO/LIFO/FEFO/Closest) | ✅ Reutilizar | **Ya existe** |
| `putaway_rule_ids` | ✅ Reutilizar | **Ya existe** — reglas básicas product→location |
| `storage_category_id` | ✅ Reutilizar | **Ya existe** |
| `cyclic_inventory_frequency` | ✅ Reutilizar | **Ya existe** — frecuencia de conteo |
| `replenish_location` | ✅ Reutilizar | **Ya existe** |
| `net_weight` / `forecast_weight` | ✅ Reutilizar | **Ya existe** |
| `is_empty` | ✅ Reutilizar | **Ya existe** — computed |
| Zone (agrupación por zona WMS) | 🔧 Extender | Odoo no tiene "zona" como concepto WMS |
| Activity Area | 🆕 Crear WMS | Áreas de actividad |
| Dock metadata | 🆕 Crear WMS | Tipo dock, estado, capacidades |
| `pick_sequence` / `travel_sequence` | 🔧 Extender | Para optimización de recorrido |
| Temperature range | 🔧 Extender | Rango de temperatura permitido |
| Hazardous compatibility | 🔧 Extender | Clase de material peligroso permitido |
| Max HU count | 🔧 Extender | Máximo de unidades de manejo |
| Capacity volume | 🔧 Extender | Volumen máximo |

---

## 6. Bodega — `stock.warehouse`

| Campo / Funcionalidad | Estado | Detalle |
|---|---|---|
| `name`, `code`, `company_id` | ✅ Reutilizar | Identificación |
| `partner_id` (address) | ✅ Reutilizar | Dirección |
| `reception_steps` / `delivery_steps` | ✅ Reutilizar | 1/2/3 pasos |
| `pick_type_id`, `pack_type_id`, `int_type_id` | ✅ Reutilizar | Tipos de operación |
| Default locations (input, output, QC, pack) | ✅ Reutilizar | Ubicaciones default |
| Routes | ✅ Reutilizar | `stock.route` |
| WMS configuration | 🔧 Extender | Configuraciones WMS específicas |
| Building structure | 🆕 Crear WMS | Edificios dentro de un complejo |

---

## 7. Rutas y Reglas — `stock.route` / `stock.rule`

| Campo / Funcionalidad | Estado | Detalle |
|---|---|---|
| `stock.route` (pull/push) | ✅ Reutilizar | Rutas de reabastecimiento |
| `stock.rule` (procurement) | ✅ Reutilizar | Reglas de procurement |
| Multi-step routes | ✅ Reutilizar | Pick-Pack-Ship configurable |
| WMS-specific routing | 🆕 Crear WMS | Routing interno WMS (topología de bodega) |

---

## 8. Productos — `product.product` / `product.template`

| Campo / Funcionalidad | Estado | Detalle |
|---|---|---|
| `product.template` / `product.product` | ✅ Reutilizar | Maestro de productos |
| `tracking` (none/lot/serial) | ✅ Reutilizar | Control por lote/serial |
| `uom_id` / `uom_ids` | ✅ Reutilizar | UOM base + packagings adicionales (`Many2many uom.uom`) |
| `product.uom` (barcode association) | ✅ Reutilizar | Asociación variante + UOM + barcode |
| `weight` / `volume` | ✅ Reutilizar | Peso y volumen |
| `use_expiration_date` / `expiration_date` | ✅ Reutilizar | Vida útil (en `stock.lot`) |
| `categ_id` | ✅ Reutilizar | Categoría |
| `barcode` | ✅ Reutilizar | Código de barras |
| WMS Logistics Profile | 🆕 Crear WMS | Ver [Product Logistics Master](00-product-logistics-master.md) |
| ABC class, velocity class | 🆕 Crear WMS | Clasificación de rotación (`abc_class`, `velocity_class`). PLM-004. |
| Temperature class, hazmat class | 🆕 Crear WMS | Clases operacionales (`temperature_class`, `hazmat_class`). PLM-004. |
| Atributos de manejo (stackable, max_stack, fragile) | 🆕 Crear WMS | Atributos físicos WMS (`stackable`, `max_stack`, `fragile`). PLM-004. |
| Pick UOM, case UOM, pallet UOM | 🔧 Extender | Vía `uom.uom` + `wms.product.logistics` (`pick_uom_id`, `case_uom_id`, `pallet_uom_id`). PLM-003A. |
| Ti-Hi (cases per layer, layers per pallet) | 🆕 Crear WMS | Configuración física WMS (`cases_per_layer`, `layers_per_pallet`). PLM-003B. |
| Cantidades derivadas de packaging | ✅ Reutilizar | Derivadas de Odoo `uom.uom` (`base_qty_per_case`, `cases_per_pallet`, `base_qty_per_pallet`). PLM-003B. |
| Política de vida útil (receipt days, shipping days) | 🆕 Crear WMS | Mínimos de vida útil restante (`min_shelf_life_receipt_days`, `min_shelf_life_shipping_days`). PLM-005A. |
| Restricciones de tipos HU (allowed_hu_type_ids, default_hu_type_id) | 🔧 Extender | Reutiliza `stock.package.type` vía `wms.product.logistics`. PLM-005B. |
| Política de inspección de calidad (requires, type, rate) | 🆕 Crear WMS | Metadatos maestros en `wms.product.logistics`. PLM-006A. |
| Ejecución de calidad en recepción (inspections, results, checks) | 🆕 Crear WMS | Diferido a dominios Inbound / Quality Engine / Rule Engine. |
| Storage/putaway/replenishment/allocation profiles | ⏸ Diferido | PLM-006B: diferido hasta existencia de entidades de dominio reales y Typed Policy Engine. |
| Vistas administrativas (list, form, search, action) | 🆕 Crear WMS | Vistas administrativas para gestión de `wms.product.logistics`. PLM-007A. |
| Navegación WMS y exposición RBAC (menus) | 🆕 Crear WMS | Jerarquía `WMS` > `Maestros` > `Perfiles logísticos` con RBAC nativo. PLM-007B. |
| Integración contextual desde Producto (`product.template` stat button) | 🆕 Crear WMS | Acceso contextual desde `product.template` al perfil WMS 1:0..1. PLM-007C. |

---

## 9. Lotes — `stock.lot`

| Campo / Funcionalidad | Estado | Detalle |
|---|---|---|
| `name` | ✅ Reutilizar | Número de lote/serial |
| `product_id` | ✅ Reutilizar | Producto |
| `expiration_date` | ✅ Reutilizar | Expiración |
| `use_date` | ✅ Reutilizar | Fecha de uso (best before) |
| `removal_date` | ✅ Reutilizar | Fecha de remoción |
| `alert_date` | ✅ Reutilizar | Fecha de alerta |
| Quality status (WMS) | 🔧 Extender | Estado de calidad WMS a nivel de lote |

---

## 10. Removal Strategies

| Estrategia | Estado | Detalle |
|---|---|---|
| FIFO (First In First Out) | ✅ Reutilizar | Por `in_date` |
| LIFO (Last In First Out) | ✅ Reutilizar | |
| FEFO (First Expired First Out) | ✅ Reutilizar | Por `expiration_date` |
| Closest Location | ✅ Reutilizar | |
| Full Pallet preference | 🆕 Crear WMS | |
| Full Box preference | 🆕 Crear WMS | |
| Least Fragmentation | 🆕 Crear WMS | |
| Customer-specific rules | 🆕 Crear WMS | |

---

## 11. Storage Categories — `stock.storage.category`

| Campo / Funcionalidad | Estado | Detalle |
|---|---|---|
| Capacity by product | ✅ Reutilizar | **Ya existe** |
| Capacity by package type | ✅ Reutilizar | **Ya existe** |
| Capacity by weight | ✅ Reutilizar | **Ya existe** |
| Allow new product (empty/same/mixed) | ✅ Reutilizar | **Ya existe** |
| WMS temperature restrictions | 🔧 Extender | |
| WMS hazmat restrictions | 🔧 Extender | |

---

## 12. Replenishment

| Campo / Funcionalidad | Estado | Detalle |
|---|---|---|
| Reordering rules (min/max) | ✅ Reutilizar | En `stock.warehouse.orderpoint` |
| Route-based replenishment | ✅ Reutilizar | Vía `stock.route` + `stock.rule` |
| Demand-driven replenishment | 🆕 Crear WMS | |
| Wave-driven replenishment | 🆕 Crear WMS | |
| Top-off replenishment | 🆕 Crear WMS | |
| Emergency replenishment | 🆕 Crear WMS | |
| Pick face concept | 🆕 Crear WMS | Odoo no distingue Reserve vs Pick Face |

---

## 13. Funcionalidades 100% Nuevas (WMS)

Estas no tienen equivalente en Odoo y se construyen completamente:

| Dominio | Modelos principales |
|---|---|
| **Work Engine** | `wms.work`, `wms.work.line`, `wms.work_type`, `wms.work_class`, `wms.work_template` |
| **Queue Engine** | `wms.queue`, `wms.queue.assignment` |
| **Resource Engine** | `wms.resource`, `wms.resource.type`, `wms.certification` |
| **Assignment Engine** | `wms.assignment` (scoring, claim, lease) |
| **Rule Engine** | `wms.policy`, `wms.policy.condition`, `wms.policy.action` |
| **RF/Mobile** | `wms.rf.session`, `wms.rf.command` |
| **Exception Engine** | `wms.exception`, `wms.exception.type` |
| **Inventory Events** | `wms.inventory.event` |
| **Audit** | `wms.audit.log` |
| **Integration** | `wms.outbox`, `wms.inbox`, `wms.integration.event` |
| **Control Tower** | `wms.kpi`, `wms.alert` |
| **ASN** | `wms.asn`, `wms.asn.line` |
| **Dock/Yard** | `wms.dock`, `wms.appointment`, `wms.gate.visit` |
| **Shipment** | `wms.shipment`, `wms.manifest` |
| **Allocation** | `wms.allocation`, `wms.allocation.line` |
| **Wave** | `wms.wave`, `wms.wave.template` |
| **Product Logistics** | `wms.product.logistics` |

---

## Resumen Cuantitativo

| Categoría | Cantidad de funcionalidades |
|---|---|
| ✅ Reutilizar tal cual | ~45 |
| 🔧 Extender | ~12 |
| 🆕 Crear nuevo | ~30+ modelos |
| ⚠️ No tocar | 3 (identidad quant, merge logic, reservation internals) |

> **Conclusión clave**: Odoo 19 Community aporta más del 40% de la infraestructura de datos que necesitamos. El WMS se construye **sobre** esta base, no **reemplazándola**.

---

*Documento nuevo para WMS Blueprint v1.1. Referencia cruzada: [ADR-011](../05-decisiones/01-adr.md), [ADR-012](../05-decisiones/01-adr.md), [ADR-013](../05-decisiones/01-adr.md).*
