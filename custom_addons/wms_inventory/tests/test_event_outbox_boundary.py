import uuid
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestEventOutboxBoundary(TransactionCase):
    """Pruebas unitarias para el Boundary Atómico Event + Outbox (INV-010B).

    Valida:
    - TEST-INV-070: Boundary singleton: 1 event + 1 message coordinados con mismo UUID4 de correlación y estado inicial PENDING/0.
    - TEST-INV-071: Contrato de correlación compartida: normalización con whitespace y rechazo estricto de tipos inválidos con ValidationError.
    - TEST-INV-072: Orquestación batch (3+3): exactamente 1 delegación multi-record a _append_events() y 1 a _enqueue_messages(), correlation único compartido y message_ids únicos.
    - TEST-INV-073: Fallo en validación de Event detiene la operación antes de invocar Outbox; cero persistencia.
    - TEST-INV-074: Fallo en Outbox revierte el Event mediante ambient transaction rollback (savepoint); cero persistencia.
    - TEST-INV-075: ADR-019 ambient transaction rollback: mutación nativa de quant + Event + fallo Outbox revierte stock, Event y Outbox conjuntamente.
    - TEST-INV-076: Preservación de seguridad RBAC y límites de compañía: Operator/Supervisor/Manager ejecutan, Plain Internal y cross-company fallan con AccessError.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Event = cls.env["wms.inventory.event"]
        cls.Outbox = cls.env["wms.outbox"]
        cls.Quant = cls.env["stock.quant"]
        cls.Product = cls.env["product.product"]
        cls.Location = cls.env["stock.location"]
        cls.Lot = cls.env["stock.lot"]
        cls.Company = cls.env.company
        cls.Users = cls.env["res.users"]

        # Compañía secundaria
        cls.company_secondary = cls.env["res.company"].create({
            "name": "Secondary Co Boundary Test",
        })

        # Ubicaciones de prueba compañía principal
        cls.loc_src = cls.Location.create({
            "name": "Loc Source Boundary Test",
            "usage": "internal",
            "company_id": cls.Company.id,
        })
        cls.loc_dst = cls.Location.create({
            "name": "Loc Dest Boundary Test",
            "usage": "internal",
            "company_id": cls.Company.id,
        })

        # Ubicaciones compañía secundaria
        cls.loc_sec_src = cls.Location.create({
            "name": "Loc Sec Src Boundary Test",
            "usage": "internal",
            "company_id": cls.company_secondary.id,
        })
        cls.loc_sec_dst = cls.Location.create({
            "name": "Loc Sec Dst Boundary Test",
            "usage": "internal",
            "company_id": cls.company_secondary.id,
        })

        # Productos
        cls.product = cls.Product.create({
            "name": "Boundary Test Product",
            "is_storable": True,
        })

        # Grupos de seguridad
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_supervisor = cls.env.ref("wms_core.group_wms_supervisor")
        cls.group_manager = cls.env.ref("wms_core.group_wms_manager")
        cls.group_system = cls.env.ref("base.group_system")

        # Usuarios de prueba
        cls.user_operator = cls._create_user("u_bnd_op", [cls.group_operator.id])
        cls.user_supervisor = cls._create_user("u_bnd_sup", [cls.group_supervisor.id])
        cls.user_manager = cls._create_user("u_bnd_mgr", [cls.group_manager.id])
        cls.user_admin = cls._create_user("u_bnd_admin", [cls.group_system.id])
        cls.user_plain_internal = cls._create_user("u_bnd_plain", [])
        cls.user_sec_manager = cls.Users.create({
            "name": "User Sec Mgr Boundary Test",
            "login": "u_sec_bnd_mgr",
            "email": "sec_bnd_mgr@test.com",
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

    def _sample_event_vals(self, qty=10.0, event_type="PICK", company_id=None, loc_src=None, loc_dst=None):
        return {
            "company_id": company_id or self.Company.id,
            "event_type": event_type,
            "product_id": self.product.id,
            "source_location_id": (loc_src or self.loc_src).id,
            "dest_location_id": (loc_dst or self.loc_dst).id,
            "quantity": qty,
        }

    def _sample_message_vals(self, event_name="inventory.pick.completed", schema_version=1, payload=None, company_id=None):
        return {
            "company_id": company_id or self.Company.id,
            "event_name": event_name,
            "schema_version": schema_version,
            "payload": payload if payload is not None else {"pick_id": 1, "qty": 10.0},
        }

    # =========================================================================
    # TEST-INV-070: Boundary singleton
    # =========================================================================
    def test_inv_070_atomic_boundary_singleton(self):
        """TEST-INV-070: Persistencia coordinada de 1 evento y 1 mensaje outbox con mismo correlation UUID4."""
        event_count_before = self.Event.search_count([])
        outbox_count_before = self.Outbox.search_count([])

        event_vals = self._sample_event_vals(qty=15.0)
        msg_vals = self._sample_message_vals(payload={"order_id": 100, "qty": 15.0})

        events, outbox = self.Event.with_user(self.user_manager)._append_events_with_outbox(
            [event_vals],
            [msg_vals],
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(len(outbox), 1)
        self.assertEqual(self.Event.search_count([]), event_count_before + 1)
        self.assertEqual(self.Outbox.search_count([]), outbox_count_before + 1)

        # Mismo correlation_id en ambos records
        self.assertEqual(events.correlation_id, outbox.correlation_id)

        # Correlation debe ser UUID4 válido
        parsed_uuid = uuid.UUID(events.correlation_id)
        self.assertEqual(parsed_uuid.version, 4)

        # Outbox en estado inicial contractual
        self.assertEqual(outbox.status, "PENDING")
        self.assertEqual(outbox.attempt_count, 0)
        self.assertFalse(outbox.next_attempt_at)
        self.assertFalse(outbox.published_at)
        self.assertFalse(outbox.last_error)

    # =========================================================================
    # TEST-INV-071: Shared correlation contract
    # =========================================================================
    def test_inv_071_shared_correlation_contract(self):
        """TEST-INV-071: Correlation ID explícito normalizado y validación de tipos inválidos."""
        event_vals = self._sample_event_vals()
        msg_vals = self._sample_message_vals()

        # Correlation explícito con whitespace debe ser normalizado con strip()
        events, outbox = self.Event.with_user(self.user_manager)._append_events_with_outbox(
            [event_vals],
            [msg_vals],
            correlation_id="  CORR-010B-001  ",
        )
        self.assertEqual(events.correlation_id, "CORR-010B-001")
        self.assertEqual(outbox.correlation_id, "CORR-010B-001")

        # Casos inválidos deben fallar estrictamente con ValidationError
        invalid_correlations = [
            False,
            True,
            0,
            123,
            "",
            "   ",
            self.Event,
            [],
            {},
        ]
        for invalid_corr in invalid_correlations:
            with self.assertRaises(ValidationError, msg=f"Debió fallar con correlation_id={invalid_corr!r}"):
                self.Event.with_user(self.user_manager)._append_events_with_outbox(
                    [event_vals],
                    [msg_vals],
                    correlation_id=invalid_corr,
                )

    # =========================================================================
    # TEST-INV-072: Batch orchestration (3+3)
    # =========================================================================
    def test_inv_072_batch_uses_single_underlying_calls(self):
        """TEST-INV-072: Batch 3+3 ejecuta exactamente 1 llamada multi a cada API y comparte correlation."""
        event_vals_list = [
            self._sample_event_vals(qty=5.0),
            self._sample_event_vals(qty=10.0),
            self._sample_event_vals(qty=15.0),
        ]
        msg_vals_list = [
            self._sample_message_vals(payload={"item": 1}),
            self._sample_message_vals(payload={"item": 2}),
            self._sample_message_vals(payload={"item": 3}),
        ]

        target_event_model = type(self.env["wms.inventory.event"])
        target_outbox_model = type(self.env["wms.outbox"])

        orig_append = target_event_model._append_events
        orig_enqueue = target_outbox_model._enqueue_messages

        with patch.object(target_event_model, "_append_events", side_effect=orig_append, autospec=True) as mock_append, \
             patch.object(target_outbox_model, "_enqueue_messages", side_effect=orig_enqueue, autospec=True) as mock_enqueue:

            events, outbox = self.Event.with_user(self.user_manager)._append_events_with_outbox(
                event_vals_list,
                msg_vals_list,
            )

            self.assertEqual(mock_append.call_count, 1)
            self.assertEqual(mock_enqueue.call_count, 1)

        self.assertEqual(len(events), 3)
        self.assertEqual(len(outbox), 3)

        # Todos los registros de ambos batches deben compartir exactamente el mismo correlation_id
        corr_ids_events = {e.correlation_id for e in events}
        corr_ids_outbox = {o.correlation_id for o in outbox}
        self.assertEqual(len(corr_ids_events), 1)
        self.assertEqual(len(corr_ids_outbox), 1)
        self.assertEqual(corr_ids_events, corr_ids_outbox)

        # Cada mensaje en outbox debe tener un message_id UUID4 único
        message_ids = {o.message_id for o in outbox}
        self.assertEqual(len(message_ids), 3)

    # =========================================================================
    # TEST-INV-073: Event failure creates nothing
    # =========================================================================
    def test_inv_073_event_failure_creates_nothing(self):
        """TEST-INV-073: Si la validación de Event falla (quantity=0), Outbox jamás se invoca y nada persiste."""
        event_count_before = self.Event.search_count([])
        outbox_count_before = self.Outbox.search_count([])

        invalid_event = self._sample_event_vals(qty=0.0)
        valid_msg = self._sample_message_vals()

        target_outbox_model = type(self.env["wms.outbox"])
        with patch.object(target_outbox_model, "_enqueue_messages", autospec=True) as mock_enqueue:
            with self.assertRaises(ValidationError):
                self.Event.with_user(self.user_manager)._append_events_with_outbox(
                    [invalid_event],
                    [valid_msg],
                )

            # _enqueue_messages no debe haber sido invocado
            mock_enqueue.assert_not_called()

        self.assertEqual(self.Event.search_count([]), event_count_before)
        self.assertEqual(self.Outbox.search_count([]), outbox_count_before)

    # =========================================================================
    # TEST-INV-074: Outbox failure rolls back Event
    # =========================================================================
    def test_inv_074_outbox_failure_rolls_back_event(self):
        """TEST-INV-074: Si Outbox falla (payload inválido), el savepoint revierte el Event insertado."""
        event_count_before = self.Event.search_count([])
        outbox_count_before = self.Outbox.search_count([])

        valid_event = self._sample_event_vals(qty=10.0)
        invalid_msg = self._sample_message_vals(payload=["not_a_dict"])

        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                self.Event.with_user(self.user_manager)._append_events_with_outbox(
                    [valid_event],
                    [invalid_msg],
                )

        # Ambos conteos deben permanecer intactos tras el rollback
        self.assertEqual(self.Event.search_count([]), event_count_before)
        self.assertEqual(self.Outbox.search_count([]), outbox_count_before)

    # =========================================================================
    # TEST-INV-075: ADR-019 ambient transaction rollback
    # =========================================================================
    def test_inv_075_ambient_transaction_stock_event_outbox_rollback(self):
        """TEST-INV-075: Mutación nativa de stock + Event + fallo Outbox revierte quant, Event y Outbox."""
        # Establecer inventario inicial usando la primitiva nativa de Odoo
        self.Quant._update_available_quantity(self.product, self.loc_src, 50.0)

        quantity_before = self.Quant._get_available_quantity(
            self.product, self.loc_src, strict=True, allow_negative=True,
        )
        event_count_before = self.Event.search_count([])
        outbox_count_before = self.Outbox.search_count([])

        valid_event = self._sample_event_vals(qty=5.0)
        invalid_msg = self._sample_message_vals(payload="invalid_payload_string")

        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                # 1. Mutación física de inventario vía primitiva nativa ORM
                self.Quant._update_available_quantity(self.product, self.loc_src, -5.0)

                # 2. Boundary atómico Event + Outbox (falla en Outbox)
                self.Event.with_user(self.user_manager)._append_events_with_outbox(
                    [valid_event],
                    [invalid_msg],
                )

        # 3. Verificar que la transacción revertida restauró inventario, Event y Outbox
        quantity_after = self.Quant._get_available_quantity(
            self.product, self.loc_src, strict=True, allow_negative=True,
        )
        self.assertEqual(quantity_after, quantity_before)
        self.assertEqual(self.Event.search_count([]), event_count_before)
        self.assertEqual(self.Outbox.search_count([]), outbox_count_before)

    # =========================================================================
    # TEST-INV-076: RBAC and company boundary preserved
    # =========================================================================
    def test_inv_076_security_and_company_boundary_preserved(self):
        """TEST-INV-076: Operator/Supervisor/Manager ejecutan; Plain Internal y cross-company fallan."""
        event_vals = self._sample_event_vals(qty=2.0)
        msg_vals = self._sample_message_vals()

        # 1. Operator ejecuta exitosamente el boundary
        events_op, outbox_op = self.Event.with_user(self.user_operator)._append_events_with_outbox(
            [event_vals],
            [msg_vals],
        )
        self.assertEqual(len(events_op), 1)
        self.assertEqual(len(outbox_op), 1)

        # Operator no tiene permiso de lectura en outbox (Read=0 en INV-010A)
        with self.assertRaises(AccessError):
            outbox_op.read(["status"])

        # Manager sí puede leer y verificar el registro creado por el Operator
        persisted_outbox = self.Outbox.with_user(self.user_manager).browse(outbox_op.id)
        self.assertEqual(persisted_outbox.status, "PENDING")

        # 2. Supervisor ejecuta exitosamente el boundary
        events_sup, outbox_sup = self.Event.with_user(self.user_supervisor)._append_events_with_outbox(
            [event_vals],
            [msg_vals],
        )
        self.assertEqual(len(events_sup), 1)
        self.assertEqual(len(outbox_sup), 1)

        # 3. Manager ejecuta y puede leer directamente el outbox
        events_mgr, outbox_mgr = self.Event.with_user(self.user_manager)._append_events_with_outbox(
            [event_vals],
            [msg_vals],
        )
        self.assertEqual(len(events_mgr), 1)
        self.assertEqual(len(outbox_mgr), 1)
        self.assertEqual(outbox_mgr.status, "PENDING")

        # 4. Plain Internal (sin roles WMS) debe fallar con AccessError
        with self.assertRaises(AccessError):
            self.Event.with_user(self.user_plain_internal)._append_events_with_outbox(
                [event_vals],
                [msg_vals],
            )

        # 5. Aislamiento multi-compañía: Operator de Compañía Principal intentando crear en Compañía Secundaria
        sec_event_vals = self._sample_event_vals(
            company_id=self.company_secondary.id,
            loc_src=self.loc_sec_src,
            loc_dst=self.loc_sec_dst,
        )
        sec_msg_vals = self._sample_message_vals(
            company_id=self.company_secondary.id,
        )
        with self.assertRaises(AccessError):
            self.Event.with_user(self.user_operator)._append_events_with_outbox(
                [sec_event_vals],
                [sec_msg_vals],
            )
