# Convenciones del Proyecto ERP-WMS-TMS — Odoo 19

Estas reglas aplican a **todo el código** del proyecto. Son obligatorias y no negociables.

---

## Versión y Licencia

- **Odoo**: 19.0 Community Edition
- **PostgreSQL**: 16
- **Licencia**: LGPL-3 (salvo que se indique lo contrario en `__manifest__.py`)
- **Python**: 3.12+ (la versión incluida en la imagen `odoo:19.0`)

---

## Directivas Invariables de Implementación y Review

Estas directivas aplican a TODO código Odoo/WMS nuevo o modificado. Tienen precedencia sobre ejemplos históricos o procedurales contenidos en las skills.

### INV-AGENT-001 — Idioma

- **Identificadores técnicos en inglés**:
  - Modelos (`_name`, `_inherit`)
  - Campos
  - Métodos
  - Variables
  - Clases
  - XML IDs
  - Claves de `Selection` (ej: `('RECEIVE', 'Recepción')`)
- **Todo contenido humano o visible debe estar 100% en español**:
  - `_description` del modelo
  - `string=` de campos
  - `help=` de campos
  - Labels de `Selection` (texto legible mostrado al usuario)
  - Mensajes de excepción (`UserError`, `ValidationError`, `AccessError`)
  - Comentarios de código Python
  - Docstrings de módulos, clases y métodos
  - Comentarios XML
  - Nombres y textos visibles en XML (nombres de `ir.rule`, botones, headers, páginas, actions, menus)

Antes de aprobar una tarea, revisar explícitamente esta regla.

### INV-AGENT-002 — Precisión de UOM en Odoo 19

Para cantidades de producto usar exclusivamente la precisión estándar de Odoo 19:

```python
digits="Product Unit"
```

Está estrictamente prohibido:

```python
digits="Product Unit of Measure"  # ❌ Inválido en Odoo 19
```

No inventar nombres de `decimal.precision`. Cuando exista duda, verificar el código fuente de Odoo 19 pinned.

### INV-AGENT-003 — No Defaults Mágicos

No agregar `default=` a ningún campo funcional o relacional por conveniencia, costumbre, ejemplo de un skill o inferencia del agente.

Un default sólo es válido cuando está respaldado explícitamente por:

1. El Task Contract vigente;
2. Un ADR aplicable;
3. Una semántica nativa de Odoo que estamos preservando;
4. Una decisión arquitectónica explícitamente documentada.

Si ninguna de estas fuentes exige un default:

```text
default = AUSENTE
```

Especialmente en campos `Many2one`, no inferir automáticamente `default=lambda self: self.env.company`, usuario actual, warehouse, location, partner, package u otra relación contextual.

Esta regla no obliga a eliminar ni alterar defaults nativos heredados de Odoo.

### INV-AGENT-004 — Exact Model Contract Tests

Cuando un Task Contract define un conjunto exacto de campos funcionales, el test debe verificar igualdad exacta de conjuntos:

```python
standard_odoo_fields = {"id", "display_name", "create_uid", "create_date", "write_uid", "write_date"}
actual_functional_fields = set(model._fields.keys()) - standard_odoo_fields
self.assertEqual(actual_functional_fields, expected_functional_fields)
```

Está estrictamente prohibido sustituir esta comprobación por:
- `self.assertIn()` iterativo por cada campo esperado;
- Verificación de que los esperados sean un subconjunto de los reales (subset testing);
- Whitelist + blacklist parcial;
- Comprobar sólo campos prohibidos conocidos.

Cuando el contrato declare un catálogo exacto de `Selection`, el test debe verificar igualdad exacta del catálogo:

```python
self.assertEqual(set(dict(model._fields["state"].selection).keys()), expected_keys)
```

### INV-AGENT-005 — No usar sudo como bypass de seguridad

En código runtime WMS:

- `sudo()` NO es el mecanismo normal de ejecución de comandos.
- No usar `sudo()` para compensar ACLs (`ir.model.access.csv`) insuficientes.
- No usar `sudo()` para saltar record rules (`ir.rule`) multi-company o multi-warehouse.
- No usar `SUPERUSER_ID` para business logic runtime.

`sudo()` sólo puede utilizarse de forma excepcional si:
1. El Task Contract lo autoriza explícitamente;
2. Existe una razón técnica justificada que no puede resolverse conservando el entorno del caller;
3. El boundary de datos con privilegios elevados está estrictamente acotado;
4. Existe test unitario específico que valida la elevación de privilegios controlada;
5. El review lo aprueba explícitamente.

### INV-AGENT-006 — Precedencia y Resolución de Conflictos

Un Task Contract define el scope ejecutable de una tarea, pero NO puede invalidar una regla global, un ADR aplicable ni el comportamiento real de Odoo 19 pinned.

**Matriz de Autoridad**:
- **Comportamiento nativo de Odoo**: Source oficial `odoo/odoo` en el Verified Commit registrado en `docs/03-plataforma/09-odoo-baseline-registry.md` (pin actual: `95f76213d3f732f1d198c740a908e8037c376114`). El Docker image digest identifica el runtime reproducible, pero NO sustituye el source commit para inspección de comportamiento ORM.
- **Arquitectura del proyecto**: Reglas globales (`.agents/rules/`) + ADRs vigentes (`docs/05-decisiones/01-adr.md`)
- **Realidad WMS implementada**: Estado real del código existente en `develop`
- **Scope y criterios de aceptación**: Task Contract vigente
- **Guía procedural de desarrollo**: Skills (`.agents/skills/`)

El Task Contract tiene precedencia sobre skills y ejemplos procedurales, pero debe ser rigurosamente compatible con las reglas globales, los ADRs y el comportamiento de Odoo 19.

Si durante la implementación o review se descubre una contradicción: **NO** adaptar silenciosamente el código. Detener la decisión, documentar la discrepancia y corregir el Task Contract o la arquitectura correspondiente.

### INV-AGENT-007 — Odoo Pinned antes de Asumir

Si una decisión depende de un API, campo, modelo, mecanismo de seguridad, UOM, packaging, reporte, vista o comportamiento ORM nativo:

Verificar primero el código fuente oficial de Odoo 19 fijado por el proyecto según el registro en `docs/03-plataforma/09-odoo-baseline-registry.md`.

Está prohibido implementar basándose en memoria o documentación de versiones anteriores (Odoo 16/17/18).

### INV-AGENT-008 — Ejemplos no son Contratos y Autoridad de APIs

Todo código mostrado en una skill o documento de arquitectura es ilustrativo/conceptual, salvo que se confirme en su autoridad correspondiente:

1. **APIs WMS / proyecto propias**:
   - Verificar su existencia real, firma y semántica en `develop`.
   - Si una API WMS no existe en `develop` → es arquitectura conceptual objetivo, NO disponible para uso inmediato.
2. **APIs nativas de Odoo**:
   - Verificar su existencia y comportamiento en el source oficial Odoo 19 pinned (`docs/03-plataforma/09-odoo-baseline-registry.md`).
   - Si una API, método o campo nativo de Odoo no existe en el source pinned → NO asumirlo ni invocarlo.
3. **APIs y librerías externas**:
   - Verificar la versión y dependencias fijadas en el proyecto.

Un ejemplo conceptual NO autoriza a:
- Crear modelos satélite no solicitados;
- Crear campos anticipados;
- Agregar defaults no exigidos;
- Agregar índices o constraints no especificados;
- Usar `sudo()`;
- Agregar SQL directo sin checklist;
- Introducir dependencias no aprobadas;
- Crear workers, endpoints o crons especulativos;
- Implementar componentes de fases futuras.

Antes de utilizar cualquier API, confirmar que el Task Contract actual incluye explícitamente su uso.

---

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
- Nunca usar `sudo()` sin justificación documentada y autorización contractual
- Los métodos de negocio deben tener docstring en español

## ⚠️ Breaking Changes de Odoo 19 (vs versiones anteriores)

Estas diferencias causan errores de instalación si se usa la sintaxis vieja:

| Concepto | ❌ Sintaxis vieja | ✅ Odoo 19 |
|---|---|---|
| Tipo base de producto físico | `type='product'` | `type='consu'` (Bienes) |
| Gestión de stock | Implícita en `type='product'` | `type='consu'` + `is_storable=True` |
| Precisión UoM Producto | `digits='Product Unit of Measure'` | `digits='Product Unit'` |
| Grupos de seguridad | `<field name="category_id" ref="..."/>` en `res.groups` | `<field name="privilege_id" ref="..."/>` — requiere `res.groups.privilege` |
| Grupos del usuario (Python) | `user.groups_id` | `user.group_ids` |
| SQL Constraints | `_sql_constraints = [(...)]` | `_name = models.Constraint('SQL', 'msg')` como atributo de clase |
| Índices compuestos | Sin API declarativa | `_name = models.Index('(col1, col2)')` como atributo de clase |
| HTTP route type | `type='json'` | `type='jsonrpc'` |
| HTTP auth por token | `auth='api_key'` | `auth='bearer'` |

### Tipos de producto y gestión de stock en Odoo 19

- `consu` — Bienes (productos físicos).
  > **Nota sobre inventario**: `type='consu'` clasifica el producto como Bien físico. Para que participe en inventario, `stock.quant` y la lógica de stock de Odoo 19 exigen además `is_storable=True`.
- `service` — Servicio
- `combo` — Combo

### Autenticación HTTP válida en Odoo 19

- `user` — Sesión de usuario Odoo (cookie)
- `bearer` — Token Bearer en header `Authorization`
- `public` — Sin autenticación, usuario público
- `none` — Sin autenticación ni usuario
