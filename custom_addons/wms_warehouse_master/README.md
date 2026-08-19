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

## Seguridad de administración

### Quién puede modificar `wms_location_role`

| Rol | Leer | Modificar |
|---|---|---|
| Operator WMS | ✅ (según permisos nativos) | ❌ |
| Supervisor WMS | ✅ (según permisos nativos) | ❌ |
| Manager WMS | ✅ | ✅ |
| System Admin | ✅ | ✅ |

La protección es **server-side** (override de `create`/`write`).
La UI la refleja (`readonly` para usuarios sin permisos), pero no la sustituye.

No se crean ACLs ni record rules adicionales: las ACL de Odoo son
a nivel de modelo y aditivas, no pueden restringir un solo campo.

---


---

### `wms.zone` (modelo propio WMS)

Agrupación lógica dentro de un warehouse para clasificación
operacional y futura distribución de ubicaciones, recursos y trabajo.

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | Char | Nombre humano de la zona |
| `code` | Char(32) | Identificador operacional (auto-uppercase, trim) |
| `warehouse_id` | Many2one | Bodega propietaria (restrict) |
| `company_id` | Related | Derivada de `warehouse_id.company_id` |
| `active` | Boolean | Permite archivar |
| `sequence` | Integer | Ordenamiento configurable |

**Reglas:**
- Identidad operacional: `warehouse_id + code`.
- `code` se normaliza automáticamente (strip + uppercase).
- `code` es único por warehouse (constraint DB).
- Compañía no se administra independientemente.
- Las ubicaciones todavía NO están asignadas a zonas.

**Seguridad:**

| Rol | Leer | Crear | Escribir | Eliminar |
|---|---|---|---|---|
| Operator WMS | ✅ | ❌ | ❌ | ❌ |
| Supervisor WMS | ✅ | ❌ | ❌ | ❌ |
| Manager WMS | ✅ | ✅ | ✅ | ✅ |
| System Admin | ✅ | ✅ | ✅ | ✅ |

Aislamiento multi-company mediante record rule global.

---

### Zone Administration UI

Administración de `wms.zone` desde el backoffice de Odoo.

**Ruta de navegación:**

```text
Inventory → Configuration → Warehouse Management → WMS Zones
```

**Vistas disponibles:**
- List (con drag-and-drop para reordenar secuencia)
- Form
- Search (filtro archivadas, agrupar por bodega/compañía)

**Acceso al menú:**
- WMS Manager + Stock Manager nativo: menú visible
- Operator WMS: sin menú administrativo
- Supervisor WMS: sin menú administrativo
- System Admin: acceso completo

La seguridad sigue siendo server-side (ACL + record rule).
El navigation shell WMS dedicado queda diferido.

---

### Location → Zone Relationship

`stock.location.wms_zone_id` enlaza ubicaciones nativas con el maestro `wms.zone`.

**Campo:**
- `Many2one("wms.zone")`, opcional, `default=False`
- `ondelete='restrict'`, `check_company=True`, `index=True`, `copy=True`

**Invariantes (si `wms_zone_id != False`):**
1. `usage == 'internal'`
2. `warehouse_id != False`
3. `zone.warehouse_id == location.warehouse_id`
4. `company_id != False` (ubicaciones compartidas no pueden tener zona)
5. `zone.company_id == location.company_id`

**Lifecycle:**
- Mover una location a otro warehouse con zone asignada → `ValidationError`
- El usuario debe limpiar `wms_zone_id` antes de mover
- Cambiar `Zone.warehouse_id` con locations asignadas → `ValidationError` (incluye archivadas)
- Cambiar `Zone.warehouse_id` sin locations → permitido
- Archivar una Zone no rompe relaciones existentes

**Seguridad de mutación:**
- Sólo WMS Manager o System Admin pueden asignar/desasignar zona
- Misma política que `wms_location_role` (refactorizado en helper unificado)
- Protección contra `default_wms_zone_id` en contexto

**Administración UI:**
- Campo disponible en formulario nativo de `stock.location`
- Sólo visible en locations internas con warehouse y company asignados
- Domain filtra zonas del mismo warehouse + misma company
- WMS Manager / System Admin: editable
- Operator / Supervisor: sólo lectura
- Quick-create de Zone deshabilitado (usar UI dedicada de WM-005)
- La seguridad server-side sigue siendo autoritativa

---

### Activity Area (`wms.activity.area`)

Subdivisión funcional de una zona WMS.

**Jerarquía:**
```text
Warehouse → Zone → Activity Area
```

**Campo owner:**
- `zone_id` — `Many2one("wms.zone")`, required, `ondelete='restrict'`

**Campos derivados:**
- `warehouse_id` — `related="zone_id.warehouse_id"`, stored, readonly
- `company_id` — `related="zone_id.company_id"`, stored, readonly

**Identidad operacional:**
- `(zone_id, code)` — UNIQUE constraint a nivel DB
- Mismo código en zonas diferentes: permitido
- Código normalizado: `strip().upper()`
- Código vacío: rechazado

**Seguridad:**
- Operator / Supervisor: sólo lectura
- Manager / System Admin: CRUD completo
- Multi-company: record rule global `[('company_id', 'in', company_ids)]`

**Lifecycle:**
- `Zone.unlink()` con Activity Areas → `restrict` (error)
- Archivar Zone no elimina Activity Areas
- Cambiar `zone_id` actualiza warehouse/company automáticamente

**Nota:** No existe todavía un catálogo de tipos de actividad (`activity_type`).
La relación `stock.location ↔ wms.activity.area` no está implementada todavía.

**Administración UI:**
- List / Form / Search disponibles
- Menú: Inventory → Configuration → Warehouse Management → WMS Activity Areas
- `zone_id` configurable, quick-create de Zone deshabilitado
- `warehouse_id` / `company_id` derivados, readonly en UI
- Manager / System Admin: administración
- Operator / Supervisor: no reciben menú administrativo
- Búsqueda: por nombre, código, zona, bodega, compañía
- Filtro: Archivadas
- Agrupación: por Zona, Bodega, Compañía
- La seguridad server-side continúa autoritativa

---

## Future Responsibilities

As the WMS evolves, this module will contain:

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
