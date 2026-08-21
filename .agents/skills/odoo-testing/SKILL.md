---
name: odoo-testing
description: >-
  Usar este skill cuando el usuario pida crear tests unitarios, tests de integración,
  ejecutar tests de módulos Odoo, o configurar testing automatizado. Incluye el
  framework de testing de Odoo 19, verificación de invariantes WMS y performance
  budgets del proyecto (ADR-023).
---

# Testing de Módulos — Odoo 19

Guía para escribir y ejecutar tests en módulos Odoo 19, aplicando verificación contractual estricta, seguridad RBAC e invariantes del proyecto.

> **ADR-023**: Cada motor WMS desde su primera versión emite métricas, respeta RBAC y tiene performance budget.

---

## 🛑 Directivas de Rigor de Testing

1. **Precedencia de Contrato**: Todo test valida el Task Contract vigente respetando las directivas de `.agents/rules/odoo-project-conventions.md`.
2. **Invariantes Inquebrantables**: Ningún test puede usar mocks para simular que un quant mutó cuando la mutación real por ORM falló o no existe.

---

## Tests de Contrato Exacto

En el proyecto distinguimos dos niveles de verificación:

| Nivel de Test | Cuándo aplica | Regla de Verificación |
|---|---|---|
| **Presence Test** | El contrato dice "debe existir / debe incluir" | `self.assertTrue(...)` / `self.assertIn(...)` |
| **Exact Contract Test** | El contrato declara "exactamente N campos / N estados / N archivos / N tests" | `self.assertEqual(actual, expected)` con igualdad estricta de conjuntos/listas |

> **⚠️ Regla**: Cuando el Task Contract declare exactitud:
> - Exactamente N campos funcionales
> - Exactamente N valores de Selection
> - Exactamente N permisos ACL
> - Exactamente N archivos en el diff
> - Exactamente N tests ejecutados
>
> Sustituir por subset testing (`assertIn` iterativo o `expected <= actual`) es **FAIL**.

### 1. Verificación de Campos Funcionales Exactos

```python
def test_model_fields_exact_contract(self):
    """Verifica que el modelo contenga exactamente los campos funcionales congelados."""
    model = self.env['wms.inventory.event']

    # Campos técnicos estándar del ORM de Odoo (Model base)
    standard_odoo_fields = {
        'id',
        'display_name',
        'create_uid',
        'create_date',
        'write_uid',
        'write_date',
    }

    expected_functional_fields = {
        'company_id',
        'occurred_at',
        'event_type',
        'product_id',
        'lot_id',
        'package_id',
        'owner_id',
        'source_location_id',
        'dest_location_id',
        'quantity',
        'operator_id',
        'warehouse_id',
        'correlation_id',
    }

    actual_functional_fields = set(model._fields.keys()) - standard_odoo_fields

    # ✅ CORRECTO: Igualdad exacta de conjuntos
    self.assertEqual(
        actual_functional_fields,
        expected_functional_fields,
        'El modelo debe contener exactamente los campos funcionales especificados en el contrato.',
    )
```

### 2. Verificación de Catálogos `Selection` Exactos

```python
def test_selection_catalog_exact_contract(self):
    """Verifica el catálogo exacto de opciones de Selection."""
    model = self.env['wms.inventory.event']
    selection_dict = dict(model._fields['event_type'].selection)

    expected_types = {
        'RECEIVE',
        'MOVE',
        'RELEASE',
        'PUTAWAY',
        'PICK',
        'PACK',
        'UNPACK',
    }

    # ✅ CORRECTO: Igualdad exacta de claves
    self.assertEqual(set(selection_dict.keys()), expected_types)

    # Validar además que los labels estén en español (INV-AGENT-001)
    self.assertEqual(selection_dict['RECEIVE'], 'Recepción')
    self.assertEqual(selection_dict['PICK'], 'Recolección')
```

### 3. Verificación de Metadatos de Campo

```python
def test_field_metadata_contract(self):
    """Verifica precisión decimal real y ausencia de defaults mágicos."""
    model = self.env['wms.inventory.event']

    # INV-AGENT-002: Product Unit exacto
    f_qty = model._fields['quantity']
    self.assertEqual(getattr(f_qty, '_digits', None), 'Product Unit')

    # INV-AGENT-003: default AUSENTE salvo exigencia contractual
    self.assertIsNone(model._fields['company_id'].default)
```

---

## Verificación de Permisos RBAC con `with_user()`

Los tests de seguridad deben verificar la autorización real simulando usuarios de diferentes perfiles con `.with_user()`:

```python
def test_operator_cannot_delete_record(self):
    """Verificar el rechazo de borrado definido contractualmente para el operador."""
    record_as_operator = self.test_record.with_user(self.user_operator)

    with self.assertRaises(AccessError):
        record_as_operator.unlink()
```

> **Regla**: Los permisos CRUD son contractuales por modelo (un modelo inmutable o append-only niega `unlink` a todos los roles). Validar operaciones permitidas para roles jerárquicos superiores únicamente cuando el Task Contract del modelo conceda expresamente ese permiso.
> Probar la autorización siempre con la identidad del caller real (`with_user()`), sin usar `sudo()`.

---

## Conteo Exacto de Tests en Gates

Un gate de ejecución (Clean Install Gate o Upgrade Gate) sólo es válido si el log de Odoo confirma el conteo exacto de tests planificado:

```text
expected_tests = N
executed_tests = N
failed = 0
errors = 0
```

> **⚠️ Alerta**: Reportar un gate como "PASS" con 0 tests ejecutados, con tests omitidos o con un conteo total distinto al especificado en el Task Contract es **FAIL**.

---

## Clases Base de Testing

| Clase | Uso | Transacción |
|---|---|---|
| `TransactionCase` | Tests unitarios estándar | Rollback automático al final de cada test |
| `HttpCase` | Tests que requieren cliente HTTP / API | Para probar controllers y endpoints |
| `tagged` | Decorador para categorizar tests | Filtrar ejecución por tags |

---

## Helpers para Crear Stock en Tests

> **⚠️ Nunca usar `stock.quant.create({'quantity': X})`** como patrón estándar.
> Bypasea `_merge_quants()`, validaciones y el flujo de moves. Produce tests que pasan manipulando quants directamente pero fallan en el flujo real de Odoo.

```python
class WmsTestCommon(TransactionCase):
    """Clase base con helpers de stock para tests WMS."""

    def _put_stock_via_inventory(self, product, location, qty, lot=None):
        """Crear stock mediante inventory adjustment (patrón por defecto para tests funcionales)."""
        quant = self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': product.id,
            'location_id': location.id,
            'inventory_quantity': qty,
            'lot_id': lot.id if lot else False,
        })
        quant.action_apply_inventory()
        return quant

    def _put_stock_via_move(self, product, location_src, location_dest, qty, lot=None):
        """Crear stock mediante stock.move confirmado y finalizado (flujo completo)."""
        move = self.env['stock.move'].create({
            'name': f'Movimiento de prueba {product.name}',
            'product_id': product.id,
            'product_uom_qty': qty,
            'product_uom': product.uom_id.id,
            'location_id': location_src.id,
            'location_dest_id': location_dest.id,
        })
        move._action_confirm()
        move._action_assign()
        for ml in move.move_line_ids:
            ml.quantity = ml.quantity_product_uom
            if lot:
                ml.lot_id = lot
            ml.picked = True
        move._action_done()
        return move

    def _put_stock_quick(self, product, location, qty, lot=None, package=None, owner=None):
        """Helper rápido para crear stock usando el método nativo _update_available_quantity().

        ⚠️ REGLA DE USO:
        - Usar exclusivamente como fixture rápido para tests donde la presencia de stock
          es un prerequisito y NO aquello que se está validando.
        - NO usar si el test pretende validar movimientos, reservas, inventario o eventos.
        """
        self.env['stock.quant']._update_available_quantity(
            product, location, qty, lot_id=lot, package_id=package, owner_id=owner
        )
```

---

## Ejecución con Docker Compose

```bash
# 0. Reset de odoo_test (DESECHABLE — siempre --entrypoint "" e init --force)
docker compose run --rm --entrypoint "" odoo odoo \
  db --db_host db --db_port 5432 -r odoo -w $DB_PASS \
  init --force odoo_test

# 1. Install
docker compose run --rm odoo odoo \
  --stop-after-init -i <module> -d odoo_test

# 2. Upgrade (idempotencia)
docker compose run --rm odoo odoo \
  --stop-after-init -u <module> -d odoo_test

# 3. Tests
docker compose run --rm odoo odoo \
  --test-enable --stop-after-init -d odoo_test \
  --test-tags /<module>
```

---

## Checklist de Verificación de Tests

1. ¿El número total de tests ejecutados coincide **exactamente** con el conteo esperado (`N failed = 0, errors = 0`)?
2. ¿Los tests de modelo verifican **igualdad exacta de conjuntos** de campos funcionales excluyendo campos técnicos ORM?
3. ¿Los catálogos `Selection` se comprueban con igualdad exacta de claves y labels en español?
4. ¿Se prueban los permisos RBAC con `with_user()` verificando rechazos `AccessError` sin inferir permisos no contratados?
5. ¿Se evita el uso de `sudo()` en tests salvo cuando se prueba explícitamente una elevación autorizada?
6. ¿Los tests son independientes entre sí y no dejan estado residual?
