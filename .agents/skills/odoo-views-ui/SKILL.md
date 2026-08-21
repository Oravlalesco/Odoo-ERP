---
name: odoo-views-ui
description: >-
  Usar este skill cuando el usuario pida crear o modificar vistas de Odoo (form,
  tree/list, kanban, search, pivot, graph, calendar), definir menús, acciones de
  ventana, o personalizar la interfaz de usuario de un módulo. También aplica para
  herencia de vistas con xpath.
---

# Vistas y UI — Odoo 19

Guía para crear vistas XML, acciones de ventana, menús y herencia con `xpath` en módulos Odoo 19.

---

## 🛑 Directivas de Alcance de UI

1. **Creación Condicional**: Una interfaz de usuario **NO** se crea automáticamente por completitud. Si la tarea actual es puramente core/modelo/seguridad, las vistas están **FUERA DE SCOPE**.
2. **Defensa en Profundidad**: Los atributos XML como `readonly="1"`, `invisible="..."` o `required="1"` son conveniencias visuales de la interfaz de usuario y **NUNCA** reemplazan ACLs, record rules ni validaciones en Python (`@api.constrains`).

---

## Tipos de Vista y Cuándo Usarlas

| Tipo | Uso principal | Cuándo crearla |
|---|---|---|
| `form` | Detalle y edición de registro | Cuando el Task Contract incluya edición o backoffice detallado |
| `list` (tree) | Navegación tabular | Cuando exista flujo de navegación humana en backoffice |
| `search` | Filtros y agrupaciones | Cuando exista una acción o lista que requiera búsqueda |
| `kanban` | Tarjetas por etapas/estados | Cuando el proceso operacional requiera tablero visual |
| `pivot` | Tabla dinámica multidimensional | Cuando el contrato incluya análisis o reporting |
| `graph` | Gráficos y visualizaciones | Para dashboards y métricas de rendimiento |

---

## Estructura XML de Vistas

### Vista Form

```xml
<record id="wms_work_view_form" model="ir.ui.view">
    <field name="name">wms.work.form</field>
    <field name="model">wms.work</field>
    <field name="arch" type="xml">
        <form string="Trabajo WMS">
            <header>
                <button name="action_validate" type="object"
                        string="Validar" class="oe_highlight"
                        invisible="state != 'draft'"/>
                <button name="action_cancel" type="object"
                        string="Cancelar"
                        invisible="state in ('completed', 'cancelled')"
                        confirm="¿Está seguro de cancelar este trabajo?"/>
                <field name="state" widget="statusbar"
                       statusbar_visible="draft,ready,assigned,in_progress,completed"/>
            </header>
            <sheet>
                <div class="oe_title">
                    <h1>
                        <field name="reference" readonly="1"/>
                    </h1>
                </div>
                <group>
                    <group string="General">
                        <field name="work_type_id"/>
                        <field name="warehouse_id"/>
                        <field name="priority"/>
                        <field name="deadline"/>
                    </group>
                    <group string="Asignación">
                        <field name="assigned_resource_id"/>
                        <field name="assigned_at"/>
                    </group>
                </group>
                <notebook>
                    <page string="Líneas de Trabajo" name="lines">
                        <field name="line_ids">
                            <list editable="bottom">
                                <field name="sequence" widget="handle"/>
                                <field name="location_id"/>
                                <field name="location_dest_id"/>
                                <field name="product_id"/>
                                <field name="quantity"/>
                            </list>
                        </field>
                    </page>
                </notebook>
            </sheet>
        </form>
    </field>
</record>
```

### Vista List (Tree)

```xml
<record id="wms_work_view_list" model="ir.ui.view">
    <field name="name">wms.work.list</field>
    <field name="model">wms.work</field>
    <field name="arch" type="xml">
        <list string="Trabajos WMS"
              decoration-danger="state == 'exception'"
              decoration-success="state == 'completed'"
              default_order="priority desc, deadline asc">
            <field name="reference"/>
            <field name="work_type_id"/>
            <field name="warehouse_id"/>
            <field name="priority"/>
            <field name="deadline"/>
            <field name="assigned_resource_id"/>
            <field name="state" widget="badge"
                   decoration-info="state == 'ready'"
                   decoration-success="state == 'completed'"
                   decoration-danger="state == 'exception'"/>
        </list>
    </field>
</record>
```

### Vista Search

```xml
<record id="wms_work_view_search" model="ir.ui.view">
    <field name="name">wms.work.search</field>
    <field name="model">wms.work</field>
    <field name="arch" type="xml">
        <search string="Buscar Trabajos WMS">
            <field name="reference"/>
            <field name="work_type_id"/>
            <field name="assigned_resource_id"/>
            <field name="warehouse_id"/>
            <filter string="Listos" name="ready"
                    domain="[('state', '=', 'ready')]"/>
            <filter string="En Progreso" name="in_progress"
                    domain="[('state', '=', 'in_progress')]"/>
            <group expand="0" string="Agrupar por">
                <filter string="Estado" name="group_state"
                        context="{'group_by': 'state'}"/>
                <filter string="Almacén" name="group_warehouse"
                        context="{'group_by': 'warehouse_id'}"/>
            </group>
        </search>
    </field>
</record>
```

---

## Herencia de Vistas con `xpath`

### Tabla de Posiciones `position`

| Posición | Efecto | Ejemplo de Uso |
|---|---|---|
| `after` | Inserta el nuevo XML inmediatamente **después** del nodo coincidente | Agregar un campo debajo de otro existente |
| `before` | Inserta el nuevo XML inmediatamente **antes** del nodo coincidente | Agregar un botón antes del botón primario |
| `inside` | Inserta el nuevo XML como **último hijo** dentro del nodo coincidente | Agregar una página al `<notebook>` o un campo a un `<group>` |
| `replace` | **Reemplaza completamente** el nodo coincidente con el nuevo XML | Sustituir un widget o estructura entera |
| `attributes` | **Modifica atributos** del nodo sin reemplazar su contenido interno | Cambiar visibilidad, clases CSS o required |

### Ejemplos de Herencia

```xml
<!-- 1. Insertar campo después de otro -->
<record id="view_location_form_wms" model="ir.ui.view">
    <field name="name">stock.location.form.wms</field>
    <field name="model">stock.location</field>
    <field name="inherit_id" ref="stock.view_location_form"/>
    <field name="arch" type="xml">
        <xpath expr="//field[@name='barcode']" position="after">
            <field name="wms_location_role"/>
        </xpath>
    </field>
</record>

<!-- 2. Modificar atributos con position="attributes" -->
<record id="view_picking_form_wms_attr" model="ir.ui.view">
    <field name="name">stock.picking.form.wms.attr</field>
    <field name="model">stock.picking</field>
    <field name="inherit_id" ref="stock.view_picking_form"/>
    <field name="arch" type="xml">
        <xpath expr="//button[@name='action_confirm']" position="attributes">
            <attribute name="invisible">state != 'draft' or is_wms_managed</attribute>
        </xpath>
    </field>
</record>
```

---

## Referencia Rápida de Widgets Comunes (Odoo 19)

> **Nota**: Consultar siempre el código fuente Odoo 19 pinned para confirmar widgets y opciones vigentes.

| Widget | Modelo/Campo Típico | Propósito |
|---|---|---|
| `statusbar` | `fields.Selection` | Barra de etapas en el `<header>` del form |
| `badge` | `fields.Selection` en list | Etiqueta coloreada con `decoration-*` |
| `handle` | `fields.Integer` en list editable | Permite reordenar filas por drag & drop |
| `monetary` | `fields.Monetary` | Formato de moneda con símbolo |
| `many2one_avatar_user` | `fields.Many2one('res.users')` | Muestra avatar de usuario junto al nombre |
| `boolean_toggle` | `fields.Boolean` | Interruptor switch tipo toggle |

---

## Convenciones de Nomenclatura para XML IDs

| Tipo de Registro | Convención de `id` | Ejemplo |
|---|---|---|
| Vista Form | `<modelo_sin_puntos>_view_form` | `wms_work_view_form` |
| Vista List | `<modelo_sin_puntos>_view_list` | `wms_work_view_list` |
| Vista Search | `<modelo_sin_puntos>_view_search` | `wms_work_view_search` |
| Vista Heredada | `view_<modelo_sin_puntos>_<extension>` | `view_location_form_wms` |
| Acción de Ventana | `action_<modelo_sin_puntos>` | `action_wms_work` |
| Menú Raíz | `menu_<modulo>_root` | `menu_wms_root` |
| Submenú | `menu_<modulo>_<seccion>` | `menu_wms_operations` |

---

## Checklist de Verificación de UI

1. ¿Las vistas fueron solicitadas **explícitamente** por el Task Contract?
2. ¿Todos los textos visibles (`string=`, `placeholder=`, nombres de menús) están 100% en español (INV-AGENT-001)?
3. ¿Las vistas form tienen `<header>` con botones y statusbar si gestionan ciclo de vida?
4. ¿Los `xml_id` son únicos y siguen las convenciones de nomenclatura del proyecto?
5. ¿Las expresiones `xpath` usan la posición adecuada (`after`, `before`, `inside`, `attributes`, `replace`)?
6. ¿No se delega la seguridad del modelo a validaciones puramente cosméticas de XML?
