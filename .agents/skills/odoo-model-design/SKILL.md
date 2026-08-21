---
name: odoo-model-design
description: >-
  Usar este skill cuando el usuario pida crear o modificar modelos de datos en Odoo
  (clases Python con _name, _inherit, fields, etc.), diseñar relaciones entre modelos,
  extender modelos existentes de Odoo, o cuando se trabaje con el ORM. Incluye las
  restricciones ADR del proyecto para stock.quant, stock.package y stock.location.
---

# Diseño de Modelos ORM — Odoo 19

Guía para diseñar modelos de datos en Odoo 19 respetando los ADRs, las directivas de `.agents/rules/odoo-project-conventions.md` y la metodología incremental del proyecto WMS.

---

## 🛑 Pre-flight Obligatorio

Antes de diseñar cualquier modelo o campo:

1. **Leer `.agents/rules/odoo-project-conventions.md`** y acatar las directivas `INV-AGENT-001` a `INV-AGENT-008`.
2. **Consultar ADRs aplicables** (`docs/05-decisiones/01-adr.md`).
3. **Verificar estado de `develop`**: Comprobar qué modelos y APIs ya existen realmente.
4. **Verificar Odoo 19 pinned**: Si una decisión depende de campos, UOM o comportamiento nativo, consultar el source pinned oficial registrado en `docs/03-plataforma/09-odoo-baseline-registry.md`.
5. **Leer el Task Contract vigente**: Define el scope exacto de campos y relaciones autorizadas. Los ejemplos de esta skill son ilustrativos y NO autorizan agregar campos o defaults adicionales.
6. **No inferir**: No agregar campos "útiles a futuro", defaults no requeridos, índices prematuros ni modelos satélite especulativos.

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
    # wms_location_role es opcional (sin default contextual).
    # False = ubicación no clasificada por el WMS.
    #
    # INVARIANTE (ADR-026):
    #   Si wms_location_role tiene valor, usage DEBE ser 'internal'.
    #   Nunca modificar ni agregar valores a stock.location.usage.
    wms_location_role = fields.Selection([
        ('STORAGE', 'Almacenamiento'),
        ('RESERVE_STORAGE', 'Almacenamiento de reserva'),
        ('PICK_FACE', 'Frente de Recolección'),
        ('RECEIVING', 'Recepción'),
        ('QUALITY_HOLD', 'Retención de calidad'),
        ('QUARANTINE', 'Cuarentena'),
        ('DAMAGE', 'Merma / Dañado'),
        ('STAGING', 'Preparación'),
        ('CONSOLIDATION', 'Consolidación'),
        ('PACKING', 'Empaque'),
        ('CROSS_DOCK', 'Cruce de Andén'),
        ('DOCK', 'Muelle'),
    ], string='Rol WMS de Ubicación',
       help='Función operacional de esta ubicación dentro del WMS. '
            'No reemplaza stock.location.usage. '
            'Solo válida en ubicaciones con usage=internal.')
    pick_sequence = fields.Integer(
        string='Secuencia de Recolección',
        help='Orden de recorrido para recolección optimizada.')
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
        string='Referencia', required=True, copy=False, readonly=True)
    # Default presente solo cuando el ciclo de vida del Task Contract lo exige explícitamente:
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
    # Sin default salvo especificación contractual:
    priority = fields.Integer(string='Prioridad')
    deadline = fields.Datetime(string='Fecha Límite')
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
    _description = 'Perfil Logístico WMS'

    product_tmpl_id = fields.Many2one(
        'product.template', required=True, ondelete='cascade',
        index=True, string='Producto')
    abc_class = fields.Selection([
        ('A', 'A — Alta rotación'),
        ('B', 'B — Media rotación'),
        ('C', 'C — Baja rotación'),
    ], string='Clase ABC')

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
| Confunde la API | `logistics.name` devolvería el nombre del producto |
| Complejidad en queries | JOINs implícitos en cada lectura |

**Regla del proyecto**: Preferir `Many2one` + `UNIQUE constraint` sobre `_inherits` para modelos satélite WMS.

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
# Precisión Odoo 19 exacta para cantidades de producto (INV-AGENT-002):
quantity = fields.Float(string='Cantidad', digits='Product Unit', required=True)
is_active = fields.Boolean(string='Activo', default=True)  # Default funcional legítimo si requerido
date_planned = fields.Datetime(string='Fecha Planificada')
amount = fields.Monetary(string='Monto', currency_field='currency_id')
priority = fields.Integer(string='Prioridad')  # Sin default salvo requerimiento contractual
```

### Campos Selection

```python
# Keys en inglés, labels en español (INV-AGENT-001):
state = fields.Selection([
    ('draft', 'Borrador'),
    ('confirmed', 'Confirmado'),
    ('done', 'Hecho'),
], string='Estado', default='draft', required=True)
```

### Campos Relacionales

```python
# Many2one — SIEMPRE definir ondelete. Sin default mágico contextual (INV-AGENT-003).
warehouse_id = fields.Many2one(
    'stock.warehouse', string='Almacén', required=True,
    ondelete='restrict', check_company=True, index=True)

# One2many — inverso de un Many2one
line_ids = fields.One2many(
    'wms.work.line', 'work_id', string='Líneas de Trabajo')

# Many2many
queue_ids = fields.Many2many(
    'wms.queue', string='Colas Compatibles',
    relation='wms_resource_queue_rel',    # Nombre explícito de tabla relación
    column1='resource_id',
    column2='queue_id')
```

### Campos Computed

```python
units_per_pallet = fields.Integer(
    string='Unidades por Palé',
    compute='_compute_units_per_pallet', store=True)

@api.depends('units_per_case', 'cases_per_layer', 'layers_per_pallet')
def _compute_units_per_pallet(self):
    """Calcula el total de unidades por palé completo."""
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
    """Valida que la prioridad esté en el rango permitido."""
    for record in self:
        if record.priority and not (0 <= record.priority <= 100):
            raise ValidationError('La prioridad debe estar entre 0 y 100.')
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
    """Asigna secuencia automática al crear si el contrato lo estipula."""
    for vals in vals_list:
        if not vals.get('reference'):
            vals['reference'] = self.env['ir.sequence'].next_by_code(
                'wms.work') or '/'
    return super().create(vals_list)
```

### Extensión de Modelo Existente

```python
class StockPackageWms(models.Model):
    """Extensión WMS existente de stock.package."""
    _inherit = 'stock.package'

    # NOTA ARQUITECTÓNICA (INV-AGENT-006 / INV-AGENT-008):
    # stock.package ya está extendido en develop por wms_handling_unit.
    # No duplicar aquí su schema: consultar siempre la implementación vigente en develop.
    # No asumir un campo `sscc`; la identidad SSCC utiliza el campo nativo stock.package.name.
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

## Checklist de Verificación

1. ¿El modelo tiene `_description` en español?
2. ¿Todos los `string=`, `help=`, labels de `Selection` y comentarios de código están 100% en español (INV-AGENT-001)?
3. ¿Las cantidades de producto usan la precisión Odoo 19 real `digits="Product Unit"` (INV-AGENT-002)?
4. ¿Cada `default=` está respaldado explícitamente por el Task Contract o ADR (sin defaults inferidos/mágicos) (INV-AGENT-003)?
5. ¿Todos los campos `Many2one` tienen `ondelete` definido y `check_company=True` si aplica?
6. ¿Las constraints SQL usan `models.Constraint()` (no `_sql_constraints`) con nombres que empiezan con `_`?
7. ¿Se verificó la Capability Matrix y el source Odoo 19 pinned para no recrear componentes nativos (INV-AGENT-007)?
8. ¿Se respetan los ADRs obligatorios (001, 011, 012, 013, 026)?
9. ¿Los campos computed con `store=True` tienen `@api.depends` correcto?
10. ¿Se evitó introducir campos "útiles para después" no exigidos por el Task Contract (INV-AGENT-008)?
