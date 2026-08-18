---
name: odoo-views-ui
description: >-
  Usar este skill cuando el usuario pida crear o modificar vistas de Odoo (form,
  tree/list, kanban, search, pivot, graph, calendar), definir menús, acciones de
  ventana, o personalizar la interfaz de usuario de un módulo. También aplica para
  herencia de vistas con xpath.
---

# Vistas y UI — Odoo 19

Guía para crear vistas XML, menús y acciones en módulos Odoo 19.

---

## Tipos de Vista

| Tipo | Uso principal | Cuándo usar |
|---|---|---|
| `form` | Detalle de un registro | Siempre — es la vista principal de edición |
| `list` (tree) | Lista tabular de registros | Siempre — es la vista principal de navegación |
| `kanban` | Tarjetas visuales por columnas | Cuando hay estados/etapas visuales |
| `search` | Filtros y agrupaciones | Siempre — complementa list y kanban |
| `pivot` | Tabla dinámica | Análisis y reporting |
| `graph` | Gráficos | Visualización de métricas |
| `calendar` | Calendario | Eventos con fechas |
| `activity` | Timeline de actividades | Seguimiento de tareas |

---

## Estructura XML de Vistas

### Vista Form

```xml
<record id="wms_work_view_form" model="ir.ui.view">
    <field name="name">wms.work.form</field>
    <field name="model">wms.work</field>
    <field name="arch" type="xml">
        <form string="Trabajo WMS">
            <!-- Statusbar para máquina de estados -->
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
                <!-- Ribbon para estados especiales -->
                <div class="oe_button_box" name="button_box">
                    <button name="action_view_lines" type="object"
                            class="oe_stat_button" icon="fa-list">
                        <field name="line_count" widget="statinfo"
                               string="Líneas"/>
                    </button>
                </div>
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
                        <field name="queue_id"/>
                    </group>
                </group>
                <notebook>
                    <page string="Líneas" name="lines">
                        <field name="line_ids">
                            <list editable="bottom">
                                <field name="sequence" widget="handle"/>
                                <field name="action"/>
                                <field name="location_id"/>
                                <field name="location_dest_id"/>
                                <field name="product_id"/>
                                <field name="quantity"/>
                                <field name="line_state"/>
                            </list>
                        </field>
                    </page>
                    <page string="Notas" name="notes">
                        <field name="notes" placeholder="Notas internas..."/>
                    </page>
                </notebook>
            </sheet>
            <chatter/>
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
        <list string="Trabajos WMS" decoration-danger="state == 'exception'"
              decoration-success="state == 'completed'"
              decoration-warning="state == 'reconciliation_required'"
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

### Vista Kanban

```xml
<record id="wms_work_view_kanban" model="ir.ui.view">
    <field name="name">wms.work.kanban</field>
    <field name="model">wms.work</field>
    <field name="arch" type="xml">
        <kanban default_group_by="state" class="o_kanban_small_column">
            <field name="reference"/>
            <field name="state"/>
            <field name="priority"/>
            <field name="assigned_resource_id"/>
            <templates>
                <t t-name="card">
                    <div class="oe_kanban_content">
                        <strong>
                            <field name="reference"/>
                        </strong>
                        <div>
                            <field name="work_type_id"/>
                        </div>
                        <div class="text-muted">
                            Prioridad: <field name="priority"/>
                        </div>
                        <div t-if="record.assigned_resource_id.value">
                            <field name="assigned_resource_id" widget="many2one_avatar"/>
                        </div>
                    </div>
                </t>
            </templates>
        </kanban>
    </field>
</record>
```

### Vista Search

```xml
<record id="wms_work_view_search" model="ir.ui.view">
    <field name="name">wms.work.search</field>
    <field name="model">wms.work</field>
    <field name="arch" type="xml">
        <search string="Buscar trabajos">
            <field name="reference"/>
            <field name="work_type_id"/>
            <field name="assigned_resource_id"/>
            <field name="warehouse_id"/>
            <!-- Filtros predefinidos -->
            <filter string="Listos" name="ready"
                    domain="[('state', '=', 'ready')]"/>
            <filter string="En progreso" name="in_progress"
                    domain="[('state', '=', 'in_progress')]"/>
            <filter string="Excepciones" name="exception"
                    domain="[('state', '=', 'exception')]"/>
            <filter string="Requiere reconciliación" name="reconciliation"
                    domain="[('state', '=', 'reconciliation_required')]"/>
            <separator/>
            <filter string="Hoy" name="today"
                    domain="[('create_date', '>=', context_today().strftime('%Y-%m-%d'))]"/>
            <!-- Agrupaciones -->
            <group expand="0" string="Agrupar por">
                <filter string="Estado" name="group_state"
                        context="{'group_by': 'state'}"/>
                <filter string="Tipo" name="group_type"
                        context="{'group_by': 'work_type_id'}"/>
                <filter string="Bodega" name="group_warehouse"
                        context="{'group_by': 'warehouse_id'}"/>
                <filter string="Recurso" name="group_resource"
                        context="{'group_by': 'assigned_resource_id'}"/>
            </group>
        </search>
    </field>
</record>
```

---

## Acciones y Menús

### Acción de Ventana

```xml
<record id="action_wms_work" model="ir.actions.act_window">
    <field name="name">Trabajos WMS</field>
    <field name="res_model">wms.work</field>
    <field name="view_mode">list,form,kanban</field>
    <field name="search_view_id" ref="wms_work_view_search"/>
    <field name="context">{'search_default_ready': 1}</field>
    <field name="help" type="html">
        <p class="o_view_nocontent_smiling_face">
            No hay trabajos WMS
        </p>
        <p>
            Los trabajos se generan automáticamente por los motores de planificación
            (inbound, allocation, replenishment, etc.).
        </p>
    </field>
</record>
```

### Menús

```xml
<!-- Menú raíz del módulo -->
<menuitem id="menu_wms_root"
          name="WMS"
          web_icon="wms_work_engine,static/description/icon.png"
          sequence="40"/>

<!-- Menú de sección -->
<menuitem id="menu_wms_operations"
          name="Operaciones"
          parent="menu_wms_root"
          sequence="10"/>

<!-- Menú que abre la acción -->
<menuitem id="menu_wms_work"
          name="Trabajos"
          parent="menu_wms_operations"
          action="action_wms_work"
          sequence="10"/>
```

---

## Herencia de Vistas (xpath)

Para modificar vistas existentes de Odoo:

```xml
<record id="view_location_form_wms" model="ir.ui.view">
    <field name="name">stock.location.form.wms</field>
    <field name="model">stock.location</field>
    <field name="inherit_id" ref="stock.view_location_form"/>
    <field name="arch" type="xml">
        <!-- Agregar campo después de uno existente -->
        <xpath expr="//field[@name='barcode']" position="after">
            <field name="wms_location_role"/>
        </xpath>

        <!-- Agregar página en un notebook existente -->
        <xpath expr="//notebook" position="inside">
            <page string="WMS" name="wms_config">
                <group>
                    <field name="pick_sequence"/>
                    <field name="travel_sequence"/>
                </group>
            </page>
        </xpath>

        <!-- Reemplazar un campo -->
        <xpath expr="//field[@name='usage']" position="attributes">
            <attribute name="readonly">1</attribute>
        </xpath>
    </field>
</record>
```

### Posiciones de xpath

| Posición | Efecto |
|---|---|
| `before` | Inserta antes del nodo encontrado |
| `after` | Inserta después del nodo encontrado |
| `inside` | Inserta dentro del nodo (al final) |
| `replace` | Reemplaza completamente el nodo |
| `attributes` | Modifica atributos del nodo |

---

## Widgets Comunes

| Widget | Uso | Campo compatible |
|---|---|---|
| `statusbar` | Barra de estados horizontal | Selection |
| `badge` | Etiqueta con color | Selection |
| `many2one_avatar` | Avatar con nombre | Many2one |
| `many2many_tags` | Tags con colores | Many2many |
| `monetary` | Formato moneda | Float/Monetary |
| `handle` | Drag & drop para reordenar | Integer (sequence) |
| `progressbar` | Barra de progreso | Float/Integer |
| `radio` | Botones radio | Selection |
| `color_picker` | Selector de color | Integer |
| `html` | Editor HTML enriquecido | Html |

---

## Convenciones de xml_id

| Tipo | Formato | Ejemplo |
|---|---|---|
| Vista form | `<modelo_sin_puntos>_view_form` | `wms_work_view_form` |
| Vista list | `<modelo_sin_puntos>_view_list` | `wms_work_view_list` |
| Vista kanban | `<modelo_sin_puntos>_view_kanban` | `wms_work_view_kanban` |
| Vista search | `<modelo_sin_puntos>_view_search` | `wms_work_view_search` |
| Acción | `action_<modelo_sin_puntos>` | `action_wms_work` |
| Menú raíz | `menu_<modulo>_root` | `menu_wms_root` |
| Menú hijo | `menu_<nombre_descriptivo>` | `menu_wms_work` |

---

## Verificación

1. ¿Todas las vistas tienen un `xml_id` único?
2. ¿Los strings de usuario están en español?
3. ¿La vista form tiene `<header>` con statusbar si el modelo tiene estados?
4. ¿La vista search tiene filtros y agrupaciones relevantes?
5. ¿Las herencias de vista usan `inherit_id` y `xpath` correctos?
6. ¿La acción tiene `help` con mensaje de "sin contenido"?
