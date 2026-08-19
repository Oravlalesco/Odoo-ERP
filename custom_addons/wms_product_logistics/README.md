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

> **Current Status**: **PLM-001 Pure Scaffold**. No business models, views, security, or operational logic are implemented in this step.

---

## Architecture & Boundaries (ADR-024)

### One-to-One Model: `wms.product.logistics` *(FUTURE / NOT IMPLEMENTED IN PLM-001)*

Rather than polluting Odoo's core `product.template` with dozens of WMS-specific fields, this domain introduces a dedicated companion model:

```text
product.template (Odoo) ◄─── (1:1) ───► wms.product.logistics (WMS)
```

- **Odoo 19 Reutilization**: Reutiliza el maestro de productos de Odoo 19 (`product.template`, `product.product`, `product.uom`).
- **WMS Scope**: Perfil logístico WMS (`wms.product.logistics`), cálculos Ti-Hi, umbrales de vida útil, clasificaciones de temperatura/hazmat y perfiles de política WMS.

> [!NOTE]
> **Odoo 19 Packaging / UOM Representation**:
> Odoo 19 source verification is pending for the final packaging/UOM mapping before PLM-002. The operational packaging/UOM representation will be verified and frozen prior to implementing `wms.product.logistics`.

---

## Roadmap of Domain Capabilities

All items below represent future development stages:

| Task | Capability | Status |
|---|---|---|
| **PLM-001** | Module Scaffold & Baseline (`wms_core`, `product`) | ✅ Current (Pure Scaffold) |
| **PLM-002** | Core Identity & One-to-One Link (`wms.product.logistics ↔ product.template`) | ⏳ Future |
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
