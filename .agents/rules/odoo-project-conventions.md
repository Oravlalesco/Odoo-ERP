# Convenciones del Proyecto ERP-WMS-TMS — Odoo 19

Estas reglas aplican a **todo el código** del proyecto. Son obligatorias y no negociables.

---

## Versión y Licencia

- **Odoo**: 19.0 Community Edition
- **PostgreSQL**: 16
- **Licencia**: LGPL-3 (salvo que se indique lo contrario en `__manifest__.py`)
- **Python**: 3.12+ (la versión incluida en la imagen `odoo:19.0`)

## Idioma

- **Código** (nombres de modelos, campos, métodos, variables, clases): **inglés**
- **Documentación, comments en código, strings de usuario** (`_description`, labels de campos, help texts): **español**
- **Commits**: español

## Estructura de Módulos

- Todos los módulos personalizados van en `custom_addons/`
- Prefijos obligatorios:
  - `wms_` — Módulos del WMS (Warehouse Management System)
  - `tms_` — Módulos del TMS (Transportation Management System)
  - `erp_` — Extensiones generales al ERP
- Nombre técnico del módulo en `snake_case` (ej: `wms_work_engine`, `tms_route_planning`)
- Nombre de modelos con punto como separador (ej: `wms.work`, `wms.work.line`)

## Architecture Decision Records (ADRs)

Los ADRs documentados en `docs/05-decisiones/01-adr.md` son **obligatorios**. Destacan:

- **ADR-001**: `stock.quant` es la fuente de verdad del inventario — NO crear una segunda base de inventario
- **ADR-002**: `stock.picking` ≠ `wms.work` — nunca usar pickings para dirigir trabajo RF
- **ADR-011**: NO agregar campos a la identidad lógica de `stock.quant` sin análisis completo de `_merge_quants()`
- **ADR-012**: Inventory Status (Quality Hold, Quarantine, Damage) se implementa con ubicaciones especializadas, no con campos en `stock.quant`
- **ADR-013**: `stock.package` es la base de Handling Units — extender, no reemplazar
- **ADR-018**: Rule Engine usa DSL tipada sin `safe_eval` — nunca ejecutar código arbitrario
- **ADR-026**: `stock.location.usage` conserva la semántica Odoo — usar `wms_location_role` para roles WMS

## Entorno de Desarrollo

- **Desarrollo local**: Docker Compose (`docker compose up -d --build`)
- **Bases de datos**: `odoo_dev` (desarrollo), `odoo_test` (tests) — NUNCA `odoo_production`
- **Actualizar módulo**: `docker compose exec odoo odoo -u <module_name> -d odoo_dev --stop-after-init`
- **Ejecutar tests**: `docker compose exec odoo odoo --test-enable --stop-after-init -i <module_name> -d odoo_test`
- **Producción**: Solo vía CI/CD → migration gate → immutable image → rolling deployment
- **⛔ PROHIBIDO**: Acceso directo del agente o desarrollador a BD de producción (`kubectl exec`, `docker compose exec` contra producción)

## Convenciones de Código Odoo

- Los modelos heredan de `models.Model` (datos persistentes) o `models.TransientModel` (wizards)
- Usar `_inherit` para extender modelos de Odoo, no copiar código
- Los campos `Many2one` siempre deben tener `ondelete` definido
- Usar `models.Constraint()` para constraints SQL (no `_sql_constraints` — legacy eliminado en Odoo 19)
- Nunca usar `sudo()` sin justificación documentada
- Los métodos de negocio deben tener docstring en español

## ⚠️ Breaking Changes de Odoo 19 (vs versiones anteriores)

Estas diferencias causan errores de instalación si se usa la sintaxis vieja:

| Concepto | ❌ Sintaxis vieja | ✅ Odoo 19 |
|---|---|---|
| Tipo de producto almacenable | `type='product'` | `type='consu'` (Bienes) |
| Grupos de seguridad | `<field name="category_id" ref="..."/>` en `res.groups` | `<field name="privilege_id" ref="..."/>` — requiere `res.groups.privilege` |
| Grupos del usuario (Python) | `user.groups_id` | `user.group_ids` |
| SQL Constraints | `_sql_constraints = [(...)]` | `_name = models.Constraint('SQL', 'msg')` como atributo de clase |
| Índices compuestos | Sin API declarativa | `_name = models.Index('(col1, col2)')` como atributo de clase |
| HTTP route type | `type='json'` | `type='jsonrpc'` |
| HTTP auth por token | `auth='api_key'` | `auth='bearer'` |

### Tipos de producto válidos en Odoo 19

- `consu` — Bienes (productos físicos/almacenables)
- `service` — Servicio
- `combo` — Combo

### Autenticación HTTP válida en Odoo 19

- `user` — Sesión de usuario Odoo (cookie)
- `bearer` — Token Bearer en header `Authorization`
- `public` — Sin autenticación, usuario público
- `none` — Sin autenticación ni usuario

