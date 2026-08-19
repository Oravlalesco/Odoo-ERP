---
name: odoo-testing
description: >-
  Usar este skill cuando el usuario pida crear tests unitarios, tests de integración,
  ejecutar tests de módulos Odoo, o configurar testing automatizado. Incluye el
  framework de testing de Odoo 19, verificación de invariantes WMS y performance
  budgets del proyecto (ADR-023).
---

# Testing de Módulos — Odoo 19

Guía para escribir y ejecutar tests en módulos Odoo 19.

> **ADR-023**: Cada motor WMS desde su primera versión emite métricas, respeta RBAC y tiene performance budget.

---

## Estructura de Tests

```text
custom_addons/wms_work_engine/
└── tests/
    ├── __init__.py
    ├── test_work.py            # Tests del modelo wms.work
    ├── test_work_line.py       # Tests del modelo wms.work.line
    ├── test_work_lifecycle.py  # Tests del ciclo de vida completo
    ├── test_concurrency.py     # Tests de concurrencia (FOR UPDATE SKIP LOCKED)
    └── common.py               # Clase base con datos compartidos
```

### `tests/__init__.py`

```python
from . import test_work
from . import test_work_line
from . import test_work_lifecycle
from . import test_concurrency
```

---

## Clases Base de Testing

| Clase | Uso | Transacción |
|---|---|---|
| `TransactionCase` | Tests unitarios estándar | Rollback al final de cada test |
| `HttpCase` | Tests que requieren cliente HTTP | Para probar controllers/API |
| `tagged` | Decorador para categorizar tests | Filtrar ejecución por tags |

---

## Template de Test Unitario

```python
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError


@tagged('post_install', '-at_install', 'wms', 'wms_work')
class TestWmsWork(TransactionCase):
    """Tests para el modelo wms.work."""

    @classmethod
    def setUpClass(cls):
        """Datos compartidos para todos los tests de esta clase."""
        super().setUpClass()

        # Crear bodega de prueba
        cls.warehouse = cls.env['stock.warehouse'].search([], limit=1)

        # Crear tipo de trabajo
        cls.work_type_pick = cls.env['wms.work_type'].create({
            'name': 'Pick',
            'code': 'PICK',
        })

        # Crear producto de prueba
        # Odoo 19: type='consu' (Bienes), 'service', 'combo'
        # NO usar type='product' — fue eliminado en Odoo 19
        cls.product = cls.env['product.product'].create({
            'name': 'Producto Test',
            'type': 'consu',
            'barcode': '7890001234567',
        })

        # Crear ubicaciones
        cls.location_src = cls.env['stock.location'].create({
            'name': 'Test Storage A01',
            'location_id': cls.warehouse.lot_stock_id.id,
            'usage': 'internal',
            'wms_location_role': 'STORAGE',
            'barcode': 'LOC-A01',
        })
        cls.location_dest = cls.env['stock.location'].create({
            'name': 'Test Staging',
            'location_id': cls.warehouse.lot_stock_id.id,
            'usage': 'internal',
            'wms_location_role': 'STAGING',
            'barcode': 'LOC-STG-01',
        })

    def test_create_work(self):
        """Verificar que se puede crear un Work en estado borrador."""
        work = self.env['wms.work'].create({
            'work_type_id': self.work_type_pick.id,
            'warehouse_id': self.warehouse.id,
            'priority': 80,
        })
        self.assertEqual(work.state, 'draft')
        self.assertTrue(work.reference)
        self.assertEqual(work.priority, 80)

    def test_validate_work(self):
        """Verificar transición de borrador a listo."""
        work = self.env['wms.work'].create({
            'work_type_id': self.work_type_pick.id,
            'warehouse_id': self.warehouse.id,
        })
        work.action_validate()
        self.assertEqual(work.state, 'ready')

    def test_cannot_cancel_completed_work(self):
        """Verificar que no se puede cancelar un trabajo completado."""
        work = self.env['wms.work'].create({
            'work_type_id': self.work_type_pick.id,
            'warehouse_id': self.warehouse.id,
        })
        work.state = 'completed'  # Simular completado
        with self.assertRaises(UserError):
            work.action_cancel()

    def test_priority_constraint(self):
        """Verificar que la prioridad debe estar entre 0 y 100."""
        with self.assertRaises(ValidationError):
            self.env['wms.work'].create({
                'work_type_id': self.work_type_pick.id,
                'warehouse_id': self.warehouse.id,
                'priority': 150,  # Inválido
            })

    def test_claim_token_unique(self):
        """Verificar CORE-006: claim_token es único."""
        work1 = self.env['wms.work'].create({
            'work_type_id': self.work_type_pick.id,
            'warehouse_id': self.warehouse.id,
            'claim_token': 'test-token-unique',
        })
        with self.assertRaises(Exception):  # IntegrityError wrapped
            self.env['wms.work'].create({
                'work_type_id': self.work_type_pick.id,
                'warehouse_id': self.warehouse.id,
                'claim_token': 'test-token-unique',  # Duplicado
            })
```

---

## Clase Base Compartida

```python
# tests/common.py
from odoo.tests import TransactionCase


class WmsTestCommon(TransactionCase):
    """Clase base con datos de prueba compartidos para tests WMS."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search([], limit=1)

        # Producto con perfil logístico
        cls.product_a = cls.env['product.product'].create({
            'name': 'SKU-A Test',
            'type': 'consu',    # Odoo 19: 'consu' reemplaza 'product'
            'tracking': 'lot',
        })

        # Ubicaciones estándar
        cls.loc_receiving = cls.env['stock.location'].create({
            'name': 'Receiving Test',
            'location_id': cls.warehouse.lot_stock_id.id,
            'usage': 'internal',
            'wms_location_role': 'RECEIVING',
        })
        cls.loc_storage = cls.env['stock.location'].create({
            'name': 'Storage A01 Test',
            'location_id': cls.warehouse.lot_stock_id.id,
            'usage': 'internal',
            'wms_location_role': 'STORAGE',
        })

    # =========================================================================
    # Helpers para crear stock en tests
    # =========================================================================
    #
    # ⚠️ NO usar stock.quant.create() como patrón estándar.
    # Crear quants directamente bypasea la lógica de Odoo (merge, validación,
    # moves) y produce tests que pasan pero no reflejan el comportamiento real.
    #
    # Usar el helper adecuado según el nivel del test:
    # =========================================================================

    def _put_stock_via_inventory(self, product, location, qty, lot=None):
        """
        Crear stock mediante ajuste de inventario (inventory adjustment).
        Usar para: tests funcionales y de comportamiento WMS.
        Es el mecanismo estándar de Odoo para establecer stock inicial.
        """
        quant = self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': product.id,
            'location_id': location.id,
            'inventory_quantity': qty,
            'lot_id': lot.id if lot else False,
        })
        quant.action_apply_inventory()
        return quant

    def _put_stock_via_move(self, product, location_src, location_dest,
                            qty, lot=None):
        """
        Crear stock mediante un stock.move confirmado y procesado.
        Usar para: tests de flujo completo (inbound, putaway, transfer).
        Replica el flujo real de Odoo desde una ubicación origen.
        """
        move = self.env['stock.move'].create({
            'name': f'Test move {product.name}',
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

    def _put_stock_quick(self, product, location, qty, lot=None):
        """
        Crear stock con _update_available_quantity() del ORM.
        Usar SOLO para: tests unitarios donde el foco NO es el flujo
        de inventario y se necesita velocidad.
        Justificar su uso con un comentario en el test.
        """
        self.env['stock.quant']._update_available_quantity(
            product, location, qty, lot_id=lot,
        )
```

### Cuándo Usar Cada Helper de Stock

| Helper | Nivel del test | Cuándo usar |
|---|---|---|
| `_put_stock_via_inventory()` | **Funcional** | Tests de comportamiento WMS: allocation, picking, replenishment. Es el patrón por defecto. |
| `_put_stock_via_move()` | **Flujo completo** | Tests que validan un flujo end-to-end (inbound → putaway → storage). |
| `_put_stock_quick()` | **Unitario** | Tests donde el stock es solo un prerequisito y el foco es otra lógica. Requiere justificación. |

> **⚠️ Nunca usar `stock.quant.create({'quantity': X})`** como patrón estándar.
> Bypasea `_merge_quants()`, validaciones y el flujo de moves. Produce tests
> que pasan manipulando quants directamente pero fallan en el flujo real de Odoo.

### Usar la clase base

```python
from .common import WmsTestCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'wms')
class TestWorkLifecycle(WmsTestCommon):

    def test_full_lifecycle(self):
        """Verificar ciclo completo: draft → ready → assigned → completed."""
        work = self._create_work(priority=90)
        # ... test del ciclo completo ...
```

---

## Verificar Invariantes del Proyecto

### CORE-001: Work ASSIGNED tiene exactamente un resource

```python
def test_core_001_assigned_has_resource(self):
    """CORE-001: Un Work ASSIGNED debe tener assigned_resource_id."""
    work = self._create_work()
    work.action_validate()
    # Simular claim
    work.write({
        'state': 'assigned',
        'assigned_resource_id': self.resource.id,
    })
    self.assertTrue(work.assigned_resource_id)
```

### CORE-003: Event se crea atómicamente con cambio de quant

```python
def test_core_003_event_atomic_with_quant(self):
    """CORE-003: wms.inventory.event se crea junto con cambio de quant."""
    # ... ejecutar operación que modifica quant ...
    events = self.env['wms.inventory.event'].search([
        ('product_id', '=', self.product_a.id),
    ])
    self.assertTrue(events, 'Debe existir un evento de inventario')
```

---

## Tests de Seguridad

```python
@tagged('post_install', '-at_install', 'wms', 'security')
class TestWmsWorkSecurity(WmsTestCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator_user = cls.env['res.users'].create({
            'name': 'Operador Test',
            'login': 'operator_test',
            'group_ids': [(6, 0, [
                cls.env.ref('wms_work_engine.group_wms_operator').id,
            ])],
        })

    def test_operator_cannot_delete_work(self):
        """Operador no debe poder eliminar Works."""
        work = self._create_work()
        with self.assertRaises(Exception):
            work.with_user(self.operator_user).unlink()

    def test_operator_cannot_create_work(self):
        """Operador no debe poder crear Works directamente."""
        with self.assertRaises(Exception):
            self.env['wms.work'].with_user(self.operator_user).create({
                'work_type_id': self.env.ref(
                    'wms_work_engine.work_type_pick').id,
                'warehouse_id': self.warehouse.id,
            })
```

---

## Ejecutar Tests

### Vía Docker Compose

```bash
# Ejecutar todos los tests de un módulo
docker compose exec odoo odoo --test-enable --stop-after-init \
    -i wms_work_engine -d odoo_test

# Ejecutar tests con tag específico
docker compose exec odoo odoo --test-enable --stop-after-init \
    --test-tags wms_work -i wms_work_engine -d odoo_test

# Ejecutar solo post_install tests (más rápido)
docker compose exec odoo odoo --test-enable --stop-after-init \
    --test-tags post_install -u wms_work_engine -d odoo_test
```

### Vía Kubernetes

```bash
ODOO_POD=$(kubectl get pods -n odoo -l app.kubernetes.io/name=odoo \
    -o jsonpath="{.items[0].metadata.name}")

kubectl exec -it $ODOO_POD -n odoo -- odoo --test-enable \
    --stop-after-init -i wms_work_engine -d odoo_test
```

### Tags Útiles

| Tag | Significado |
|---|---|
| `post_install` | Se ejecuta después de instalar el módulo |
| `-at_install` | NO se ejecuta durante la instalación |
| `wms` | Tag personalizado para todos los tests WMS |
| `wms_work` | Tag específico del dominio |
| `security` | Tests de seguridad |
| `concurrency` | Tests de concurrencia |

---

## Verificación

1. ¿Cada modelo nuevo tiene al menos un test?
2. ¿Los tests usan `setUpClass` para datos compartidos (más eficiente)?
3. ¿Se verifican las invariantes CORE relevantes?
4. ¿Se testea la seguridad (acceso por grupo)?
5. ¿Los tests son independientes entre sí?
6. ¿Se ejecutan sin errores? → `docker compose exec odoo odoo --test-enable --stop-after-init -i <modulo> -d odoo_test`
