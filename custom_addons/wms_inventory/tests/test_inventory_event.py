import uuid
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestInventoryEvent(TransactionCase):
    """Pruebas unitarias para el Journal Operacional de Eventos de Inventario WMS (INV-008).

    Valida:
    - TEST-INV-056: Modelo registrado, exactamente 13 campos funcionales, 7 event types exactos, sin campos prohibidos ni defaults espurios.
    - TEST-INV-057: API privada _append_events() singleton: server-owned timestamp, operator_id y correlation_id.
    - TEST-INV-058: API privada _append_events() batch (3 eventos): 1 sola creación multi, mismo correlation_id/timestamp/operator, orden preservado.
    - TEST-INV-059: Append-only: create directo, write y unlink fallan con UserError para cualquier rol (Manager / Admin incluidos).
    - TEST-INV-060: Validaciones: quantity <= 0, lot/product mismatch y chequeos multi-compañía.
    - TEST-INV-061: RBAC y aislamiento multi-compañía: WMS roles y System Admin pasan, Plain Internal falla, aislamiento entre compañías.
    - TEST-INV-062: Límite de efectos secundarios: _append_events crea solo journal rows, no modifica quants, moves, lines, packages ni history.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Event = cls.env["wms.inventory.event"]
        cls.Product = cls.env["product.product"]
        cls.Location = cls.env["stock.location"]
        cls.Package = cls.env["stock.package"]
        cls.Lot = cls.env["stock.lot"]
        cls.Partner = cls.env["res.partner"]
        cls.Warehouse = cls.env["stock.warehouse"]
        cls.Quant = cls.env["stock.quant"]
        cls.StockMove = cls.env["stock.move"]
        cls.StockMoveLine = cls.env["stock.move.line"]
        cls.PackageHistory = cls.env["stock.package.history"]
        cls.Company = cls.env.company
        cls.Users = cls.env["res.users"]

        # Compañía secundaria
        cls.company_secondary = cls.env["res.company"].create({
            "name": "Secondary Co Event Test",
        })

        # Ubicaciones
        cls.loc_src = cls.Location.create({
            "name": "Loc Source Event Test",
            "usage": "internal",
            "company_id": cls.Company.id,
        })
        cls.loc_dst = cls.Location.create({
            "name": "Loc Dest Event Test",
            "usage": "internal",
            "company_id": cls.Company.id,
        })
        cls.loc_sec = cls.Location.create({
            "name": "Loc Sec Event Test",
            "usage": "internal",
            "company_id": cls.company_secondary.id,
        })

        # Almacén
        cls.warehouse = cls.Warehouse.search([("company_id", "=", cls.Company.id)], limit=1)
        if not cls.warehouse:
            cls.warehouse = cls.Warehouse.create({
                "name": "WH Event Test",
                "code": "WHET",
                "company_id": cls.Company.id,
            })

        # Productos
        cls.product_a = cls.Product.create({
            "name": "Event Test Product A",
            "is_storable": True,
        })
        cls.product_b = cls.Product.create({
            "name": "Event Test Product B",
            "is_storable": True,
        })

        # Lotes
        cls.lot_a = cls.Lot.create({
            "name": "LOT-EVT-001",
            "product_id": cls.product_a.id,
            "company_id": cls.Company.id,
        })
        cls.lot_b = cls.Lot.create({
            "name": "LOT-EVT-002",
            "product_id": cls.product_b.id,
            "company_id": cls.Company.id,
        })

        # Paquete
        cls.package = cls.Package.create({
            "name": "PKG-EVT-001",
        })

        # Partner (Owner)
        cls.owner = cls.Partner.create({
            "name": "Owner Partner Event Test",
        })

        # Grupos de seguridad
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_supervisor = cls.env.ref("wms_core.group_wms_supervisor")
        cls.group_manager = cls.env.ref("wms_core.group_wms_manager")
        cls.group_system = cls.env.ref("base.group_system")

        # Usuarios de prueba
        cls.user_operator = cls._create_user("u_evt_op", [cls.group_operator.id])
        cls.user_supervisor = cls._create_user("u_evt_sup", [cls.group_supervisor.id])
        cls.user_manager = cls._create_user("u_evt_mgr", [cls.group_manager.id])
        cls.user_admin = cls._create_user("u_evt_admin", [cls.group_system.id])
        cls.user_plain_internal = cls._create_user("u_evt_plain", [])
        cls.user_sec_operator = cls.Users.create({
            "name": "User Sec Op Event Test",
            "login": "u_sec_evt_op",
            "email": "sec_evt_op@test.com",
            "company_id": cls.company_secondary.id,
            "company_ids": [(6, 0, [cls.company_secondary.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_operator.id])],
        })

    @classmethod
    def _create_user(cls, login, group_ids):
        all_groups = [cls.group_internal.id] + group_ids
        return cls.Users.create({
            "name": f"User {login}",
            "login": login,
            "email": f"{login}@test.com",
            "company_id": cls.Company.id,
            "company_ids": [(6, 0, [cls.Company.id])],
            "group_ids": [(6, 0, all_groups)],
        })

    # -------------------------------------------------------------------------
    # TEST-INV-056: Modelo registrado, 13 campos funcionales exactos, 7 event types
    # -------------------------------------------------------------------------

    def test_inv_056_model_registered_and_contract_boundaries(self):
        """INV-056: wms.inventory.event tiene exactamente 13 campos funcionales, 7 event types y metadatos exactos."""
        self.assertIn("wms.inventory.event", self.env)
        event_model = self.env["wms.inventory.event"]

        # Campos técnicos estándar de Odoo
        standard_odoo_fields = {
            "id",
            "display_name",
            "create_uid",
            "create_date",
            "write_uid",
            "write_date",
        }

        # Exactamente 13 campos funcionales congelados
        expected_functional_fields = {
            "company_id",
            "occurred_at",
            "event_type",
            "product_id",
            "lot_id",
            "package_id",
            "owner_id",
            "source_location_id",
            "dest_location_id",
            "quantity",
            "operator_id",
            "warehouse_id",
            "correlation_id",
        }

        actual_all_fields = set(event_model._fields.keys())
        actual_functional_fields = actual_all_fields - standard_odoo_fields

        self.assertEqual(
            actual_functional_fields,
            expected_functional_fields,
            "El modelo wms.inventory.event debe contener exactamente los 13 campos funcionales congelados.",
        )

        # Catálogo exacto de 7 event_type
        event_type_selection = dict(event_model._fields["event_type"].selection)
        expected_types = {"RECEIVE", "MOVE", "RELEASE", "PUTAWAY", "PICK", "PACK", "UNPACK"}
        self.assertEqual(set(event_type_selection.keys()), expected_types)

        # Validación de metadata estricta: precisión decimal y ausencia de default en company_id
        f_qty = event_model._fields["quantity"]
        self.assertEqual(getattr(f_qty, "_digits", None), "Product Unit", "El campo quantity debe usar precisión 'Product Unit'")
        self.assertIsNone(event_model._fields["company_id"].default, "company_id debe ser explícito y no tener valor default")

    # -------------------------------------------------------------------------
    # TEST-INV-057: API privada _append_events() singleton
    # -------------------------------------------------------------------------

    def test_inv_057_append_events_singleton(self):
        """INV-057: _append_events() crea evento con timestamp, operator y correlation_id server-owned."""
        now_before = fields.Datetime.now()

        # Intento de pasar valores manipulados para campos server-owned
        vals = {
            "company_id": self.Company.id,
            "event_type": "RECEIVE",
            "product_id": self.product_a.id,
            "lot_id": self.lot_a.id,
            "package_id": self.package.id,
            "owner_id": self.owner.id,
            "source_location_id": self.loc_src.id,
            "dest_location_id": self.loc_dst.id,
            "quantity": 15.5,
            "warehouse_id": self.warehouse.id,
            # Valores a sobrescribir:
            "occurred_at": "2020-01-01 00:00:00",
            "operator_id": self.user_admin.id,
            "correlation_id": "fake-client-correlation-id",
        }

        # Ejecutar como user_operator
        events = self.Event.with_user(self.user_operator)._append_events([vals])
        self.assertEqual(len(events), 1)
        event = events[0]

        now_after = fields.Datetime.now()

        # Campos de negocio preservados
        self.assertEqual(event.company_id, self.Company)
        self.assertEqual(event.event_type, "RECEIVE")
        self.assertEqual(event.product_id, self.product_a)
        self.assertEqual(event.lot_id, self.lot_a)
        self.assertEqual(event.package_id, self.package)
        self.assertEqual(event.owner_id, self.owner)
        self.assertEqual(event.source_location_id, self.loc_src)
        self.assertEqual(event.dest_location_id, self.loc_dst)
        self.assertEqual(event.quantity, 15.5)
        self.assertEqual(event.warehouse_id, self.warehouse)

        # Campos server-owned sobrescritos y validados
        self.assertEqual(event.operator_id, self.user_operator, "El operador debe ser el usuario en sesión")
        self.assertNotEqual(event.operator_id, self.user_admin)
        self.assertTrue(now_before <= event.occurred_at <= now_after, "Timestamp debe ser asignado por el servidor")
        self.assertNotEqual(str(event.occurred_at), "2020-01-01 00:00:00")
        self.assertNotEqual(event.correlation_id, "fake-client-correlation-id")
        self.assertTrue(bool(event.correlation_id))

        # Pasar correlation_id explícito válido a través del parámetro
        custom_corr = str(uuid.uuid4())
        events_custom = self.Event.with_user(self.user_operator)._append_events([vals], correlation_id=custom_corr)
        self.assertEqual(events_custom[0].correlation_id, custom_corr)

    # -------------------------------------------------------------------------
    # TEST-INV-058: API privada _append_events() batch de 3 eventos
    # -------------------------------------------------------------------------

    def test_inv_058_append_events_batch_multi_create_atomic(self):
        """INV-058: _append_events() con 3 eventos realiza 1 sola creación multi, comparte correlation/time y preserva orden."""
        vals_list = [
            {
                "company_id": self.Company.id,
                "event_type": "PICK",
                "product_id": self.product_a.id,
                "source_location_id": self.loc_src.id,
                "dest_location_id": self.loc_dst.id,
                "quantity": 10.0,
            },
            {
                "company_id": self.Company.id,
                "event_type": "PACK",
                "product_id": self.product_a.id,
                "package_id": self.package.id,
                "source_location_id": self.loc_dst.id,
                "quantity": 10.0,
            },
            {
                "company_id": self.Company.id,
                "event_type": "MOVE",
                "product_id": self.product_b.id,
                "source_location_id": self.loc_src.id,
                "dest_location_id": self.loc_dst.id,
                "quantity": 5.0,
            },
        ]

        count_before = self.Event.search_count([])

        # Instrumentar _create sobre el modelo para verificar exactamente 1 llamada multi con batch de 3
        with patch.object(type(self.Event), "_create", wraps=self.Event._create) as spy_create:
            events = self.Event.with_user(self.user_operator)._append_events(vals_list)

            self.assertEqual(spy_create.call_count, 1, "Debe ejecutarse exactamente 1 creación multi-record en el ORM")
            self.assertEqual(len(spy_create.call_args[0][0]), 3, "El batch enviado a _create debe tener tamaño 3")

        # Verificaciones del batch
        self.assertEqual(len(events), 3)
        self.assertEqual(self.Event.search_count([]), count_before + 3)

        # Orden lógico preservado
        self.assertEqual(events[0].event_type, "PICK")
        self.assertEqual(events[0].product_id, self.product_a)
        self.assertEqual(events[1].event_type, "PACK")
        self.assertEqual(events[1].package_id, self.package)
        self.assertEqual(events[2].event_type, "MOVE")
        self.assertEqual(events[2].product_id, self.product_b)

        # Metadata común a todo el batch
        corr_0 = events[0].correlation_id
        time_0 = events[0].occurred_at
        op_0 = events[0].operator_id

        for e in events:
            self.assertEqual(e.correlation_id, corr_0, "Todos los eventos del batch deben compartir el correlation_id")
            self.assertEqual(e.occurred_at, time_0, "Todos los eventos del batch deben compartir el occurred_at")
            self.assertEqual(e.operator_id, op_0, "Todos los eventos del batch deben compartir el operator_id")
            self.assertEqual(e.operator_id, self.user_operator)

    # -------------------------------------------------------------------------
    # TEST-INV-059: Inmutabilidad (create directo, write, unlink fallan)
    # -------------------------------------------------------------------------

    def test_inv_059_append_only_immutability_guards(self):
        """INV-059: create() directo, write() y unlink() fallan con UserError incluso para Manager y Admin."""
        # 1. Crear evento válido vía _append_events
        event = self.Event.with_user(self.user_operator)._append_events([{
            "company_id": self.Company.id,
            "event_type": "MOVE",
            "product_id": self.product_a.id,
            "quantity": 10.0,
        }])[0]

        # 2. create() directo prohibido
        with self.assertRaises(UserError):
            self.Event.with_user(self.user_operator).create({
                "company_id": self.Company.id,
                "event_type": "MOVE",
                "product_id": self.product_a.id,
                "quantity": 10.0,
            })

        with self.assertRaises(UserError):
            self.Event.with_user(self.user_manager).create({
                "company_id": self.Company.id,
                "event_type": "MOVE",
                "product_id": self.product_a.id,
                "quantity": 10.0,
            })

        with self.assertRaises(UserError):
            self.Event.with_user(self.user_admin).create({
                "company_id": self.Company.id,
                "event_type": "MOVE",
                "product_id": self.product_a.id,
                "quantity": 10.0,
            })

        # 3. write() prohibido
        with self.assertRaises(UserError):
            event.with_user(self.user_operator).write({"quantity": 20.0})

        with self.assertRaises(UserError):
            event.with_user(self.user_manager).write({"quantity": 20.0})

        with self.assertRaises(UserError):
            event.with_user(self.user_admin).write({"quantity": 20.0})

        # 4. unlink() prohibido
        with self.assertRaises(UserError):
            event.with_user(self.user_operator).unlink()

        with self.assertRaises(UserError):
            event.with_user(self.user_manager).unlink()

        with self.assertRaises(UserError):
            event.with_user(self.user_admin).unlink()

    # -------------------------------------------------------------------------
    # TEST-INV-060: Validaciones de cantidad, lote/producto y multi-compañía
    # -------------------------------------------------------------------------

    def test_inv_060_validations_and_constraints(self):
        """INV-060: quantity <= 0, lot/product mismatch y relaciones cross-company son rechazadas."""
        # 1. quantity <= 0
        with self.assertRaises(ValidationError):
            self.Event.with_user(self.user_operator)._append_events([{
                "company_id": self.Company.id,
                "event_type": "MOVE",
                "product_id": self.product_a.id,
                "quantity": 0.0,
            }])

        with self.assertRaises(ValidationError):
            self.Event.with_user(self.user_operator)._append_events([{
                "company_id": self.Company.id,
                "event_type": "MOVE",
                "product_id": self.product_a.id,
                "quantity": -5.0,
            }])

        # 2. Lot / Product mismatch
        with self.assertRaises(ValidationError):
            self.Event.with_user(self.user_operator)._append_events([{
                "company_id": self.Company.id,
                "event_type": "MOVE",
                "product_id": self.product_a.id,
                "lot_id": self.lot_b.id,  # Lote del producto B asignado a producto A
                "quantity": 1.0,
            }])

        # 3. Multi-compañía: ubicación de compañía secundaria en evento de compañía principal
        with self.assertRaises(UserError):  # _check_company_auto lanza UserError por mismatch de compañía
            self.Event.with_user(self.user_operator)._append_events([{
                "company_id": self.Company.id,
                "event_type": "MOVE",
                "product_id": self.product_a.id,
                "source_location_id": self.loc_sec.id,  # Ubicación de compañía secundaria
                "quantity": 1.0,
            }])

    # -------------------------------------------------------------------------
    # TEST-INV-061: RBAC y aislamiento multi-compañía
    # -------------------------------------------------------------------------

    def test_inv_061_rbac_and_multi_company_isolation(self):
        """INV-061: WMS roles y System Admin pueden usar _append_events y leer; Plain Internal falla; aislamiento entre compañías."""
        # 1. WMS Operator PASS
        evt_op = self.Event.with_user(self.user_operator)._append_events([{
            "company_id": self.Company.id,
            "event_type": "RECEIVE",
            "product_id": self.product_a.id,
            "quantity": 5.0,
        }])
        self.assertEqual(len(evt_op), 1)
        self.assertTrue(self.Event.with_user(self.user_operator).search([("id", "=", evt_op.id)]))

        # 2. WMS Supervisor PASS
        evt_sup = self.Event.with_user(self.user_supervisor)._append_events([{
            "company_id": self.Company.id,
            "event_type": "PUTAWAY",
            "product_id": self.product_a.id,
            "quantity": 5.0,
        }])
        self.assertEqual(len(evt_sup), 1)
        self.assertTrue(self.Event.with_user(self.user_supervisor).search([("id", "=", evt_sup.id)]))

        # 3. WMS Manager PASS
        evt_mgr = self.Event.with_user(self.user_manager)._append_events([{
            "company_id": self.Company.id,
            "event_type": "PICK",
            "product_id": self.product_a.id,
            "quantity": 5.0,
        }])
        self.assertEqual(len(evt_mgr), 1)
        self.assertTrue(self.Event.with_user(self.user_manager).search([("id", "=", evt_mgr.id)]))

        # 4. System Admin PASS
        evt_admin = self.Event.with_user(self.user_admin)._append_events([{
            "company_id": self.Company.id,
            "event_type": "PACK",
            "product_id": self.product_a.id,
            "quantity": 5.0,
        }])
        self.assertEqual(len(evt_admin), 1)
        self.assertTrue(self.Event.with_user(self.user_admin).search([("id", "=", evt_admin.id)]))

        # 5. Plain Internal (sin rol WMS) recibe AccessError al crear y leer
        with self.assertRaises(AccessError):
            self.Event.with_user(self.user_plain_internal)._append_events([{
                "company_id": self.Company.id,
                "event_type": "MOVE",
                "product_id": self.product_a.id,
                "quantity": 5.0,
            }])

        with self.assertRaises(AccessError):
            self.Event.with_user(self.user_plain_internal).search([("id", "=", evt_op.id)])

        # 6. Aislamiento multi-compañía: operador de compañía secundaria no ve eventos de compañía principal
        events_seen_by_sec = self.Event.with_user(self.user_sec_operator).search([("id", "in", [evt_op.id, evt_sup.id, evt_mgr.id, evt_admin.id])])
        self.assertEqual(len(events_seen_by_sec), 0, "Operador de compañía secundaria no debe ver eventos de compañía principal")

    # -------------------------------------------------------------------------
    # TEST-INV-062: Límite de efectos secundarios (side-effect boundary)
    # -------------------------------------------------------------------------

    def test_inv_062_side_effect_boundary(self):
        """INV-062: _append_events() crea exclusivamente journal rows; quants, moves, packages e history intactos."""
        quant = self.Quant.create({
            "product_id": self.product_a.id,
            "location_id": self.loc_src.id,
            "package_id": self.package.id,
            "quantity": 100.0,
            "reserved_quantity": 20.0,
            "company_id": self.Company.id,
        })

        # Snapshot antes
        orig_quant_id = quant.id
        orig_quant_qty = quant.quantity
        orig_quant_res = quant.reserved_quantity
        orig_quant_pkg = quant.package_id

        move_count_before = self.StockMove.search_count([])
        move_line_count_before = self.StockMoveLine.search_count([])
        package_count_before = self.Package.search_count([])
        history_count_before = self.PackageHistory.search_count([])
        event_count_before = self.Event.search_count([])

        # Ejecutar _append_events
        events = self.Event.with_user(self.user_operator)._append_events([
            {
                "company_id": self.Company.id,
                "event_type": "MOVE",
                "product_id": self.product_a.id,
                "package_id": self.package.id,
                "source_location_id": self.loc_src.id,
                "dest_location_id": self.loc_dst.id,
                "quantity": 10.0,
            },
            {
                "company_id": self.Company.id,
                "event_type": "UNPACK",
                "product_id": self.product_a.id,
                "package_id": self.package.id,
                "quantity": 10.0,
            },
        ])

        # Verificar incremento exacto en el journal
        self.assertEqual(len(events), 2)
        self.assertEqual(self.Event.search_count([]), event_count_before + 2)

        # Invariantes de inventario estándar intactos
        quant.invalidate_recordset()
        self.assertEqual(quant.id, orig_quant_id)
        self.assertEqual(quant.quantity, orig_quant_qty)
        self.assertEqual(quant.reserved_quantity, orig_quant_res)
        self.assertEqual(quant.package_id, orig_quant_pkg)

        self.assertEqual(self.StockMove.search_count([]), move_count_before)
        self.assertEqual(self.StockMoveLine.search_count([]), move_line_count_before)
        self.assertEqual(self.Package.search_count([]), package_count_before)
        self.assertEqual(self.PackageHistory.search_count([]), history_count_before)
