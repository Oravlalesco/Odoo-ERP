---
name: odoo-model-design
description: >-
  Usar este skill cuando el usuario pida crear o modificar modelos de datos en Odoo
  (clases Python con _name, _inherit, fields, etc.), diseñar relaciones entre modelos,
  extender modelos existentes de Odoo, o cuando se trabaje con el ORM. Incluye las
  restricciones ADR del proyecto para stock.quant, stock.package y stock.location.
---

# Diseño de Modelos ORM — Odoo 19

Guía para diseñar modelos de datos en Odoo 19 respetando los ADRs y convenciones de este proyecto WMS.

---

## Tipos de Herencia en Odoo

### 1. Extensión in-place (`_inherit` sin `_name`)

Agrega campos o métodos a un modelo existente **sin crear tabla nueva**.

```python
from odoo import models, fields

class StockLocationWms(models.Model):
    """Extensión de ubicación con campos WMS."""
    _inherit = 'stock.location'

    # Catálogo aprobado: 12 roles operacionales WMS.
    # wms_location_role es OPCIONAL (default=False).
    # False = ubicación no clasificada por el WMS.
    #
    # INVARIANTE (ADR-026):
    #   Si wms_location_role tiene valor, usage DEBE ser 'internal'.
    #   Nunca modificar ni agregar valores a stock.location.usage.
    wms_location_role = fields.Selection([
        ('STORAGE', 'Storage'),
        ('RESERVE_STORAGE', 'Reserve Storage'),
        ('PICK_FACE', 'Pick Face'),
        ('RECEIVING', 'Receiving'),
        ('QUALITY_HOLD', 'Quality Hold'),
        ('QUARANTINE', 'Quarantine'),
        ('DAMAGE', 'Damage'),
        ('STAGING', 'Staging'),
        ('CONSOLIDATION', 'Consolidation'),
        ('PACKING', 'Packing'),
        ('CROSS_DOCK', 'Cross-Dock'),
        ('DOCK', 'Dock'),
    ], string='WMS Location Role', default=False,
       help='Operational function of this location within the WMS. '
            'Does not replace stock.location.usage. '
            'Only valid on locations with usage=internal.')
    pick_sequence = fields.Integer(
        string='Secuencia de picking',
        help='Orden de recorrido para picking optimizado')
```

### 2. Modelo nuevo (`_name` propio)

Crea una tabla nueva en la base de datos.

```python
class WmsWork(models.Model):
    """Unidad de trabajo dirigido del WMS."""
    _name = 'wms.work'
    _description = 'Trabajo WMS'
    _order = 'priority desc, deadline asc'
    _rec_name = 'reference'

    reference = fields.Char(
        string='Referencia', required=True, copy=False, readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('wms.work'))
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('ready', 'Listo'),
        ('assigned', 'Asignado'),
        ('in_progress', 'En progreso'),
        ('completed', 'Completado'),
        ('exception', 'Excepción'),
        ('reclaimable', 'Reclamable'),
        ('reconciliation_required', 'Requiere reconciliación'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', default='draft', required=True, tracking=True)
    priority = fields.Integer(string='Prioridad', default=50)
    deadline = fields.Datetime(string='Fecha límite')
```

### 3. Modelo satélite con relación 1:0..1 (Many2one + UNIQUE)

Cuando un modelo WMS es un **complemento opcional** de un modelo de Odoo
(no una especialización "es un tipo de"), usar `Many2one` + `models.Constraint(UNIQUE)`:

```text
1 product.template
        │
        │ 0..1
        ▼
wms.product.logistics
```

```python
class WmsProductLogistics(models.Model):
    """Perfil logístico WMS — complemento opcional de product.template."""
    _name = 'wms.product.logistics'
    _description = 'Perfil logístico WMS'

    product_tmpl_id = fields.Many2one(
        'product.template', required=True, ondelete='cascade',
        index=True, string='Producto')
    abc_class = fields.Selection([
        ('A', 'A — Alta rotación'),
        ('B', 'B — Media rotación'),
        ('C', 'C — Baja rotación'),
    ], string='Clase ABC', default='C')

    # Garantiza relación 1:0..1 a nivel de base de datos
    _product_tmpl_unique = models.Constraint(
        'UNIQUE(product_tmpl_id)',
        'Solo puede existir un perfil logístico por producto.')
```

### ⚠️ NO usar `_inherits` (delegation inheritance) en este proyecto

`_inherits` delega **todos** los campos del modelo padre al hijo, creando
la ilusión de que el hijo "es" el padre. Problemas:

| Problema | Impacto |
|---|---|
| No garantiza 1:0..1 | Sin UNIQUE, múltiples registros pueden apuntar al mismo padre |
| Delega toda la interfaz | `wms.product.logistics` expondría todos los campos de `product.template` |
| Confunde la API | `logistics.name` devolvería el nombre del producto — ¿es eso lo que queremos? |
| Complejidad en queries | JOINs implícitos en cada lectura |

**Regla del proyecto**: Preferir `Many2one` + `UNIQUE constraint` sobre `_inherits` para modelos satélite WMS. Solo considerar `_inherits` si el modelo realmente **es un tipo de** otro (ej: una especialización que necesita comportarse como el padre en toda la API).


---

## ⚠️ Restricciones ADR Obligatorias

### ADR-011: NO ampliar la identidad lógica de `stock.quant`

Odoo consolida quants con `_merge_quants()` agrupando por:
```
(product_id, company_id, location_id, lot_id, package_id, owner_id)
```

**PROHIBIDO** agregar campos como `inventory_status` o `quality_status` al quant sin analizar completamente el impacto en `_merge_quants()`, gathering, reservations y moves.

### ADR-012: Inventory Status vive en ubicaciones, no en quants

| Necesidad | Solución | Dónde vive |
|---|---|---|
| Quality Hold | Mover a ubicación `QUALITY_HOLD` | `stock.location` |
| Quarantine | Mover a ubicación `QUARANTINE` | `stock.location` |
| Damage | Mover a ubicación `DAMAGE` | `stock.location` |
| Bloqueo operacional | `wms.inventory.block` | Modelo nuevo WMS |

### ADR-013: `stock.package` es la base de Handling Units

**NO** crear `wms.handling.unit`. La HU es `stock.package` extendido con campos WMS.

### ADR-026: `stock.location.usage` conserva la semántica Odoo

**NO** crear valores nuevos en `usage`. Usar `wms_location_role` para semántica WMS. Todas las locations WMS mantienen `usage='internal'`.

---

## Tipos de Campos

### Campos Básicos

```python
name = fields.Char(string='Nombre', required=True, translate=True)
description = fields.Text(string='Descripción')
quantity = fields.Float(string='Cantidad', digits='Product Unit of Measure')
is_active = fields.Boolean(string='Activo', default=True)
date_planned = fields.Datetime(string='Fecha planificada')
amount = fields.Monetary(string='Monto', currency_field='currency_id')
priority = fields.Integer(string='Prioridad', default=50)
```

### Campos Selection

```python
state = fields.Selection([
    ('draft', 'Borrador'),
    ('confirmed', 'Confirmado'),
    ('done', 'Hecho'),
], string='Estado', default='draft', required=True)
```

### Campos Relacionales

```python
# Many2one — SIEMPRE definir ondelete
warehouse_id = fields.Many2one(
    'stock.warehouse', string='Bodega', required=True,
    ondelete='restrict')

# One2many — inverso de un Many2one
line_ids = fields.One2many(
    'wms.work.line', 'work_id', string='Líneas')

# Many2many
queue_ids = fields.Many2many(
    'wms.queue', string='Colas compatibles',
    relation='wms_resource_queue_rel',    # Nombre explícito de tabla relación
    column1='resource_id',
    column2='queue_id')
```

### Campos Computed

```python
units_per_pallet = fields.Integer(
    string='Unidades por pallet',
    compute='_compute_units_per_pallet', store=True)

@api.depends('units_per_case', 'cases_per_layer', 'layers_per_pallet')
def _compute_units_per_pallet(self):
    """Calcula el total de unidades por pallet completo."""
    for record in self:
        record.units_per_pallet = (
            record.units_per_case
            * record.cases_per_layer
            * record.layers_per_pallet
        )
```

---

## Constraints e Índices (Odoo 19)

### models.Constraint (reemplaza `_sql_constraints`)

Odoo 19 eliminó `_sql_constraints`. Las constraints se definen como atributos
de clase con `models.Constraint`. El nombre del atributo **debe empezar con `_`**.

```python
class WmsWork(models.Model):
    _name = 'wms.work'
    _description = 'Trabajo WMS'

    # ✅ Odoo 19: models.Constraint como atributo de clase
    _claim_token_unique = models.Constraint(
        'UNIQUE(claim_token)',
        'El claim token debe ser único.')
    _reference_unique = models.Constraint(
        'UNIQUE(reference)',
        'La referencia de trabajo debe ser única.')
    _check_priority_range = models.Constraint(
        'CHECK(priority >= 0 AND priority <= 100)',
        'La prioridad debe estar entre 0 y 100.')

    # ❌ LEGACY — NO usar en Odoo 19:
    # _sql_constraints = [
    #     ('claim_token_unique', 'UNIQUE(claim_token)', '...'),
    # ]
```

### models.Index

Para índices compuestos, usar `models.Index` como atributo de clase:

```python
class WmsWork(models.Model):
    _name = 'wms.work'

    # Índice compuesto para queries frecuentes
    _state_priority_idx = models.Index('(state, priority DESC, deadline ASC)')
    _queue_state_idx = models.Index('(queue_id, state)')
```

### Python Constraints

```python
@api.constrains('priority')
def _check_priority(self):
    """Valida que la prioridad esté en rango válido."""
    for record in self:
        if not (0 <= record.priority <= 100):
            raise ValidationError(
                'La prioridad debe estar entre 0 y 100.')
```

---

## Patrones Comunes del Proyecto

### Modelo con Máquina de Estados

```python
class WmsWork(models.Model):
    _name = 'wms.work'
    _description = 'Trabajo WMS'

    state = fields.Selection([...], default='draft')

    def action_validate(self):
        """Valida el trabajo y lo pasa a estado Listo."""
        self.ensure_one()
        # ... validaciones ...
        self.write({'state': 'ready'})

    def action_cancel(self):
        """Cancela el trabajo."""
        for record in self:
            if record.state in ('completed',):
                raise UserError('No se puede cancelar un trabajo completado.')
            record.state = 'cancelled'
```

### Modelo con Secuencia Automática

```python
@api.model_create_multi
def create(self, vals_list):
    """Asigna secuencia automática al crear."""
    for vals in vals_list:
        if not vals.get('reference'):
            vals['reference'] = self.env['ir.sequence'].next_by_code(
                'wms.work') or '/'
    return super().create(vals_list)
```

### Extensión de Modelo Existente

```python
class StockPackageWms(models.Model):
    """Extensión de stock.package con campos WMS para Handling Units."""
    _inherit = 'stock.package'

    hu_state = fields.Selection([
        ('created', 'Creado'),
        ('in_use', 'En uso'),
        ('sealed', 'Sellado'),
        ('shipped', 'Enviado'),
        ('disposed', 'Descartado'),
    ], string='Estado HU', default='created')
    seal_number = fields.Char(string='Número de sello')
```

---

## Referencia Rápida: Capability Matrix

Antes de crear cualquier modelo, consultar la [Capability Matrix](../../docs/01-dominios/00-odoo19-capability-matrix.md) para verificar:

- ✅ **Reutilizar**: El modelo/campo ya existe en Odoo → NO recrear
- 🔧 **Extender**: Odoo tiene la base → usar `_inherit` para agregar campos
- 🆕 **Crear WMS**: No existe → crear modelo nuevo con prefijo `wms.`
- ⚠️ **No tocar**: Funcionalidad interna de Odoo → NO modificar

Para un resumen ejecutivo, ver [references/capability-matrix-summary.md](./references/capability-matrix-summary.md).

---

## Verificación

1. ¿El modelo tiene `_description` en español?
2. ¿Todos los `Many2one` tienen `ondelete` definido?
3. ¿Las constraints usan `models.Constraint()` (no `_sql_constraints`)?
4. ¿Se verificó la Capability Matrix para no recrear algo que Odoo ya tiene?
5. ¿Se respetan los ADRs (011, 012, 013, 026)?
6. ¿Los campos computed con `store=True` tienen `@api.depends` correcto?
