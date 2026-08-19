# WMS Warehouse Master

Extends the native Odoo warehouse topology with WMS operational semantics.

---

## Purpose

Add WMS-specific meaning to the physical warehouse structure that Odoo
already manages. Odoo's `stock.warehouse` and `stock.location` remain the
authoritative models for topology — this module **extends** them, it does
not replace them.

---

## Odoo Authority

| Model | Owner | Role |
|---|---|---|
| `stock.warehouse` | Odoo (stock) | Warehouse entity, routing, sequences |
| `stock.location` | Odoo (stock) | Physical/logical location tree, `usage` field |

`wms_warehouse_master` adds operational attributes to these models
but never overrides their core behavior.

---

## Current Capabilities

### `wms_location_role` (stock.location extension)

A `Selection` field on `stock.location` identifying the operational
function of a location within the WMS.

| Role | Description |
|---|---|
| `RECEIVING` | Inbound receiving area |
| `QUALITY_HOLD` | Quality inspection hold |
| `QUARANTINE` | Quarantine isolation |
| `DAMAGE` | Damaged goods area |
| `STORAGE` | Primary bulk storage |
| `RESERVE_STORAGE` | Reserve / overflow storage |
| `PICK_FACE` | Forward pick location |
| `CONSOLIDATION` | Order consolidation area |
| `PACKING` | Packing station |
| `STAGING` | Outbound staging |
| `CROSS_DOCK` | Cross-dock flow-through |
| `DOCK` | Shipping/receiving dock |

**Rules:**
- Default is `False` (location not classified by WMS).
- Only valid on locations with `usage='internal'`.
- Does **not** replace or modify `stock.location.usage`.

---

## Future Responsibilities

As the WMS evolves, this module will contain:

- `wms.zone` — logical grouping of locations for work distribution
- Activity areas
- Storage types and physical capacities
- Operational restrictions per location
- Travel / pick sequencing attributes
- Dock semantics

---

## Non-Responsibilities

The following belong in other modules, **not** in `wms_warehouse_master`:

| Capability | Module |
|---|---|
| Inventory balances / quant management | `wms_inventory` |
| Stock reservation / allocation | `wms_allocation` |
| Work execution / directed work | `wms_work` |
| Handling Units (HU) | `wms_handling_unit` |
| RF / mobile interface | Domain-specific |
| Putaway engine | Domain-specific |
| Picking engine | Domain-specific |

---

## Dependency Rule

```text
wms_warehouse_master
    ├──► wms_core
    └──► stock (Odoo)

wms_core ──╳──► wms_warehouse_master   (PROHIBITED)
```

- Domain modules may depend on `wms_warehouse_master`.
- `wms_core` must NOT depend on `wms_warehouse_master`.
- `wms_warehouse_master` must NOT duplicate native Odoo topology.
