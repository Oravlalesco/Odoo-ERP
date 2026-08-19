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
- WMS security taxonomy (category, privileges, groups)

> **Principle**: No abstraction is added until a concrete, demonstrated
> need exists in at least two domain modules.

---

## Security Baseline

`wms_core` defines the foundational WMS role taxonomy using Odoo 19's
three-level security model:

```text
ir.module.category: WMS
├── res.groups.privilege: WMS Operations
│   ├── res.groups: Operator       (base floor identity)
│   └── res.groups: Supervisor     (implies Operator)
└── res.groups.privilege: WMS Configuration
    └── res.groups: Manager        (implies Supervisor)
```

**What this provides:**
- A shared role identity that all WMS modules can reference.
- A stable hierarchy: Manager → Supervisor → Operator.

**What this does NOT provide:**
- ACLs (`ir.model.access.csv`) — defined by each domain module.
- Record rules — defined by each domain module.
- Command authorization — defined when WMS commands exist.
- Domain-specific roles (Planner, Inventory Controller, etc.).

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
