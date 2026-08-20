# WMS Product Logistics Master

Product Logistics Domain Module for the Warehouse Management System (WMS).

---

## Purpose

`wms_product_logistics` implements the **Product Logistics Profile** domain (WMS Kernel — Phase 5.5 / ADR-024).

It defines the operational and logistical characteristics of products required by WMS execution engines (Putaway, Allocation, Replenishment, Slotting, Packing, Quality):
- Packaging hierarchy and operational packaging/UOM assignments.
- Pallet configurations (Ti-Hi).
- Physical logistical dimensions and stackability.
- Operational classifications (ABC, Velocity, Temperature, Hazmat).
- Shelf-life control policies.
- Handling Unit (HU) type restrictions.
- Domain strategy profiles (Storage, Putaway, Replenishment, Allocation).
- Quality inspection triggers and sampling rules.

> **Current Status**: **PLM-006A — Quality Inspection Policy Master**. Política maestra de inspección de calidad (`requires_quality_inspection`, `quality_inspection_type`, `quality_sampling_rate`) implementada sobre `wms.product.logistics`. Strategy profile bindings diferidos a PLM-006B.

---

## Architecture & Boundaries (ADR-024)

### One-to-One Model: `wms.product.logistics`

Companion 1:1 de `product.template`:

```text
product.template (Odoo) ◄─── (1:0..1) ───► wms.product.logistics (WMS)
```

**Campos funcionales (PLM-002):**
- `product_tmpl_id` → product.template, required, index, cascade
- `company_id` → related de product_tmpl_id.company_id, store, readonly, puede ser False
- `active` → related de product_tmpl_id.active, store, readonly
- UNIQUE(product_tmpl_id)
- rec_name basado en product_tmpl_id

**Lifecycle:**
- Crear producto NO crea perfil automáticamente
- Archivar producto → perfil queda active=False
- Reactivar producto → perfil vuelve a active=True
- Eliminar producto → perfil eliminado (cascade)
- Eliminar perfil → producto permanece

**Seguridad:**
- Operator / Supervisor: sólo lectura
- Manager / System Admin: CRUD completo
- Record rule: `parent_of` + global products (company_id=False)

**Campos funcionales (PLM-003A):**
- `pick_uom_id` → uom.uom, optional, restrict. Acepta uom_id base O uom_ids.
- `case_uom_id` → uom.uom, optional, restrict. Sólo uom_ids (packaging adicional).
- `pallet_uom_id` → uom.uom, optional, restrict. Sólo uom_ids (packaging adicional).
- Constraint server-side valida pertenencia al producto.
- Reasignar product_tmpl_id revalida UOM seleccionadas.

**Campos funcionales (PLM-003B):**
- `cases_per_layer` → Integer (Ti, WMS-owned configuration).
- `layers_per_pallet` → Integer (Hi, WMS-owned configuration).
- `base_qty_per_case` → Float, compute, readonly, non-stored (derived from Odoo UOM).
- `cases_per_pallet` → Float, compute, readonly, non-stored (derived from Odoo UOM).
- `base_qty_per_pallet` → Float, compute, readonly, non-stored (derived from Odoo UOM).
- Constraint server-side valida consistencia Ti-Hi: `Ti × Hi == cases_per_pallet`.

**Campos funcionales (PLM-004):**
- `abc_class` → Selection (A, B, C), optional, no default.
- `velocity_class` → Selection (FAST, MEDIUM, SLOW, DEAD), optional, no default.
- `temperature_class` → Selection (AMBIENT, CHILLED, FROZEN, ULTRA_FROZEN), optional, no default.
- `hazmat_class` → Selection (NONE, CLASS_1..CLASS_9), optional, no default.
- `stackable` → Boolean (apilable físicamente).
- `max_stack` → Integer (niveles máximos de apilado, >= 0 via DB CHECK).
- `fragile` → Boolean (manipulación frágil, independiente de stackable).
- Constraint server-side valida coherencia stackable ↔ max_stack (`False → 0`, `True → >= 2`).

**Campos funcionales (PLM-005A):**
- `min_shelf_life_receipt_days` → Integer (mínimo de días restantes al recibir, >= 0 via DB CHECK).
- `min_shelf_life_shipping_days` → Integer (mínimo de días restantes al despachar, >= 0 via DB CHECK).

**Campos funcionales (PLM-005B):**
- `allowed_hu_type_ids` → Many2many (`stock.package.type`), optional, no default.
  - Vacío: sin restricción de tipos de HU.
  - No vacío: sólo los tipos listados están permitidos.
- `default_hu_type_id` → Many2one (`stock.package.type`), optional, restrict, no default.
  - Con allowlist no vacío: `default_hu_type_id` DEBE pertenecer a `allowed_hu_type_ids`.
- Reglas multi-company (server-side):
  - Perfil de producto específico de compañía: admite tipos globales (`company_id=False`) o de la misma compañía.
  - Perfil de producto global (`company_id=False`): sólo admite tipos globales (`company_id=False`).
- Reasignación de producto (`product_tmpl_id`) revalida toda la configuración HU.

**Campos funcionales (PLM-006A):**
- `requires_quality_inspection` → Boolean (requerimiento maestro de inspección al recibir).
  - `False` no impide inspecciones decididas dinámicamente por reglas de recepción futuras.
- `quality_inspection_type` → Selection (`VISUAL`, `DIMENSIONAL`, `SAMPLING`), optional, no default.
  - Clasificación/preferencia maestra de inspección.
- `quality_sampling_rate` → Float (porcentaje de muestreo preferido, 0 a 100).
  - Protegido por DB CHECK `quality_sampling_rate >= 0 AND quality_sampling_rate <= 100`.
  - `0.0` indica sin porcentaje de override estático en el maestro de producto.
- Los 3 campos son deliberadamente independientes (sin constraints artificiales de combinación).

- **Odoo 19 Reutilization**:
  - `stock.package` = Instancia física del HU.
  - `stock.package.type` = Catálogo oficial de tipos (dimensiones, peso tara/máximo, `package_use`).
  - `wms.product.logistics` = Perfil de política WMS (allowed y default HU types, y política de calidad únicamente).

> [!NOTE]
> **Odoo UOM como fuente de verdad cuantitativa (PLM-003B)**:
> Odoo `uom.uom` es la fuente de verdad cuantitativa; Ti-Hi sólo añade geometría física WMS.
> Las cantidades por caja y por pallet no se duplican ni se almacenan de forma independiente;
> se derivan dinámicamente mediante los factores de conversión y `_compute_quantity()` de `uom.uom`.

---

## Roadmap of Domain Capabilities

All items below represent future development stages:

| Task | Capability | Status |
|---|---|---|
| **PLM-001** | Module Scaffold & Baseline (`wms_core`, `product`) | ✅ Merged |
| **PLM-002** | Core Identity & One-to-One Link (`wms.product.logistics ↔ product.template`) | ✅ Merged |
| **PLM-003A** | Operational UOM Roles (`pick_uom_id`, `case_uom_id`, `pallet_uom_id`) | ✅ Merged |
| **PLM-003B** | Ti-Hi Configuration & Derived Quantities | ✅ Merged |
| **PLM-004** | Classifications & Handling Attributes (ABC, Velocity, Temp, Hazmat, Stack) | ✅ Merged |
| **PLM-005A** | Shelf-Life Policy Master (`min_shelf_life_receipt_days`, `shipping_days`) | ✅ Merged |
| **PLM-005B** | HU Type Restrictions (`allowed_hu_type_ids`, `default_hu_type_id`) | ✅ Merged |
| **PLM-006A** | Quality Inspection Policy Master (`requires_quality_inspection`, `type`, `rate`) | ✅ Current |
| **PLM-006B** | Strategy Profile Bindings (`storage`, `putaway`, `replenishment`, `allocation`) | ⏸ Deferred |
| **PLM-007** | Product Logistics UI & Views | ⏳ Future |

---

## Non-Responsibilities

The following belong in other domain modules, **not** in `wms_product_logistics`:

| Capability | Module |
|---|---|
| Warehouse topology, zones, locations | `wms_warehouse_master` |
| Quant mutations, stock balances, inventory blocks | `wms_inventory` |
| Directed work execution & assignment | `wms_work` |
| Handling Unit container lifecycle | `wms_handling_unit` |
| Putaway determination engine | `wms_putaway` |
| Allocation / wave engine | `wms_outbound` / `wms_allocation` |

---

## Dependencies

```text
wms_product_logistics ──► wms_core ──► base
                      ├──► product  ──► base
                      └──► stock    ──► base
```
