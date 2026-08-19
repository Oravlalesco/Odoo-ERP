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

## Future Responsibilities

As the WMS evolves, this module will contain:

- `wms_location_role` — operational function of a location (STORAGE, RECEIVING, STAGING, DOCK, etc.)
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
