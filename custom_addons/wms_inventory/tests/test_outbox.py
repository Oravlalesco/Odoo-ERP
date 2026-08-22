import uuid
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestOutbox(TransactionCase):
    """Pruebas unitarias para la Bandeja de Salida Transaccional WMS (INV-010A).

    Valida:
    - TEST-INV-063: Modelo registrado, 12 campos funcionales exactos, sin campos prohibidos, status exactos y constraints.
    - TEST-INV-064: API privada _enqueue_messages() singleton: server-owned metadata, UUID4 message_id, correlation generado vs explícito.
    - TEST-INV-065: API privada _enqueue_messages() batch (3 mensajes): 1 sola creación multi, mismo timestamp/correlation, 3 message IDs únicos, orden preservado.
    - TEST-INV-066: Inmutabilidad pública: create, write y unlink fallan con UserError; estado inicial PENDING/0/sin delivery.
    - TEST-INV-067: Validaciones e integridad: messages inválido, correlation_id estricto, event_name, schema_version, payload, claves no permitidas, unicidad DB de message_id.
    - TEST-INV-068: RBAC estricto (Operator/Supervisor C=1, R=0; Manager/Admin C=1, R=1, W=1; Plain Internal C=0, R=0) y aislamiento multi-compañía.
    - TEST-INV-069: Límite de efectos secundarios (side-effect boundary): _enqueue_messages crea exclusivamente outbox rows; quants, moves, blocks, events e history intactos.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Outbox = cls.env["wms.outbox"]
        cls.Event = cls.env["wms.inventory.event"]
        cls.Block = cls.env["wms.inventory.block"]
        cls.Product = cls.env["product.product"]
        cls.Location = cls.env["stock.location"]
        cls.Package = cls.env["stock.package"]
        cls.Lot = cls.env["stock.lot"]
        cls.Warehouse = cls.env["stock.warehouse"]
        cls.Quant = cls.env["stock.quant"]
        cls.StockMove = cls.env["stock.move"]
        cls.StockMoveLine = cls.env["stock.move.line"]
        cls.PackageHistory = cls.env["stock.package.history"]
        cls.Company = cls.env.company
        cls.Users = cls.env["res.users"]

        # Compañía secundaria
        cls.company_secondary = cls.env["res.company"].create({
            "name": "Secondary Co Outbox Test",
        })

        # Ubicaciones de prueba
        cls.loc_src = cls.Location.create({
            "name": "Loc Source Outbox Test",
            "usage": "internal",
            "company_id": cls.Company.id,
        })
        cls.loc_dst = cls.Location.create({
            "name": "Loc Dest Outbox Test",
            "usage": "internal",
            "company_id": cls.Company.id,
        })

        # Productos
        cls.product = cls.Product.create({
            "name": "Outbox Test Product",
            "is_storable": True,
        })

        # Paquete
        cls.package = cls.Package.create({
            "name": "PKG-OUTBOX-001",
        })

        # Grupos de seguridad
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_supervisor = cls.env.ref("wms_core.group_wms_supervisor")
        cls.group_manager = cls.env.ref("wms_core.group_wms_manager")
        cls.group_system = cls.env.ref("base.group_system")

        # Usuarios de prueba
        cls.user_operator = cls._create_user("u_outbox_op", [cls.group_operator.id])
        cls.user_supervisor = cls._create_user("u_outbox_sup", [cls.group_supervisor.id])
        cls.user_manager = cls._create_user("u_outbox_mgr", [cls.group_manager.id])
        cls.user_admin = cls._create_user("u_outbox_admin", [cls.group_system.id])
        cls.user_plain_internal = cls._create_user("u_outbox_plain", [])
        cls.user_sec_manager = cls.Users.create({
            "name": "User Sec Mgr Outbox Test",
            "login": "u_sec_outbox_mgr",
            "email": "sec_outbox_mgr@test.com",
            "company_id": cls.company_secondary.id,
            "company_ids": [(6, 0, [cls.company_secondary.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_manager.id])],
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
    # TEST-INV-063: Modelo registrado, 12 campos funcionales exactos, constraints
    # -------------------------------------------------------------------------

    def test_inv_063_model_registered_and_contract_boundaries(self):
        """INV-063: wms.outbox tiene exactamente 12 campos funcionales, 3 status exactos y metadatos exactos."""
        self.assertIn("wms.outbox", self.env)
        outbox_model = self.env["wms.outbox"]

        # Campos técnicos estándar de Odoo
        standard_odoo_fields = {
            "id",
            "display_name",
            "create_uid",
            "create_date",
            "write_uid",
            "write_date",
        }

        # Exactamente 12 campos funcionales congelados
        expected_functional_fields = {
            "company_id",
            "message_id",
            "created_at",
            "event_name",
            "schema_version",
            "payload",
            "correlation_id",
            "status",
            "attempt_count",
            "next_attempt_at",
            "published_at",
            "last_error",
        }

        actual_all_fields = set(outbox_model._fields.keys())
        actual_functional_fields = actual_all_fields - standard_odoo_fields

        self.assertEqual(
            actual_functional_fields,
            expected_functional_fields,
            "El modelo wms.outbox debe contener exactamente los 12 campos funcionales congelados.",
        )

        # Campos prohibidos explícitos
        forbidden_fields = {
            "inventory_event_id",
            "quant_id",
            "stock_move_id",
            "package_id",
            "work_id",
            "source_model",
            "source_id",
            "routing_key",
            "exchange",
            "destination",
            "headers",
            "priority",
            "active",
            "idempotency_key",
        }
        for ff in forbidden_fields:
            self.assertNotIn(ff, actual_all_fields, f"El campo {ff} no debe existir en wms.outbox")

        # Catálogo exacto de 3 status
        status_selection = dict(outbox_model._fields["status"].selection)
        expected_statuses = {"PENDING", "SENT", "DEAD"}
        self.assertEqual(set(status_selection.keys()), expected_statuses)

        # Metadatos del modelo
        self.assertIsNone(outbox_model._fields["company_id"].default, "company_id debe ser explícito y sin default")
        self.assertEqual(outbox_model._order, "created_at asc, id asc", "El orden debe ser created_at asc, id asc")
        self.assertTrue(outbox_model._check_company_auto, "_check_company_auto debe ser True")

    # -------------------------------------------------------------------------
    # TEST-INV-064: API privada _enqueue_messages() singleton
    # -------------------------------------------------------------------------

    def test_inv_064_enqueue_messages_singleton(self):
        """INV-064: _enqueue_messages() singleton asigna server-owned metadata, UUID4 message_id y correlation correcto."""
        now_before = fields.Datetime.now()

        # Intento de falsificar campos server-owned
        vals = {
            "company_id": self.Company.id,
            "event_name": "inventory.item_received",
            "schema_version": 1,
            "payload": {"product_id": self.product.id, "quantity": 100.0},
            # Campos a sobrescribir:
            "message_id": "fake-message-uuid",
            "created_at": "2020-01-01 00:00:00",
            "correlation_id": "fake-correlation-id",
            "status": "SENT",
            "attempt_count": 99,
            "next_attempt_at": "2020-01-01 00:00:00",
            "published_at": "2020-01-01 00:00:00",
            "last_error": "fake error",
        }

        # Ejecutar como user_manager para verificar lectura
        messages = self.Outbox.with_user(self.user_manager)._enqueue_messages([vals])
        self.assertEqual(len(messages), 1)
        msg = messages[0]

        now_after = fields.Datetime.now()

        # Validar campos de negocio
        self.assertEqual(msg.company_id, self.Company)
        self.assertEqual(msg.event_name, "inventory.item_received")
        self.assertEqual(msg.schema_version, 1)
        self.assertEqual(msg.payload, {"product_id": self.product.id, "quantity": 100.0})

        # Validar campos server-owned sobrescritos
        self.assertNotEqual(msg.message_id, "fake-message-uuid")
        self.assertTrue(bool(msg.message_id))
        uuid.UUID(msg.message_id)  # Valida que sea UUID válido

        self.assertTrue(now_before <= msg.created_at <= now_after)
        self.assertNotEqual(str(msg.created_at), "2020-01-01 00:00:00")

        self.assertNotEqual(msg.correlation_id, "fake-correlation-id")
        self.assertTrue(bool(msg.correlation_id))
        uuid.UUID(msg.correlation_id)  # Valida que sea UUID válido

        self.assertEqual(msg.status, "PENDING")
        self.assertEqual(msg.attempt_count, 0)
        self.assertFalse(msg.next_attempt_at)
        self.assertFalse(msg.published_at)
        self.assertFalse(msg.last_error)

        # Probar correlation_id explícito válido
        explicit_corr = "CORR-BATCH-999"
        msg_explicit = self.Outbox.with_user(self.user_manager)._enqueue_messages([vals], correlation_id=explicit_corr)
        self.assertEqual(msg_explicit[0].correlation_id, explicit_corr)

        # Probar correlation_id con espacios alrededor que deben limpiarse (strip)
        msg_strip = self.Outbox.with_user(self.user_manager)._enqueue_messages([vals], correlation_id="  CORR-STRIP-123  ")
        self.assertEqual(msg_strip[0].correlation_id, "CORR-STRIP-123")

    # -------------------------------------------------------------------------
    # TEST-INV-065: API privada _enqueue_messages() batch de 3 mensajes
    # -------------------------------------------------------------------------

    def test_inv_065_enqueue_messages_batch_multi_create_atomic(self):
        """INV-065: _enqueue_messages() con 3 mensajes ejecuta 1 creación multi en ORM, comparte correlation/time y preserva orden."""
        vals_list = [
            {
                "company_id": self.Company.id,
                "event_name": "inventory.item_received",
                "schema_version": 1,
                "payload": {"sku": "A", "qty": 10},
            },
            {
                "company_id": self.Company.id,
                "event_name": "inventory.item_moved",
                "schema_version": 1,
                "payload": {"sku": "A", "from": "LOC1", "to": "LOC2"},
            },
            {
                "company_id": self.Company.id,
                "event_name": "inventory.item_packed",
                "schema_version": 2,
                "payload": {"sku": "A", "package": "PKG1"},
            },
        ]

        count_before = self.Outbox.search_count([])

        # Instrumentar _create sobre el modelo para verificar exactamente 1 llamada multi con batch de 3
        with patch.object(type(self.Outbox), "_create", wraps=self.Outbox._create) as spy_create:
            messages = self.Outbox.with_user(self.user_manager)._enqueue_messages(vals_list)

            self.assertEqual(spy_create.call_count, 1, "Debe ejecutarse exactamente 1 creación multi-record en el ORM")
            self.assertEqual(len(spy_create.call_args[0][0]), 3, "El batch enviado a _create debe tener tamaño 3")

        # Verificaciones del batch
        self.assertEqual(len(messages), 3)
        self.assertEqual(self.Outbox.search_count([]), count_before + 3)

        # Orden lógico preservado
        self.assertEqual(messages[0].event_name, "inventory.item_received")
        self.assertEqual(messages[1].event_name, "inventory.item_moved")
        self.assertEqual(messages[2].event_name, "inventory.item_packed")

        # Metadata común a todo el batch
        time_0 = messages[0].created_at
        corr_0 = messages[0].correlation_id

        # IDs de mensaje únicos
        message_ids = set()
        for m in messages:
            self.assertEqual(m.created_at, time_0, "Todos los mensajes del batch deben compartir created_at")
            self.assertEqual(m.correlation_id, corr_0, "Todos los mensajes del batch deben compartir correlation_id")
            self.assertEqual(m.status, "PENDING")
            self.assertEqual(m.attempt_count, 0)
            self.assertNotIn(m.message_id, message_ids, "Cada mensaje del batch debe tener un message_id único")
            message_ids.add(m.message_id)

        self.assertEqual(len(message_ids), 3)

    # -------------------------------------------------------------------------
    # TEST-INV-066: Inmutabilidad pública y estado inicial de entrega
    # -------------------------------------------------------------------------

    def test_inv_066_immutability_and_initial_delivery_state(self):
        """INV-066: create() directo, write() y unlink() fallan con UserError para cualquier rol; estado inicial PENDING/0."""
        # 1. Encolar mensaje vía API interna
        msg = self.Outbox.with_user(self.user_manager)._enqueue_messages([{
            "company_id": self.Company.id,
            "event_name": "inventory.item_received",
            "schema_version": 1,
            "payload": {"key": "val"},
        }])[0]

        # 2. create() directo prohibido para todos los roles
        direct_vals = {
            "company_id": self.Company.id,
            "event_name": "inventory.item_received",
            "schema_version": 1,
            "payload": {"key": "val"},
        }
        with self.assertRaises(UserError):
            self.Outbox.with_user(self.user_operator).create(direct_vals)
        with self.assertRaises(UserError):
            self.Outbox.with_user(self.user_supervisor).create(direct_vals)
        with self.assertRaises(UserError):
            self.Outbox.with_user(self.user_manager).create(direct_vals)
        with self.assertRaises(UserError):
            self.Outbox.with_user(self.user_admin).create(direct_vals)

        # 3. write() prohibido
        with self.assertRaises(UserError):
            msg.with_user(self.user_operator).write({"status": "SENT"})
        with self.assertRaises(UserError):
            msg.with_user(self.user_supervisor).write({"status": "SENT"})
        with self.assertRaises(UserError):
            msg.with_user(self.user_manager).write({"status": "SENT"})
        with self.assertRaises(UserError):
            msg.with_user(self.user_admin).write({"status": "SENT"})

        # 4. unlink() prohibido
        with self.assertRaises(UserError):
            msg.with_user(self.user_operator).unlink()
        with self.assertRaises(UserError):
            msg.with_user(self.user_supervisor).unlink()
        with self.assertRaises(UserError):
            msg.with_user(self.user_manager).unlink()
        with self.assertRaises(UserError):
            msg.with_user(self.user_admin).unlink()

        # 5. Verificar estado inicial
        self.assertEqual(msg.status, "PENDING")
        self.assertEqual(msg.attempt_count, 0)
        self.assertFalse(msg.next_attempt_at)
        self.assertFalse(msg.published_at)
        self.assertFalse(msg.last_error)

    # -------------------------------------------------------------------------
    # TEST-INV-067: Validaciones e integridad (correlation_id, claves, unicidad DB)
    # -------------------------------------------------------------------------

    def test_inv_067_validations_and_integrity_constraints(self):
        """INV-067: Rechazo estricto de mensajes inválidos, correlation_id inválido, claves no permitidas y unicidad DB message_id."""
        valid_msg = {
            "company_id": self.Company.id,
            "event_name": "inventory.test",
            "schema_version": 1,
            "payload": {"test": 1},
        }

        # 1. messages no válido
        with self.assertRaises(UserError):
            self.Outbox.with_user(self.user_manager)._enqueue_messages([])
        with self.assertRaises(UserError):
            self.Outbox.with_user(self.user_manager)._enqueue_messages("not-a-list")
        with self.assertRaises(UserError):
            self.Outbox.with_user(self.user_manager)._enqueue_messages([None])

        # 2. correlation_id estricto
        invalid_corrs = [False, 0, 123, "", "   ", self.Company]
        for inv_corr in invalid_corrs:
            with self.assertRaises(ValidationError):
                self.Outbox.with_user(self.user_manager)._enqueue_messages([valid_msg], correlation_id=inv_corr)

        # 3. event_name inválido
        with self.assertRaises(ValidationError):
            self.Outbox.with_user(self.user_manager)._enqueue_messages([{
                **valid_msg,
                "event_name": "",
            }])
        with self.assertRaises(ValidationError):
            self.Outbox.with_user(self.user_manager)._enqueue_messages([{
                **valid_msg,
                "event_name": "   ",
            }])
        with self.assertRaises(ValidationError):
            self.Outbox.with_user(self.user_manager)._enqueue_messages([{
                **valid_msg,
                "event_name": 123,
            }])

        # 4. schema_version inválida
        invalid_versions = [0, -1, True, False, "1", 1.5]
        for inv_ver in invalid_versions:
            with self.assertRaises(ValidationError):
                self.Outbox.with_user(self.user_manager)._enqueue_messages([{
                    **valid_msg,
                    "schema_version": inv_ver,
                }])

        # 5. payload no dict
        invalid_payloads = ["string", [1, 2], 123, None, True]
        for inv_payload in invalid_payloads:
            with self.assertRaises(ValidationError):
                self.Outbox.with_user(self.user_manager)._enqueue_messages([{
                    **valid_msg,
                    "payload": inv_payload,
                }])

        # 6. Claves no permitidas
        with self.assertRaises(ValidationError):
            self.Outbox.with_user(self.user_manager)._enqueue_messages([{
                **valid_msg,
                "unknown_key": "arbitrary_value",
            }])
        with self.assertRaises(ValidationError):
            self.Outbox.with_user(self.user_manager)._enqueue_messages([{
                **valid_msg,
                "quant_id": 123,
            }])

        # 7. Unicidad global de DB de message_id con rollback demostrable
        fixed_uuid = "11111111-2222-3333-4444-555555555555"
        with patch("uuid.uuid4", return_value=uuid.UUID(fixed_uuid)):
            # Batch de 2 mensajes con correlation_id explícito y mismo message_id simulado
            msg_batch = [
                {**valid_msg, "payload": {"item": 1}},
                {**valid_msg, "payload": {"item": 2}},
            ]
            count_before = self.Outbox.search_count([])
            with self.assertRaises(Exception):  # IntegrityError envuelto por ORM
                with self.env.cr.savepoint():
                    self.Outbox.with_user(self.user_manager)._enqueue_messages(msg_batch, correlation_id="COLLISION-TEST-CORR")

            # Demostrar que el batch completo hizo rollback y no quedó ningún registro parcial
            self.assertEqual(self.Outbox.search_count([]), count_before)

    # -------------------------------------------------------------------------
    # TEST-INV-068: RBAC estricto y aislamiento multi-compañía
    # -------------------------------------------------------------------------

    def test_inv_068_rbac_and_multi_company_isolation(self):
        """INV-068: Operator/Supervisor encolan (C=1) sin leer (R=0); Manager/Admin encolan y leen; Plain Internal denegado; multi-company."""
        valid_msg = {
            "company_id": self.Company.id,
            "event_name": "inventory.test_rbac",
            "schema_version": 1,
            "payload": {"user_test": True},
        }

        # 1. Operator: C=1 (enqueue PASS), R=0 (read AccessError)
        op_outbox = self.Outbox.with_user(self.user_operator)._enqueue_messages([valid_msg])
        self.assertEqual(len(op_outbox), 1)
        created_id = op_outbox.id

        # Intentar leer los campos del registro como Operator genera AccessError
        with self.assertRaises(AccessError):
            _ = op_outbox.with_user(self.user_operator).event_name

        with self.assertRaises(AccessError):
            self.Outbox.with_user(self.user_operator).search([("id", "=", created_id)])

        # Comprobar desde Manager que el registro efectivamente se creó en la DB
        self.assertTrue(self.Outbox.with_user(self.user_manager).search([("id", "=", created_id)]))

        # 2. Supervisor: C=1 (enqueue PASS), R=0 (read AccessError)
        sup_outbox = self.Outbox.with_user(self.user_supervisor)._enqueue_messages([valid_msg])
        self.assertEqual(len(sup_outbox), 1)
        sup_id = sup_outbox.id

        with self.assertRaises(AccessError):
            _ = sup_outbox.with_user(self.user_supervisor).event_name

        with self.assertRaises(AccessError):
            self.Outbox.with_user(self.user_supervisor).search([("id", "=", sup_id)])

        self.assertTrue(self.Outbox.with_user(self.user_manager).search([("id", "=", sup_id)]))

        # 3. Manager: C=1, R=1, W=1
        mgr_outbox = self.Outbox.with_user(self.user_manager)._enqueue_messages([valid_msg])
        self.assertEqual(len(mgr_outbox), 1)
        self.assertEqual(mgr_outbox.event_name, "inventory.test_rbac")
        self.assertTrue(self.Outbox.with_user(self.user_manager).search([("id", "=", mgr_outbox.id)]))

        # 4. System Admin: C=1, R=1, W=1
        adm_outbox = self.Outbox.with_user(self.user_admin)._enqueue_messages([valid_msg])
        self.assertEqual(len(adm_outbox), 1)
        self.assertEqual(adm_outbox.event_name, "inventory.test_rbac")
        self.assertTrue(self.Outbox.with_user(self.user_admin).search([("id", "=", adm_outbox.id)]))

        # 5. Plain Internal: C=0, R=0 (AccessError en ambos)
        with self.assertRaises(AccessError):
            self.Outbox.with_user(self.user_plain_internal)._enqueue_messages([valid_msg])

        with self.assertRaises(AccessError):
            self.Outbox.with_user(self.user_plain_internal).search([("id", "=", mgr_outbox.id)])

        # 6. Multi-compañía:
        # Operator de compañía principal intentando encolar para compañía secundaria -> AccessError
        with self.assertRaises(AccessError):
            self.Outbox.with_user(self.user_operator)._enqueue_messages([{
                **valid_msg,
                "company_id": self.company_secondary.id,
            }])

        # Manager de compañía secundaria no puede leer mensajes de compañía principal
        sec_mgr_seen = self.Outbox.with_user(self.user_sec_manager).search([("id", "in", [created_id, sup_id, mgr_outbox.id, adm_outbox.id])])
        self.assertEqual(len(sec_mgr_seen), 0, "Manager de compañía secundaria no debe ver mensajes outbox de compañía principal")

    # -------------------------------------------------------------------------
    # TEST-INV-069: Límite de efectos secundarios (side-effect boundary)
    # -------------------------------------------------------------------------

    def test_inv_069_side_effect_boundary(self):
        """INV-069: _enqueue_messages() crea exclusivamente outbox rows; events, blocks, quants, moves, packages intactos."""
        # 1. Precondiciones: Quant con package, block activo, block liberado, eventos preexistentes
        quant = self.Quant.create({
            "product_id": self.product.id,
            "location_id": self.loc_src.id,
            "package_id": self.package.id,
            "quantity": 50.0,
            "reserved_quantity": 10.0,
            "company_id": self.Company.id,
        })
        active_block = self.Block.create({
            "company_id": self.Company.id,
            "block_scope": "LOCATION",
            "location_id": self.loc_src.id,
            "block_type": "HOLD",
            "reason": "Test Active Block",
        })
        rel_block = self.Block.create({
            "company_id": self.Company.id,
            "block_scope": "PACKAGE",
            "package_id": self.package.id,
            "block_type": "INVESTIGATION",
            "reason": "Test Released Block",
        })
        rel_block.with_user(self.user_supervisor).action_release()

        pre_events = self.Event.with_user(self.user_operator)._append_events([
            {
                "company_id": self.Company.id,
                "event_type": "RECEIVE",
                "product_id": self.product.id,
                "quantity": 50.0,
            },
            {
                "company_id": self.Company.id,
                "event_type": "MOVE",
                "product_id": self.product.id,
                "quantity": 10.0,
            },
        ])

        # Snapshot inicial
        orig_quant_id = quant.id
        orig_quant_qty = quant.quantity
        orig_quant_res = quant.reserved_quantity
        orig_quant_pkg = quant.package_id

        outbox_count_before = self.Outbox.search_count([])
        event_count_before = self.Event.search_count([])
        block_count_before = self.Block.search_count([])
        move_count_before = self.StockMove.search_count([])
        move_line_count_before = self.StockMoveLine.search_count([])
        package_count_before = self.Package.search_count([])
        history_count_before = self.PackageHistory.search_count([])

        # 2. Ejecutar _enqueue_messages
        messages = self.Outbox.with_user(self.user_manager)._enqueue_messages([
            {
                "company_id": self.Company.id,
                "event_name": "inventory.stock_updated",
                "schema_version": 1,
                "payload": {"sku": self.product.default_code, "qty": 50.0},
            },
            {
                "company_id": self.Company.id,
                "event_name": "inventory.package_sealed",
                "schema_version": 1,
                "payload": {"package": self.package.name},
            },
        ])

        # 3. Validar que solo outbox aumentó en 2
        self.assertEqual(len(messages), 2)
        self.assertEqual(self.Outbox.search_count([]), outbox_count_before + 2)

        # 4. Validar que los demás dominios/modelos permanecen 100% idénticos
        self.assertEqual(self.Event.search_count([]), event_count_before)
        self.assertEqual(self.Block.search_count([]), block_count_before)
        self.assertEqual(self.StockMove.search_count([]), move_count_before)
        self.assertEqual(self.StockMoveLine.search_count([]), move_line_count_before)
        self.assertEqual(self.Package.search_count([]), package_count_before)
        self.assertEqual(self.PackageHistory.search_count([]), history_count_before)

        quant.invalidate_recordset()
        self.assertEqual(quant.id, orig_quant_id)
        self.assertEqual(quant.quantity, orig_quant_qty)
        self.assertEqual(quant.reserved_quantity, orig_quant_res)
        self.assertEqual(quant.package_id, orig_quant_pkg)

        active_block.invalidate_recordset()
        self.assertFalse(active_block.released_at)

        rel_block.invalidate_recordset()
        self.assertTrue(bool(rel_block.released_at))
