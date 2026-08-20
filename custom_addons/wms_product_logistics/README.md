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

> **Current Status**: **PLM-002 — Core Identity & One-to-One Link**. El modelo `wms.product.logistics` está implementado como companion 1:1 de `product.template`.

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

- **Odoo 19 Reutilization**: Reutiliza el maestro de productos de Odoo 19 (`product.template`, `product.product`). La revisión contra el pinned Odoo 19 source está completada (ver nota abajo).
- **WMS Scope**: Perfil logístico WMS (`wms.product.logistics`), cálculos Ti-Hi, umbrales de vida útil, clasificaciones de temperatura/hazmat y perfiles de política WMS.

> [!NOTE]
> **Odoo 19 Packaging / UOM — Investigación completada (PLM-002)**:
> La revisión del pinned Odoo 19 source confirmó que la representación
> de unidades de medida usa `uom.uom` y `product.uom` (asociado a
> variante/UOM para barcode de packaging).  El supuesto documental
> previo basado en `product.packaging` no es directamente implementable
> sobre el pinned Odoo 19 tal como se encuentra actualmente.
> **La decisión operacional definitiva queda diferida a PLM-003.**
> No se implementa ningún campo de packaging/UOM en PLM-002.

---

## Roadmap of Domain Capabilities

All items below represent future development stages:

| Task | Capability | Status |
|---|---|---|
| **PLM-001** | Module Scaffold & Baseline (`wms_core`, `product`) | ✅ Merged |
| **PLM-002** | Core Identity & One-to-One Link (`wms.product.logistics ↔ product.template`) | ✅ Current |
| **PLM-003** | Operational Packagings / UOMs & Ti-Hi calculations | ⏳ Future |
| **PLM-004** | Classifications & Handling Attributes (ABC, Velocity, Temp, Hazmat, Stack) | ⏳ Future |
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
