---
name: odoo-security-access
description: >-
  Usar este skill cuando el usuario pida configurar permisos de acceso, grupos de
  seguridad, ACLs (ir.model.access.csv), record rules (ir.rule), o implementar
  control de acceso basado en roles (RBAC) en módulos Odoo. También aplica cuando
  se pregunte sobre seguridad del WMS (ADR-023).
---

# Seguridad y Permisos — Odoo 19

Guía para configurar grupos, ACLs, record rules y RBAC en módulos Odoo 19.

> **ADR-023**: Security es un cross-cutting concern — cada motor WMS desde su primera versión debe respetar RBAC.

---

## Componentes de Seguridad

| Componente | Archivo | Propósito |
|---|---|---|
| Grupos de seguridad | `security/security.xml` | Definen roles de usuario |
| ACLs (Access Control Lists) | `security/ir.model.access.csv` | Permisos CRUD por modelo y grupo |
| Record Rules | `security/security.xml` | Filtran registros visibles por usuario |
| Superusuario | N/A | `sudo()` bypasea toda seguridad — usar con precaución |

---

## 1. Grupos de Seguridad

Los grupos se definen en XML como registros de `res.groups`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Categoría de módulo (para organizar en Ajustes) -->
    <record id="module_category_wms" model="ir.module.category">
        <field name="name">WMS</field>
        <field name="description">Módulos del Warehouse Management System</field>
        <field name="sequence">50</field>
    </record>

    <!-- Grupo base: Operador WMS -->
    <record id="group_wms_operator" model="res.groups">
        <field name="name">Operador</field>
        <field name="category_id" ref="module_category_wms"/>
        <field name="comment">
            Acceso a operaciones de piso: ejecutar trabajo, confirmar picks/puts,
            reportar excepciones.
        </field>
    </record>

    <!-- Grupo intermedio: Supervisor WMS (hereda de Operador) -->
    <record id="group_wms_supervisor" model="res.groups">
        <field name="name">Supervisor</field>
        <field name="category_id" ref="module_category_wms"/>
        <field name="implied_ids" eval="[(4, ref('group_wms_operator'))]"/>
        <field name="comment">
            Todo lo del operador + gestión de excepciones, reconciliación
            de works, reasignación de trabajo, control tower.
        </field>
    </record>

    <!-- Grupo avanzado: Administrador WMS (hereda de Supervisor) -->
    <record id="group_wms_manager" model="res.groups">
        <field name="name">Administrador</field>
        <field name="category_id" ref="module_category_wms"/>
        <field name="implied_ids" eval="[(4, ref('group_wms_supervisor'))]"/>
        <field name="comment">
            Todo lo del supervisor + configuración de bodegas, zonas, colas,
            políticas, recursos y perfiles logísticos.
        </field>
    </record>
</odoo>
```

### Jerarquía de Grupos Recomendada para el WMS

```text
Administrador WMS (group_wms_manager)
    └── Supervisor WMS (group_wms_supervisor)
            └── Operador WMS (group_wms_operator)
```

`implied_ids` con `(4, ref(...))` hace que al asignar Supervisor, automáticamente se asigne también Operador.

---

## 2. ACLs — `ir.model.access.csv`

Cada línea define permisos CRUD para un modelo y un grupo:

```csv
id,name,model_id/id,group_id/id,perm_read,perm_write,perm_create,perm_unlink
access_wms_work_operator,wms.work.operator,model_wms_work,wms_work_engine.group_wms_operator,1,1,0,0
access_wms_work_supervisor,wms.work.supervisor,model_wms_work,wms_work_engine.group_wms_supervisor,1,1,1,0
access_wms_work_manager,wms.work.manager,model_wms_work,wms_work_engine.group_wms_manager,1,1,1,1
access_wms_work_line_operator,wms.work.line.operator,model_wms_work_line,wms_work_engine.group_wms_operator,1,1,0,0
access_wms_work_line_supervisor,wms.work.line.supervisor,model_wms_work_line,wms_work_engine.group_wms_supervisor,1,1,1,0
access_wms_work_line_manager,wms.work.line.manager,model_wms_work_line,wms_work_engine.group_wms_manager,1,1,1,1
access_wms_work_type_all,wms.work_type.all,model_wms_work_type,base.group_user,1,0,0,0
access_wms_work_type_manager,wms.work_type.manager,model_wms_work_type,wms_work_engine.group_wms_manager,1,1,1,1
```

### Reglas para el CSV

| Columna | Formato | Ejemplo |
|---|---|---|
| `id` | `access_<modelo_underscored>_<grupo>` | `access_wms_work_operator` |
| `name` | `<modelo.dotted>.<grupo>` | `wms.work.operator` |
| `model_id/id` | `model_<modelo_underscored>` | `model_wms_work` |
| `group_id/id` | `<modulo>.<xml_id_grupo>` | `wms_work_engine.group_wms_operator` |
| Permisos | `0` o `1` | `1,1,0,0` (read+write, no create/delete) |

### Matriz de Permisos Típica del WMS

| Modelo | Operador | Supervisor | Administrador |
|---|---|---|---|
| `wms.work` | R, W | R, W, C | R, W, C, D |
| `wms.work.line` | R, W | R, W, C | R, W, C, D |
| `wms.work_type` | R | R | R, W, C, D |
| `wms.queue` | R | R, W | R, W, C, D |
| `wms.resource` | R (propio) | R, W | R, W, C, D |
| `wms.policy` | R | R | R, W, C, D |
| `wms.exception` | R, C | R, W, C | R, W, C, D |
| `wms.inventory.event` | R | R | R |
| `wms.audit.log` | — | R | R |

---

## 3. Record Rules — Filtro por Registro

Restringen **qué registros** puede ver/modificar cada grupo:

```xml
<!-- Operador solo ve Works de su bodega asignada -->
<record id="rule_wms_work_operator_warehouse" model="ir.rule">
    <field name="name">Operador: Works de su bodega</field>
    <field name="model_id" ref="model_wms_work"/>
    <field name="domain_force">[
        ('warehouse_id', 'in', user.wms_resource_ids.warehouse_id.ids)
    ]</field>
    <field name="groups" eval="[(4, ref('group_wms_operator'))]"/>
    <field name="perm_read" eval="True"/>
    <field name="perm_write" eval="True"/>
    <field name="perm_create" eval="False"/>
    <field name="perm_unlink" eval="False"/>
</record>

<!-- Supervisor ve Works de todas las bodegas que supervisa -->
<record id="rule_wms_work_supervisor_warehouse" model="ir.rule">
    <field name="name">Supervisor: Works de sus bodegas</field>
    <field name="model_id" ref="model_wms_work"/>
    <field name="domain_force">[
        '|',
        ('warehouse_id', 'in', user.wms_supervised_warehouse_ids.ids),
        ('warehouse_id', '=', False)
    ]</field>
    <field name="groups" eval="[(4, ref('group_wms_supervisor'))]"/>
</record>

<!-- Administrador ve todo (sin domain_force o domain vacío) -->
<record id="rule_wms_work_manager_all" model="ir.rule">
    <field name="name">Administrador: Todos los Works</field>
    <field name="model_id" ref="model_wms_work"/>
    <field name="domain_force">[(1, '=', 1)]</field>
    <field name="groups" eval="[(4, ref('group_wms_manager'))]"/>
</record>
```

### Multi-company

Si el módulo debe soportar multi-compañía:

```xml
<record id="rule_wms_work_company" model="ir.rule">
    <field name="name">WMS Work: regla multi-compañía</field>
    <field name="model_id" ref="model_wms_work"/>
    <field name="domain_force">[
        ('company_id', 'in', company_ids)
    ]</field>
</record>
```

---

## 4. Visibilidad en Vistas por Grupo

Controlar qué elementos ve cada grupo en la interfaz:

```xml
<!-- Botón solo visible para supervisores -->
<button name="action_force_complete" type="object"
        string="Forzar completado"
        groups="wms_work_engine.group_wms_supervisor"/>

<!-- Campo solo visible para administradores -->
<field name="claim_token" groups="wms_work_engine.group_wms_manager"/>

<!-- Página completa condicional -->
<page string="Configuración avanzada" name="advanced"
      groups="wms_work_engine.group_wms_manager">
    <!-- ... -->
</page>
```

---

## Orden de Archivos en `__manifest__.py`

```python
'data': [
    'security/security.xml',           # 1. Grupos primero
    'security/ir.model.access.csv',    # 2. ACLs que referencian los grupos
    'views/work_views.xml',            # 3. Vistas después (pueden usar groups=)
    'data/work_type_data.xml',         # 4. Datos al final
],
```

---

## Verificación

1. ¿Cada modelo tiene al menos una línea en `ir.model.access.csv`?
2. ¿Los grupos forman una jerarquía con `implied_ids`?
3. ¿Las record rules usan `domain_force` correctos?
4. ¿`security.xml` se carga ANTES de `ir.model.access.csv` en el manifest?
5. ¿Se probó el acceso con un usuario de cada grupo?
6. ¿No se usa `sudo()` innecesariamente?
