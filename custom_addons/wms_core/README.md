# WMS Core

Foundational module for the Warehouse Management System (WMS).

---

## Purpose

Minimal shared infrastructure for all WMS modules.

`wms_core` serves as the single root dependency for the WMS module tree.
It does not implement business logic — it provides only the elements
that are genuinely shared across multiple WMS domains.

---

## Future Responsibilities

As the WMS evolves, `wms_core` will contain **only** elements that are
truly cross-cutting across domain modules:

- Shared base classes (if needed by multiple domains)
- Common constants or enumerations
- Cross-domain event infrastructure (when justified)

> **Principle**: No abstraction is added until a concrete, demonstrated
> need exists in at least two domain modules.

---

## Non-Responsibilities

The following belong in their respective specialized modules, **not** in `wms_core`:

| Capability | Module |
|---|---|
| Inventory management | `wms_inventory` |
| Warehouse topology / locations | `wms_warehouse_master` |
| Directed work engine | `wms_work` |
| Handling Units (HU) | `wms_handling_unit` |
| Allocation / reservation | `wms_allocation` |
| Picking / packing / shipping | Domain-specific modules |
| Domain business rules | Domain-specific modules |

---

## Dependency Rule

```text
wms_inventory ──┐
wms_work ───────┤
wms_warehouse ──┼──► wms_core ──► base
wms_hu ─────────┤
...             ┘

wms_core ──╳──► wms_inventory   (PROHIBITED)
wms_core ──╳──► wms_work        (PROHIBITED)
```

- **WMS modules may depend on `wms_core`**.
- **`wms_core` must NOT depend on any functional WMS module**.

This ensures `wms_core` remains a stable, low-change foundation
that does not create circular dependencies.
