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

> **Current Status**: **PLM-004 — Classifications & Handling Attributes**. Clasificaciones operacionales (ABC, velocidad, temperatura, hazmat) y atributos de manejo físico (stackable, max_stack, fragile) implementados sobre `wms.product.logistics`.

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

- **Odoo 19 Reutilization**: Reutiliza `product.template.uom_id` (base) y `product.template.uom_ids` (packagings como Many2many `uom.uom`). `product.uom` es la asociación variante+UOM+barcode, no se usa como FK del perfil.

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
| **PLM-004** | Classifications & Handling Attributes (ABC, Velocity, Temp, Hazmat, Stack) | ✅ Current |
| **PLM-005** | Shelf Life Controls & HU Restrictions | ⏳ Future |
| **PLM-006** | Strategy Profiles & Quality Configuration | ⏳ Future |
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
                      └──► product  ──► base
```
