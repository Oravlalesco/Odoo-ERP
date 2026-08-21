---
name: odoo-security-access
description: >-
  Usar este skill cuando el usuario pida configurar permisos de acceso, grupos de
  seguridad, ACLs (ir.model.access.csv), record rules (ir.rule), o implementar
  control de acceso basado en roles (RBAC) en módulos Odoo. También aplica cuando
  se pregunte sobre seguridad del WMS (ADR-023).
---

# Seguridad y Permisos — Odoo 19

Guía para configurar grupos, privilegios, ACLs, record rules y control de acceso en módulos Odoo 19.

> **ADR-023**: Security es un cross-cutting concern — cada motor WMS desde su primera versión debe respetar RBAC.

> **⚠️ BREAKING CHANGE en Odoo 19**: El modelo de seguridad cambió de 2 a 3 niveles.
> `res.groups` ya NO usa `category_id`. Usa `privilege_id` que apunta a `res.groups.privilege`.
> Además, `res.users.groups_id` se renombró a `res.users.group_ids`.

---

## 🛑 Directivas de Seguridad del Proyecto

1. **No usar `sudo()` como bypass**: El código WMS opera conservando el entorno del usuario autenticado (`self.env`).
2. **Defensa en profundidad Server-Side**:
   - `readonly="1"` o `invisible="1"` en XML **NO** es seguridad de backend.
   - La visibilidad en UI **NO** sustituye ACLs ni Record Rules.
   - `groups="..."` en reportes XML **NO** garantiza autorización server-side; el parser/controller (`_get_report_values`) debe validar permisos explícitamente en Python.
3. **Elevación de privilegios excepcional**: `sudo()` solo se permite si el Task Contract lo autoriza explícitamente, el boundary de datos está delimitado y existen tests específicos.

---

## Modelo Mental: ACL vs Record Rule vs Autorización de Comandos

En el WMS distinguimos tres niveles complementarios de autorización:

```text
1. ACL (ir.model.access.csv)
   → ¿Tiene este rol permiso CRUD genérico sobre la tabla?
   → Condición NECESARIA pero NO suficiente para ejecutar operaciones operacionales.

2. Record Rules (ir.rule)
   → ¿Puede este usuario acceder a este conjunto de registros (multi-compañía, almacén asignado)?
   → Aislamiento de datos a nivel de consulta SQL (domain_force).

3. Command Authorization (Python en métodos de negocio)
   → ¿Tiene este usuario autorización para ejecutar ESTE comando en ESTE estado y contexto operacional?
   → Validación de invariantes de negocio, pertenencia a grupos y roles operacionales en self.env.
```

> **Regla de Oro**: Tener permiso de escritura (`perm_write=1` en ACL) no autoriza por sí solo a ejecutar una transición de estado si el usuario no cumple el rol operacional requerido.

---

## Arquitectura de Seguridad en Odoo 19

### Jerarquía de 3 Niveles

```text
ir.module.category         ← Categoría del módulo (agrupa privilegios en Ajustes)
    └── res.groups.privilege   ← Privilegio (agrupa grupos del mismo feature)
            └── res.groups         ← Grupo concreto (nivel de acceso con permisos)
```

| Nivel | Modelo | Propósito | Ejemplo |
|---|---|---|---|
| Categoría | `ir.module.category` | Agrupa privilegios en la UI de Ajustes | "WMS" |
| Privilegio | `res.groups.privilege` | Agrupa niveles de acceso de un feature | "Operaciones WMS" |
| Grupo | `res.groups` | Nivel de acceso concreto con permisos | "Operador", "Supervisor" |

---

## 1. Grupos de Seguridad (Odoo 19)

### Estructura en XML (`security/security.xml`)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- ================================================================== -->
    <!-- 1. CATEGORÍA DEL MÓDULO                                            -->
    <!-- ================================================================== -->
    <record id="module_category_wms" model="ir.module.category">
        <field name="name">WMS</field>
        <field name="description">Módulos del Sistema de Gestión de Almacenes (WMS)</field>
        <field name="sequence">50</field>
    </record>

    <!-- ================================================================== -->
    <!-- 2. PRIVILEGIOS (res.groups.privilege)                              -->
    <!-- ================================================================== -->
    <record id="privilege_wms_operations" model="res.groups.privilege">
        <field name="name">Operaciones WMS</field>
        <field name="category_id" ref="module_category_wms"/>
        <field name="sequence">10</field>
    </record>

    <record id="privilege_wms_configuration" model="res.groups.privilege">
        <field name="name">Configuración WMS</field>
        <field name="category_id" ref="module_category_wms"/>
        <field name="sequence">20</field>
    </record>

    <!-- ================================================================== -->
    <!-- 3. GRUPOS (res.groups) — Usan privilege_id, NO category_id          -->
    <!-- ================================================================== -->
    <record id="group_wms_operator" model="res.groups">
        <field name="name">Operador</field>
        <field name="privilege_id" ref="privilege_wms_operations"/>
        <field name="sequence">10</field>
        <field name="comment">Acceso a operaciones de piso: ejecución de trabajo dirigido y confirmaciones.</field>
    </record>

    <record id="group_wms_supervisor" model="res.groups">
        <field name="name">Supervisor</field>
        <field name="privilege_id" ref="privilege_wms_operations"/>
        <field name="sequence">20</field>
        <field name="implied_ids" eval="[(4, ref('group_wms_operator'))]"/>
        <field name="comment">Gestión de excepciones, reasignación de trabajo y reconciliación.</field>
    </record>

    <record id="group_wms_manager" model="res.groups">
        <field name="name">Administrador</field>
        <field name="privilege_id" ref="privilege_wms_configuration"/>
        <field name="sequence">30</field>
        <field name="implied_ids" eval="[(4, ref('group_wms_supervisor'))]"/>
        <field name="comment">Configuración completa de almacenes, colas, políticas y recursos.</field>
    </record>
</odoo>
```

---

## 2. Permisos CRUD — `ir.model.access.csv`

Los permisos ACL modelan los derechos de acceso directos del usuario autenticado:

```csv
id,name,model_id/id,group_id/id,perm_read,perm_write,perm_create,perm_unlink
access_wms_work_operator,wms.work.operator,model_wms_work,wms_core.group_wms_operator,1,1,0,0
access_wms_work_supervisor,wms.work.supervisor,model_wms_work,wms_core.group_wms_supervisor,1,1,1,0
access_wms_work_manager,wms.work.manager,model_wms_work,wms_core.group_wms_manager,1,1,1,1
access_wms_inventory_event_operator,wms.inventory.event.operator,model_wms_inventory_event,wms_core.group_wms_operator,1,0,1,0
access_wms_inventory_event_supervisor,wms.inventory.event.supervisor,model_wms_inventory_event,wms_core.group_wms_supervisor,1,0,1,0
access_wms_inventory_event_manager,wms.inventory.event.manager,model_wms_inventory_event,wms_core.group_wms_manager,1,0,1,0
access_wms_inventory_event_admin,wms.inventory.event.admin,model_wms_inventory_event,base.group_system,1,0,1,0
```

---

## 3. Métodos-Comando y Autorización Server-Side

La lógica de negocio valida permisos antes de mutar el estado:

```python
class WmsWork(models.Model):
    _name = 'wms.work'
    _description = 'Trabajo WMS'

    def action_claim_work(self, resource_id, claim_token):
        """Asignar trabajo a un recurso validando credenciales y estado."""
        self.ensure_one()

        # 1. Validación de autorización
        self.check_access('write')
        if not self.env.user.has_group('wms_core.group_wms_operator'):
            raise AccessError('No tiene permisos de operador WMS para reclamar trabajo.')

        # 2. Validación de estado y ownership
        if self.state != 'ready':
            raise UserError('El trabajo no está disponible para asignación.')

        # 3. Mutación en el entorno del llamador
        self.write({
            'state': 'assigned',
            'assigned_resource_id': resource_id,
            'claim_token': claim_token,
            'assigned_at': fields.Datetime.now(),
        })
```

---

## 4. Record Rules — Filtros de Registro

Las reglas de registro aíslan datos multi-compañía y multi-almacén:

```xml
<!-- Regla Multi-compañía -->
<record id="rule_wms_work_company" model="ir.rule">
    <field name="name">Trabajo WMS: multi-compañía</field>
    <field name="model_id" ref="model_wms_work"/>
    <field name="domain_force">[('company_id', 'in', company_ids)]</field>
</record>

<!-- Regla de Ámbito Operacional -->
<record id="rule_wms_work_operator_warehouse" model="ir.rule">
    <field name="name">Operador: Trabajos de su almacén asignado</field>
    <field name="model_id" ref="model_wms_work"/>
    <field name="domain_force">[
        ('warehouse_id', 'in', user.wms_resource_ids.warehouse_id.ids)
    ]</field>
    <field name="groups" eval="[(4, ref('wms_core.group_wms_operator'))]"/>
</record>
```

---

## Checklist de Seguridad

1. ¿Cada grupo nuevo usa `privilege_id` (Odoo 19) y no `category_id`?
2. ¿Los privilegios se declaran ANTES de los grupos en el archivo XML?
3. ¿Todos los nombres de reglas, descripciones y comentarios XML están 100% en español (INV-AGENT-001)?
4. ¿Se evita el uso de `sudo()` en el código runtime, preservando `self.env` (INV-AGENT-005)?
5. ¿Cada reporte y endpoint cuenta con validación de autorización server-side y no depende solo de la visibilidad en UI?
6. ¿Las reglas multi-compañía cubren todos los modelos del módulo?
7. ¿Se usa `user.group_ids` en Python en lugar del legado `user.groups_id`?
8. ¿Se respeta la jerarquía: ACL necesaria → Record Rule aísla → Command Authorization valida lógica de negocio?
