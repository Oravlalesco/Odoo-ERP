# Capability Matrix — Resumen Ejecutivo

Resumen rápido de la [Capability Matrix completa](../../../docs/01-dominios/00-odoo19-capability-matrix.md) para referencia durante el desarrollo.

---

## Modelos que se REUTILIZAN tal cual (NO recrear)

| Modelo | Funcionalidades clave ya incluidas |
|---|---|
| `stock.quant` | `quantity`, `reserved_quantity`, `available_quantity`, `in_date`, `owner_id`, `warehouse_id`, `storage_category_id` |
| `stock.move` / `stock.move.line` | Estados, reservas, `_action_assign()`, `lot_id`, `package_id`, `owner_id` |
| `stock.picking` / `stock.picking.batch` | Como registro logístico (NO como Work) |
| `stock.package` | Jerarquía (`parent_package_id`), `package_type_id`, `location_id`, `owner_id`, `shipping_weight`, `pack_date`, `valid_sscc` |
| `stock.package.type` | Dimensiones, `base_weight`, `max_weight`, `barcode`, `package_use`, capacidades de almacenamiento |
| `stock.location` | Jerarquía, `barcode`, `warehouse_id`, `removal_strategy_id`, `putaway_rule_ids`, `storage_category_id`, `cyclic_inventory_frequency`, `replenish_location`, `net_weight`, `is_empty` |
| `stock.warehouse` | Identificación, `reception_steps`/`delivery_steps`, tipos de operación, routes |
| `stock.route` / `stock.rule` | Pull/push routes, procurement rules, multi-step |
| `product.product` / `product.template` | Maestro, `tracking`, `uom_id`, `weight`, `volume`, `barcode`, `categ_id` |
| `product.packaging` | `name`, `qty`, `barcode` |
| `stock.lot` | `expiration_date`, `use_date`, `removal_date`, `alert_date` |
| `stock.storage.category` | Capacidad por producto, tipo de paquete, peso; `allow_new_product` |
| Removal strategies | FIFO, LIFO, FEFO, Closest Location |

## Modelos que se EXTIENDEN (`_inherit`)

| Modelo | Qué se agrega |
|---|---|
| `stock.location` | `wms_location_role`, `pick_sequence`, `travel_sequence`, temperatura, hazmat, `max_hu_count`, volumen |
| `stock.warehouse` | Configuraciones WMS específicas |
| `stock.package` | Estado HU, `seal_number`, `hu_operational_class`, work references, operation history |
| `stock.lot` | Estado de calidad WMS |
| `stock.storage.category` | Restricciones WMS (temperatura, hazmat) |
| `product.packaging` | Referenciado desde `wms.product.logistics` (`pick_packaging_id`, etc.) |

## Modelos que se CREAN NUEVOS (prefijo `wms.`)

| Dominio | Modelos |
|---|---|
| Work Engine | `wms.work`, `wms.work.line`, `wms.work_type`, `wms.work_class`, `wms.work_template` |
| Queue Engine | `wms.queue`, `wms.queue.assignment` |
| Resource Engine | `wms.resource`, `wms.resource.type`, `wms.certification` |
| Rule Engine | `wms.policy`, `wms.policy.condition`, `wms.policy.action` |
| Exception Engine | `wms.exception`, `wms.exception.type` |
| Inventory Events | `wms.inventory.event` |
| Integration | `wms.outbox`, `wms.inbox`, `wms.integration.event` |
| Control Tower | `wms.kpi`, `wms.alert` |
| ASN | `wms.asn`, `wms.asn.line` |
| Dock/Yard | `wms.dock`, `wms.appointment`, `wms.gate.visit` |
| Shipment | `wms.shipment`, `wms.manifest` |
| Allocation | `wms.allocation`, `wms.allocation.line` |
| Wave | `wms.wave`, `wms.wave.template` |
| Product Logistics | `wms.product.logistics` |
| Audit | `wms.audit.log` |

## ⚠️ Lo que NO se debe tocar

- Identidad lógica de `stock.quant` (el `GROUP BY` de `_merge_quants()`)
- Merge logic interna de quants
- Reservation internals de Odoo
- `stock.location.usage` (usar `wms_location_role` en su lugar)
