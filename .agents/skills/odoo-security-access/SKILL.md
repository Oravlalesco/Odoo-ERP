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

> **⚠️ BREAKING CHANGE en Odoo 19**: El modelo de seguridad cambió de 2 a 3 niveles.
> `res.groups` ya NO usa `category_id`. Usa `privilege_id` que apunta a `res.groups.privilege`.
> Además, `res.users.groups_id` se renombró a `res.users.group_ids`.

---

## Arquitectura de Seguridad en Odoo 19

### Jerarquía de 3 Niveles

```text
ir.module.category         ← Categoría del módulo (agrupa privilegios en Ajustes)
    └── res.groups.privilege   ← Privilegio (agrupa grupos del mismo feature)
            └── res.groups         ← Grupo concreto (nivel de acceso)
```

| Nivel | Modelo | Propósito | Ejemplo |
|---|---|---|---|
| Categoría | `ir.module.category` | Agrupa privilegios en la UI de Ajustes | "WMS" |
| Privilegio | `res.groups.privilege` | Agrupa niveles de acceso de un feature | "Gestión de trabajo" |
| Grupo | `res.groups` | Nivel de acceso concreto con permisos | "Operador", "Supervisor" |

### Campos Clave de `res.groups` en Odoo 19

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | Char | Nombre del grupo |
| `privilege_id` | Many2one(`res.groups.privilege`) | **Reemplaza** `category_id` |
| `implied_ids` | Many2many | Grupos que se heredan automáticamente |
| `user_ids` | Many2many | Usuarios con este grupo (antes era `users`) |
| `comment` | Text | Descripción del grupo |

### Campos Clave de `res.groups.privilege`

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | Char | Nombre del privilegio |
| `category_id` | Many2one(`ir.module.category`) | Categoría del módulo |
| `sequence` | Integer | Orden en la UI |

### Constraint de Unicidad

```text
Odoo 19: UNIQUE(privilege_id, name) — NO UNIQUE(category_id, name)
```

---

## Componentes de Seguridad

| Componente | Archivo | Propósito |
|---|---|---|
| Categoría + Privilegios + Grupos | `security/security.xml` | Definen roles de usuario |
| ACLs (Access Control Lists) | `security/ir.model.access.csv` | Permisos CRUD por modelo y grupo |
| Record Rules | `security/security.xml` | Filtran registros visibles por usuario |

---

## 1. Grupos de Seguridad (Odoo 19)

### Estructura Completa

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- ================================================================== -->
    <!-- 1. CATEGORÍA DEL MÓDULO                                            -->
    <!-- ================================================================== -->
    <record id="module_category_wms" model="ir.module.category">
        <field name="name">WMS</field>
        <field name="description">Módulos del Warehouse Management System</field>
        <field name="sequence">50</field>
    </record>

    <!-- ================================================================== -->
    <!-- 2. PRIVILEGIOS (res.groups.privilege)                              -->
    <!--    Cada privilegio agrupa los niveles de acceso de un feature       -->
    <!-- ================================================================== -->

    <!-- Privilegio: Operaciones WMS (pick, put, move, count) -->
    <record id="privilege_wms_operations" model="res.groups.privilege">
        <field name="name">Operaciones WMS</field>
        <field name="category_id" ref="module_category_wms"/>
        <field name="sequence">10</field>
    </record>

    <!-- Privilegio: Configuración WMS (bodegas, zonas, colas, políticas) -->
    <record id="privilege_wms_configuration" model="res.groups.privilege">
        <field name="name">Configuración WMS</field>
        <field name="category_id" ref="module_category_wms"/>
        <field name="sequence">20</field>
    </record>

    <!-- ================================================================== -->
    <!-- 3. GRUPOS (res.groups)                                             -->
    <!--    Usan privilege_id, NO category_id                               -->
    <!-- ================================================================== -->

    <!-- Grupo: Operador WMS -->
    <record id="group_wms_operator" model="res.groups">
        <field name="name">Operador</field>
        <field name="privilege_id" ref="privilege_wms_operations"/>
        <field name="sequence">10</field>
        <field name="comment">
            Acceso a operaciones de piso: ejecutar trabajo dirigido,
            confirmar picks/puts, reportar excepciones.
        </field>
    </record>

    <!-- Grupo: Supervisor WMS (hereda de Operador) -->
    <record id="group_wms_supervisor" model="res.groups">
        <field name="name">Supervisor</field>
        <field name="privilege_id" ref="privilege_wms_operations"/>
        <field name="sequence">20</field>
        <field name="implied_ids" eval="[(4, ref('group_wms_operator'))]"/>
        <field name="comment">
            Todo lo del operador + gestión de excepciones, reconciliación
            de works, reasignación de trabajo, control tower.
        </field>
    </record>

    <!-- Grupo: Administrador WMS (hereda de Supervisor) -->
    <record id="group_wms_manager" model="res.groups">
        <field name="name">Administrador</field>
        <field name="privilege_id" ref="privilege_wms_configuration"/>
        <field name="sequence">30</field>
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
ir.module.category: WMS
├── res.groups.privilege: Operaciones WMS
│   ├── res.groups: Operador        (sequence=10)
│   └── res.groups: Supervisor      (sequence=20, implies Operador)
└── res.groups.privilege: Configuración WMS
    └── res.groups: Administrador   (sequence=30, implies Supervisor)
```

`implied_ids` con `(4, ref(...))` hace que al asignar Supervisor, automáticamente se asigne también Operador.

### Privilegios Adicionales por Dominio

Para módulos WMS grandes, cada dominio puede tener su propio privilegio:

```xml
<!-- Privilegio para gestión de inventario -->
<record id="privilege_wms_inventory" model="res.groups.privilege">
    <field name="name">Inventario WMS</field>
    <field name="category_id" ref="module_category_wms"/>
    <field name="sequence">30</field>
</record>

<!-- Privilegio para integraciones -->
<record id="privilege_wms_integration" model="res.groups.privilege">
    <field name="name">Integraciones WMS</field>
    <field name="category_id" ref="module_category_wms"/>
    <field name="sequence">40</field>
</record>
```

---

## 2. Seguridad en Dos Capas: CRUD + Comandos

> **La seguridad del WMS es command-oriented, no solo CRUD.**

La capa CRUD de Odoo (ACLs) es necesaria pero **insuficiente**. Un operador
con `perm_write=1` en `wms.work` podría ejecutar:

```python
# ❌ PELIGROSO: el operador podría hacer cualquier write
work.write({'state': 'completed', 'priority': 100, 'assigned_resource_id': 999})
```

La solución es **dos capas de seguridad**:

```text
Capa 1: ACLs (Odoo)              Capa 2: Comandos (WMS)
┌────────────────────┐            ┌─────────────────────────────────┐
│ Operador:          │            │ Operador solo puede ejecutar:   │
│   wms.work = R     │──────────▶│   ACCEPT_WORK                   │
│   wms.work.line = R│            │   CONFIRM_PICK                  │
│   (NO write)       │            │   CONFIRM_PUT                   │
│                    │            │   REPORT_SHORT                  │
│                    │            │   REPORT_EXCEPTION              │
│                    │            │   HEARTBEAT                     │
│                    │            │                                 │
│                    │            │ Cada comando valida:            │
│                    │            │   ✓ usuario/resource            │
│                    │            │   ✓ claim_token                 │
│                    │            │   ✓ assignment_version          │
│                    │            │   ✓ work state                  │
│                    │            │   ✓ warehouse/queue             │
└────────────────────┘            └─────────────────────────────────┘
```

### Capa 1: ACLs — `ir.model.access.csv`

El operador tiene **solo lectura** en modelos transaccionales. Las mutaciones
las ejecutan los métodos-comando con `sudo()` después de validar el contexto.

```csv
id,name,model_id/id,group_id/id,perm_read,perm_write,perm_create,perm_unlink
access_wms_work_operator,wms.work.operator,model_wms_work,wms_work_engine.group_wms_operator,1,0,0,0
access_wms_work_supervisor,wms.work.supervisor,model_wms_work,wms_work_engine.group_wms_supervisor,1,1,1,0
access_wms_work_manager,wms.work.manager,model_wms_work,wms_work_engine.group_wms_manager,1,1,1,1
access_wms_work_line_operator,wms.work.line.operator,model_wms_work_line,wms_work_engine.group_wms_operator,1,0,0,0
access_wms_work_line_supervisor,wms.work.line.supervisor,model_wms_work_line,wms_work_engine.group_wms_supervisor,1,1,1,0
access_wms_work_line_manager,wms.work.line.manager,model_wms_work_line,wms_work_engine.group_wms_manager,1,1,1,1
access_wms_work_type_all,wms.work_type.all,model_wms_work_type,base.group_user,1,0,0,0
access_wms_work_type_manager,wms.work_type.manager,model_wms_work_type,wms_work_engine.group_wms_manager,1,1,1,1
```

### Matriz de Permisos CRUD (Capa 1)

| Modelo | Operador | Supervisor | Administrador |
|---|---|---|---|
| `wms.work` | **R** | R, W, C | R, W, C, D |
| `wms.work.line` | **R** | R, W, C | R, W, C, D |
| `wms.work_type` | R | R | R, W, C, D |
| `wms.queue` | R | R, W | R, W, C, D |
| `wms.resource` | R (propio) | R, W | R, W, C, D |
| `wms.policy` | R | R | R, W, C, D |
| `wms.exception` | R, C | R, W, C | R, W, C, D |
| `wms.inventory.event` | R | R | R |
| `wms.audit.log` | — | R | R |

> **Nota**: El operador tiene `perm_write=0` en `wms.work` y `wms.work.line`.
> Toda mutación pasa por métodos-comando que usan `sudo()` internamente.

### Capa 2: Métodos-Comando (seguridad WMS)

Los métodos-comando son la interfaz real del operador. Cada uno:
1. Verifica que el usuario tiene el grupo correcto
2. Valida el contexto completo (resource, claim_token, state, etc.)
3. Solo entonces ejecuta la mutación con `sudo()`

```python
class WmsWork(models.Model):
    _name = 'wms.work'

    def cmd_accept_work(self, resource_id, claim_token):
        """
        Comando: operador acepta un trabajo asignado.

        Validaciones:
        - Usuario pertenece al grupo operador
        - Resource pertenece al usuario
        - Work está en estado 'assigned'
        - claim_token coincide
        - assignment_version no ha cambiado
        """
        self.ensure_one()

        # 1. Verificar grupo
        if not self.env.user.has_group(
                'wms_work_engine.group_wms_operator'):
            raise AccessError('No tiene permisos de operador WMS.')

        # 2. Verificar que el resource pertenece al usuario
        resource = self.env['wms.resource'].browse(resource_id)
        if resource.user_id != self.env.user:
            raise AccessError('El recurso no pertenece al usuario.')

        # 3. Verificar estado y claim_token
        if self.state != 'assigned':
            raise UserError('El trabajo no está en estado asignado.')
        if self.claim_token != claim_token:
            raise UserError('Claim token inválido — trabajo reasignado.')
        if self.assigned_resource_id != resource:
            raise UserError('El trabajo no está asignado a este recurso.')

        # 4. Ejecutar mutación con sudo() — DESPUÉS de validar todo
        self.sudo().write({
            'state': 'in_progress',
            'started_at': fields.Datetime.now(),
        })

    def cmd_confirm_pick(self, line_id, scanned_qty, claim_token):
        """
        Comando: operador confirma un pick.

        Validaciones: claim_token, state, resource, line pertenece al work.
        """
        self.ensure_one()
        self._validate_operator_context(claim_token)

        line = self.line_ids.filtered(lambda l: l.id == line_id)
        if not line:
            raise UserError('Línea no pertenece a este trabajo.')
        if line.line_state != 'pending':
            raise UserError('Línea ya fue procesada.')

        # Ejecutar pick vía mecanismo ORM (ver skill wms-transaction-patterns)
        line.sudo()._execute_pick(scanned_qty)

    def cmd_report_exception(self, line_id, exception_type, notes,
                             claim_token):
        """
        Comando: operador reporta una excepción (short pick, daño, etc.).
        """
        self.ensure_one()
        self._validate_operator_context(claim_token)

        self.sudo().write({'state': 'exception'})
        self.env['wms.exception'].sudo().create({
            'work_id': self.id,
            'work_line_id': line_id,
            'exception_type': exception_type,
            'notes': notes,
            'reported_by': self.env.user.id,
        })

    def _validate_operator_context(self, claim_token):
        """
        Validación común para todos los comandos de operador.
        Verifica: grupo, resource, claim_token, estado, lease.
        """
        if not self.env.user.has_group(
                'wms_work_engine.group_wms_operator'):
            raise AccessError('No tiene permisos de operador WMS.')
        if self.state not in ('assigned', 'in_progress'):
            raise UserError('Estado del trabajo no permite esta operación.')
        if self.claim_token != claim_token:
            raise UserError('Claim token inválido.')
        if (self.lease_expires_at
                and self.lease_expires_at < fields.Datetime.now()):
            raise UserError('Lease expirado — solicitar nuevo trabajo.')
```

### Catálogo de Comandos por Rol

| Comando | Operador | Supervisor | Administrador |
|---|---|---|---|
| `cmd_accept_work` | ✅ | ✅ | ✅ |
| `cmd_confirm_pick` | ✅ | ✅ | ✅ |
| `cmd_confirm_put` | ✅ | ✅ | ✅ |
| `cmd_report_short` | ✅ | ✅ | ✅ |
| `cmd_report_exception` | ✅ | ✅ | ✅ |
| `cmd_heartbeat` | ✅ | ✅ | ✅ |
| `cmd_force_complete` | ❌ | ✅ | ✅ |
| `cmd_reassign_work` | ❌ | ✅ | ✅ |
| `cmd_cancel_work` | ❌ | ✅ | ✅ |
| `cmd_reconcile_work` | ❌ | ✅ | ✅ |
| Configuración directa (CRUD) | ❌ | Parcial | ✅ |

### Reglas para Métodos-Comando

1. **Prefijo `cmd_`**: Todos los comandos del operador empiezan con `cmd_`
2. **Validar antes de mutar**: Toda validación ocurre ANTES de `sudo().write()`
3. **`sudo()` justificado**: El operador no tiene `perm_write`, el comando usa `sudo()` solo después de validar contexto completo
4. **Un comando = una acción**: No combinar varias operaciones en un comando
5. **Documentar validaciones**: Cada `cmd_` lista en su docstring qué valida

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

## 5. Referencia a Grupos en Python (Odoo 19)

```python
# Verificar si el usuario tiene un grupo
if self.env.user.has_group('wms_work_engine.group_wms_supervisor'):
    # lógica de supervisor

# Acceder a los grupos del usuario (Odoo 19: group_ids, NO groups_id)
user_groups = self.env.user.group_ids
```

> **⚠️ Odoo 19**: El campo se llama `group_ids` (no `groups_id` como en versiones anteriores).

---

## Orden de Archivos en `__manifest__.py`

```python
'data': [
    'security/security.xml',           # 1. Categoría + Privilegios + Grupos
    'security/ir.model.access.csv',    # 2. ACLs que referencian los grupos
    'views/work_views.xml',            # 3. Vistas después (pueden usar groups=)
    'data/work_type_data.xml',         # 4. Datos al final
],
```

---

## Errores Comunes en Odoo 19

| ❌ Error (sintaxis vieja) | ✅ Correcto (Odoo 19) |
|---|---|
| `<field name="category_id" ref="..."/>` en `res.groups` | `<field name="privilege_id" ref="..."/>` |
| Crear grupo sin privilegio | Crear `res.groups.privilege` primero, luego referenciar |
| `user.groups_id` en Python | `user.group_ids` |
| `UNIQUE(category_id, name)` | `UNIQUE(privilege_id, name)` — automático |

---

## Verificación

1. ¿Cada grupo referencia un `privilege_id` (no `category_id`)?
2. ¿Los privilegios (`res.groups.privilege`) se definen ANTES que los grupos?
3. ¿Cada modelo tiene al menos una línea en `ir.model.access.csv`?
4. ¿Los grupos forman una jerarquía con `implied_ids`?
5. ¿Las record rules usan `domain_force` correctos?
6. ¿`security.xml` se carga ANTES de `ir.model.access.csv` en el manifest?
7. ¿Se usa `user.group_ids` (no `user.groups_id`) en Python?
8. ¿No se usa `sudo()` innecesariamente?
