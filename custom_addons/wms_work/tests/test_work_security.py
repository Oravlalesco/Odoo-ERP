# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import AccessError
from odoo.tools import mute_logger

from .common import WorkCommon


class TestWorkSecurity(WorkCommon):
    """Pruebas unitarias de seguridad RBAC, ACL y aislamiento multi-compañía (WORK-002)."""

    def setUp(self):
        super().setUp()
        self.work_a = self.env["wms.work"].create({
            "warehouse_id": self.warehouse_a.id,
        })
        self.line_a = self.env["wms.work.line"].create({
            "work_id": self.work_a.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
        })

    def test_work_14_acl_existence_and_exact_bits(self):
        """TEST-WORK-014: Existencia y bits exactos de las 8 ACLs en ir.model.access."""
        Acl = self.env["ir.model.access"]
        model_work = self.env["ir.model"]._get_id("wms.work")
        model_work_line = self.env["ir.model"]._get_id("wms.work.line")

        # Roles y bits esperados (read, write, create, unlink)
        expected_acls = [
            # wms.work
            (model_work, self.group_operator.id, True, False, False, False),
            (model_work, self.group_supervisor.id, True, False, False, False),
            (model_work, self.group_manager.id, True, False, False, False),
            (model_work, self.group_system.id, True, True, True, True),
            # wms.work.line
            (model_work_line, self.group_operator.id, True, False, False, False),
            (model_work_line, self.group_supervisor.id, True, False, False, False),
            (model_work_line, self.group_manager.id, True, False, False, False),
            (model_work_line, self.group_system.id, True, True, True, True),
        ]

        for model_id, group_id, r, w, c, u in expected_acls:
            acl = Acl.search([
                ("model_id", "=", model_id),
                ("group_id", "=", group_id),
            ], limit=1)
            self.assertTrue(acl, f"ACL no encontrada para model_id={model_id}, group_id={group_id}")
            self.assertEqual(acl.perm_read, r)
            self.assertEqual(acl.perm_write, w)
            self.assertEqual(acl.perm_create, c)
            self.assertEqual(acl.perm_unlink, u)

    def test_work_15_crud_matrix_by_role(self):
        """TEST-WORK-015: Matriz CRUD completa por rol."""
        # 1. Operador WMS: Read-Only (Create, Write, Unlink prohibidos)
        work_op = self.work_a.with_user(self.user_operator)
        self.assertEqual(work_op.reference, self.work_a.reference)
        with self.assertRaises(AccessError):
            self.env["wms.work"].with_user(self.user_operator).create({
                "warehouse_id": self.warehouse_a.id,
            })
        with self.assertRaises(AccessError):
            work_op.write({"priority": 80})
        with self.assertRaises(AccessError):
            work_op.unlink()

        # Líneas para Operador
        line_op = self.line_a.with_user(self.user_operator)
        self.assertEqual(line_op.action, "pick")
        with self.assertRaises(AccessError):
            self.env["wms.work.line"].with_user(self.user_operator).create({
                "work_id": self.work_a.id,
                "sequence": 99,
                "action": "put",
                "source_location_id": self.loc_source_a.id,
            })
        with self.assertRaises(AccessError):
            line_op.write({"quantity": 10.0})
        with self.assertRaises(AccessError):
            line_op.unlink()

        # 2. Supervisor WMS: Read-Only (Create, Write, Unlink prohibidos en WORK-002)
        work_sup = self.work_a.with_user(self.user_supervisor)
        self.assertEqual(work_sup.reference, self.work_a.reference)
        with self.assertRaises(AccessError):
            self.env["wms.work"].with_user(self.user_supervisor).create({
                "warehouse_id": self.warehouse_a.id,
            })
        with self.assertRaises(AccessError):
            work_sup.write({"priority": 80})
        with self.assertRaises(AccessError):
            work_sup.unlink()

        # Líneas para Supervisor
        line_sup = self.line_a.with_user(self.user_supervisor)
        self.assertEqual(line_sup.action, "pick")
        with self.assertRaises(AccessError):
            self.env["wms.work.line"].with_user(self.user_supervisor).create({
                "work_id": self.work_a.id,
                "sequence": 99,
                "action": "put",
                "source_location_id": self.loc_source_a.id,
            })
        with self.assertRaises(AccessError):
            line_sup.write({"quantity": 10.0})
        with self.assertRaises(AccessError):
            line_sup.unlink()

        # 3. Manager WMS: Read-Only (Create, Write, Unlink prohibidos en WORK-002)
        work_mgr = self.work_a.with_user(self.user_manager)
        self.assertEqual(work_mgr.reference, self.work_a.reference)
        with self.assertRaises(AccessError):
            self.env["wms.work"].with_user(self.user_manager).create({
                "warehouse_id": self.warehouse_a.id,
            })
        with self.assertRaises(AccessError):
            work_mgr.write({"priority": 80})
        with self.assertRaises(AccessError):
            work_mgr.unlink()

        # Líneas para Manager
        line_mgr = self.line_a.with_user(self.user_manager)
        self.assertEqual(line_mgr.action, "pick")
        with self.assertRaises(AccessError):
            self.env["wms.work.line"].with_user(self.user_manager).create({
                "work_id": self.work_a.id,
                "sequence": 99,
                "action": "put",
                "source_location_id": self.loc_source_a.id,
            })
        with self.assertRaises(AccessError):
            line_mgr.write({"quantity": 10.0})
        with self.assertRaises(AccessError):
            line_mgr.unlink()

        # 4. System Admin: Full CRUD (Header + Lines)
        work_sys = self.env["wms.work"].with_user(self.user_system).create({
            "warehouse_id": self.warehouse_a.id,
            "priority": 75,
        })
        self.assertEqual(work_sys.priority, 75)
        work_sys.write({"priority": 85})
        self.assertEqual(work_sys.priority, 85)

        line_sys = self.env["wms.work.line"].with_user(self.user_system).create({
            "work_id": work_sys.id,
            "sequence": 10,
            "action": "put",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "quantity": 12.0,
        })
        self.assertEqual(line_sys.quantity, 12.0)
        line_sys.write({"quantity": 15.0})
        self.assertEqual(line_sys.quantity, 15.0)
        line_sys.unlink()
        work_sys.unlink()

    def test_work_16_multi_company_isolation(self):
        """TEST-WORK-016: Aislamiento multi-compañía de encabezado y líneas."""
        work_b = self.env["wms.work"].create({
            "warehouse_id": self.warehouse_b.id,
        })
        line_b = self.env["wms.work.line"].create({
            "work_id": work_b.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_b.id,
        })

        # Operador de Company A buscando works
        visible_works = self.env["wms.work"].with_user(self.user_operator).search([])
        self.assertIn(self.work_a, visible_works)
        self.assertNotIn(work_b, visible_works)

        visible_lines = self.env["wms.work.line"].with_user(self.user_operator).search([])
        self.assertIn(self.line_a, visible_lines)
        self.assertNotIn(line_b, visible_lines)

        # Acceso directo a registro de otra compañía bloqueado por record rule
        with mute_logger("odoo.addons.base.models.ir_rule"), self.assertRaises(AccessError):
            work_b.with_user(self.user_operator).read(["reference"])

    def test_work_17_plain_and_stock_only_users_rejected(self):
        """TEST-WORK-017: Usuarios plain y stock-only reciben AccessError (0 acceso)."""
        # Usuario plain (solo base.group_user)
        with self.assertRaises(AccessError):
            self.work_a.with_user(self.user_plain).read(["reference"])
        with self.assertRaises(AccessError):
            self.env["wms.work"].with_user(self.user_plain).search([])
        with self.assertRaises(AccessError):
            self.line_a.with_user(self.user_plain).read(["action"])

        # Usuario Stock Only (stock.group_stock_user sin rol WMS)
        with self.assertRaises(AccessError):
            self.work_a.with_user(self.user_stock_user).read(["reference"])
        with self.assertRaises(AccessError):
            self.env["wms.work"].with_user(self.user_stock_user).search([])
        with self.assertRaises(AccessError):
            self.line_a.with_user(self.user_stock_user).read(["action"])

    def test_work_18_negative_boundary(self):
        """TEST-WORK-018: Boundary negativo: sin lease, queue, commands ni mutación de stock."""
        Work = self.env["wms.work"]
        Line = self.env["wms.work.line"]

        # 1. Ausencia de campos de slices diferidos
        deferred_work_fields = [
            "assigned_resource_id",
            "claim_token",
            "lease_expires_at",
            "last_heartbeat_at",
            "queue_id",
            "work_type_id",
            "picking_id",
        ]
        for f in deferred_work_fields:
            self.assertNotIn(f, Work._fields, f"El campo diferido '{f}' no debe existir en wms.work.")

        deferred_line_fields = [
            "move_id",
            "move_line_id",
            "line_state",
            "completed_qty",
        ]
        for f in deferred_line_fields:
            self.assertNotIn(f, Line._fields, f"El campo diferido '{f}' no debe existir en wms.work.line.")

        # 2. Ausencia de métodos operacionales diferidos (action_* o cmd_*)
        deferred_methods = [
            "action_validate",
            "action_assign",
            "action_start",
            "action_complete",
            "action_cancel",
            "action_reclaim",
            "cmd_accept_work",
            "cmd_confirm_pick",
            "cmd_confirm_put",
            "cmd_report_short",
            "cmd_report_exception",
            "cmd_heartbeat",
        ]
        for m in deferred_methods:
            self.assertFalse(
                hasattr(Work, m),
                f"Método operacional diferido '{m}' no debe existir en wms.work.",
            )
            self.assertFalse(
                hasattr(Line, m),
                f"Método operacional diferido '{m}' no debe existir en wms.work.line.",
            )

        # 3. Creación y borrado de Work y Work Line no muta quants ni genera outbox/events
        quant_count_before = self.env["stock.quant"].search_count([])
        outbox_count_before = self.env["wms.outbox"].search_count([])
        event_count_before = self.env["wms.inventory.event"].search_count([])

        w = Work.create({"warehouse_id": self.warehouse_a.id})
        l = Line.create({
            "work_id": w.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "quantity": 10.0,
        })
        l.unlink()
        w.unlink()

        quant_count_after = self.env["stock.quant"].search_count([])
        outbox_count_after = self.env["wms.outbox"].search_count([])
        event_count_after = self.env["wms.inventory.event"].search_count([])

        self.assertEqual(quant_count_before, quant_count_after, "Work CRUD no debe mutar stock.quant.")
        self.assertEqual(outbox_count_before, outbox_count_after, "Work CRUD no debe emitir outbox.")
        self.assertEqual(event_count_before, event_count_after, "Work CRUD no debe emitir wms.inventory.event.")
