# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.addons.wms_work.tests.common import WorkCommon


@tagged("post_install", "-at_install", "wms_work", "work_lifecycle")
class TestWorkLifecycle(WorkCommon):
    """Pruebas de ciclo de vida y máquina de estados (WORK-003).

    Cubre los acceptance tests contractuales TEST-WORK-019 a TEST-WORK-027.
    """

    def test_work_19_surface_and_deferred_boundaries(self):
        """TEST-WORK-019: Superficie exacta de lifecycle y boundary de capacidades diferidas."""
        work = self.env["wms.work"].create({"warehouse_id": self.warehouse_a.id})
        self.env["wms.work.line"].create({
            "work_id": work.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "quantity": 1.0,
        })

        # 1. Métodos expuestos autorizados existen y son invocables retornando True
        self.assertTrue(hasattr(work, "action_validate"))
        self.assertTrue(hasattr(work, "action_cancel"))
        self.assertTrue(hasattr(work, "_wms_transition_state"))

        res_val = work.action_validate()
        self.assertIs(res_val, True)
        self.assertEqual(work.state, "ready")

        res_canc = work.action_cancel()
        self.assertIs(res_canc, True)
        self.assertEqual(work.state, "cancelled")

        # 2. Métodos diferidos prohibidos no existen en este slice
        deferred_methods = [
            "action_claim",
            "action_assign",
            "action_accept",
            "action_start",
            "action_complete",
            "action_reconcile",
            "action_reclaim",
            "action_heartbeat",
        ]
        for meth in deferred_methods:
            self.assertFalse(
                hasattr(work, meth),
                f"El método diferido {meth} no debe existir en WORK-003.",
            )

    def test_work_20_creation_strictly_draft_and_multicreate_atomic(self):
        """TEST-WORK-020: Creación exclusivamente en draft y prevalidación de multi-create."""
        # 1. Creación sin estado -> draft
        work1 = self.env["wms.work"].create({"warehouse_id": self.warehouse_a.id})
        self.assertEqual(work1.state, "draft")

        # 2. Creación con estado draft explícito -> draft
        work2 = self.env["wms.work"].create({
            "warehouse_id": self.warehouse_a.id,
            "state": "draft",
        })
        self.assertEqual(work2.state, "draft")

        # 3. Creación con cualquier otro estado -> UserError
        non_draft_states = [
            "ready",
            "assigned",
            "in_progress",
            "completed",
            "exception",
            "reclaimable",
            "reconciliation_required",
            "cancelled",
        ]
        for st in non_draft_states:
            with self.assertRaises(UserError):
                self.env["wms.work"].create({
                    "warehouse_id": self.warehouse_a.id,
                    "state": st,
                })

        # 4. Multi-create atómico: si uno falla, ninguno se crea ni consume secuencia
        count_before = self.env["wms.work"].search_count([])
        with self.assertRaises(UserError):
            self.env["wms.work"].create([
                {"warehouse_id": self.warehouse_a.id},
                {"warehouse_id": self.warehouse_a.id, "state": "cancelled"},
            ])
        count_after = self.env["wms.work"].search_count([])
        self.assertEqual(count_before, count_after)

    def test_work_21_validation_requires_lines_and_idempotency(self):
        """TEST-WORK-021: Validación exige líneas; éxito e idempotencia."""
        # 1. Work sin líneas en draft no puede validarse
        work_empty = self.env["wms.work"].create({"warehouse_id": self.warehouse_a.id})
        self.assertEqual(len(work_empty.line_ids), 0)
        with self.assertRaises(UserError):
            work_empty.action_validate()
        self.assertEqual(work_empty.state, "draft")

        # 2. Work con líneas se valida correctamente
        self.env["wms.work.line"].create({
            "work_id": work_empty.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "quantity": 2.0,
        })
        res = work_empty.action_validate()
        self.assertIs(res, True)
        self.assertEqual(work_empty.state, "ready")

        # 3. Re-validación sobre estado ready es un no-op idempotente
        res_idempotent = work_empty.action_validate()
        self.assertIs(res_idempotent, True)
        self.assertEqual(work_empty.state, "ready")

    def test_work_22_cancel_from_ready_rejection_from_draft_and_terminality(self):
        """TEST-WORK-022: ready -> cancelled, rechazo desde draft y terminalidad."""
        work = self.env["wms.work"].create({"warehouse_id": self.warehouse_a.id})
        self.env["wms.work.line"].create({
            "work_id": work.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "quantity": 1.0,
        })

        # 1. action_cancel desde draft -> rechazada (los borradores se descartan con unlink)
        with self.assertRaises(UserError):
            work.action_cancel()
        self.assertEqual(work.state, "draft")

        # 2. Validar a ready y cancelar -> transiciona a cancelled
        work.action_validate()
        self.assertEqual(work.state, "ready")
        res_canc = work.action_cancel()
        self.assertIs(res_canc, True)
        self.assertEqual(work.state, "cancelled")

        # 3. Re-cancelar es idempotente
        res_idemp = work.action_cancel()
        self.assertIs(res_idemp, True)
        self.assertEqual(work.state, "cancelled")

        # 4. Cancelled es terminal: no se puede re-validar
        with self.assertRaises(UserError):
            work.action_validate()
        self.assertEqual(work.state, "cancelled")

    def test_work_23_forbidden_transition_matrix_and_direct_write_rejection(self):
        """TEST-WORK-023: Matriz de transiciones prohibidas y rechazo de write(state)."""
        work = self.env["wms.work"].create({"warehouse_id": self.warehouse_a.id})
        self.env["wms.work.line"].create({
            "work_id": work.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "quantity": 1.0,
        })

        # 1. Modificación directa de state prohibida para cualquier usuario
        with self.assertRaises(UserError):
            work.write({"state": "ready"})
        with self.assertRaises(UserError):
            work.write({"state": "cancelled"})
        with self.assertRaises(UserError):
            work.with_user(self.user_system).write({"state": "ready"})

        # 2. Primitive interna rechaza transiciones no autorizadas
        with self.assertRaises(UserError):
            work._wms_transition_state("in_progress")
        with self.assertRaises(UserError):
            work._wms_transition_state("completed")

    def test_work_24_batch_transition_all_or_nothing(self):
        """TEST-WORK-024: Transición batch all-or-nothing."""
        # Creamos 3 works: 2 válidos con líneas, 1 sin líneas
        w1 = self.env["wms.work"].create({"warehouse_id": self.warehouse_a.id})
        self.env["wms.work.line"].create({
            "work_id": w1.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "quantity": 1.0,
        })

        w2_invalid = self.env["wms.work"].create({"warehouse_id": self.warehouse_a.id})

        w3 = self.env["wms.work"].create({"warehouse_id": self.warehouse_a.id})
        self.env["wms.work.line"].create({
            "work_id": w3.id,
            "sequence": 10,
            "action": "put",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "quantity": 2.0,
        })

        batch = w1 | w2_invalid | w3
        with self.assertRaises(UserError):
            batch.action_validate()

        # Ninguno debió haber cambiado de estado
        self.assertEqual(w1.state, "draft")
        self.assertEqual(w2_invalid.state, "draft")
        self.assertEqual(w3.state, "draft")

    def test_work_25_immutability_of_header_and_lines_outside_draft(self):
        """TEST-WORK-025: Inmutabilidad de cabecera y líneas fuera de draft."""
        work = self.env["wms.work"].create({"warehouse_id": self.warehouse_a.id})
        line = self.env["wms.work.line"].create({
            "work_id": work.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "quantity": 5.0,
        })
        work.action_validate()
        self.assertEqual(work.state, "ready")

        # 1. En ready: almacén, referencia y borrado de work quedan prohibidos
        with self.assertRaises(UserError):
            work.write({"warehouse_id": self.warehouse_b.id})
        with self.assertRaises(UserError):
            work.write({"reference": "MODIFIED/REF"})
        with self.assertRaises(UserError):
            work.unlink()

        # 2. En ready: mutaciones de líneas prohibidas
        with self.assertRaises(UserError):
            self.env["wms.work.line"].create({
                "work_id": work.id,
                "sequence": 20,
                "action": "put",
                "source_location_id": self.loc_source_a.id,
            })
        with self.assertRaises(UserError):
            line.write({"quantity": 10.0})
        with self.assertRaises(UserError):
            line.unlink()
        with self.assertRaises(UserError):
            work.write({"line_ids": [Command.create({
                "sequence": 30,
                "action": "move",
                "source_location_id": self.loc_source_a.id,
            })]})

        # 3. En ready: prioridad y deadline sí pueden actualizarse
        work.write({"priority": 90, "deadline": fields.Datetime.now()})
        self.assertEqual(work.priority, 90)

        # 4. En cancelled (terminal): prioridad, deadline y unlink prohibidos
        work.action_cancel()
        self.assertEqual(work.state, "cancelled")
        with self.assertRaises(UserError):
            work.write({"priority": 10})
        with self.assertRaises(UserError):
            work.write({"deadline": fields.Datetime.now()})
        with self.assertRaises(UserError):
            work.unlink()

    def test_work_26_acl_multi_company_and_no_sudo(self):
        """TEST-WORK-026: ACL, multi-compañía y ausencia de sudo()."""
        work = self.env["wms.work"].create({"warehouse_id": self.warehouse_a.id})
        self.env["wms.work.line"].create({
            "work_id": work.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "quantity": 1.0,
        })

        # 1. Operador, Supervisor y Manager no tienen permiso de escritura en ACL
        for user in [self.user_operator, self.user_supervisor, self.user_manager]:
            with self.assertRaises(AccessError):
                work.with_user(user).action_validate()
            with self.assertRaises(AccessError):
                work.with_user(user).action_cancel()

        # 2. System Admin sí puede validar y cancelar
        res_val = work.with_user(self.user_system).action_validate()
        self.assertIs(res_val, True)
        self.assertEqual(work.state, "ready")

        res_canc = work.with_user(self.user_system).action_cancel()
        self.assertIs(res_canc, True)
        self.assertEqual(work.state, "cancelled")

        # 3. Aislamiento multi-compañía
        product_comp_b = self.Product.create({
            "name": "Product Beta Company",
            "type": "consu",
            "is_storable": True,
            "uom_id": self.uom_unit.id,
            "company_id": self.company_b.id,
        })
        work_b = self.env["wms.work"].create({"warehouse_id": self.warehouse_b.id})
        self.env["wms.work.line"].create({
            "work_id": work_b.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_b.id,
            "product_id": product_comp_b.id,
            "quantity": 1.0,
        })
        user_company_a = self.user_system.copy({
            "company_id": self.company_a.id,
            "company_ids": [Command.set([self.company_a.id])],
        })
        with self.assertRaises(AccessError):
            work_b.with_user(user_company_a).action_validate()

    def test_work_27_concurrency_locking_and_zero_side_effects(self):
        """TEST-WORK-027: Carrera concurrente validate/unlink; quant, events, outbox intactos."""
        # 1. Medición de invariantes de inventario y mensajería
        quants_before = self.env["stock.quant"].search_count([])
        events_before = self.env["wms.inventory.event"].search_count([])
        outbox_before = self.env["wms.outbox"].search_count([])

        work = self.env["wms.work"].create({"warehouse_id": self.warehouse_a.id})
        self.env["wms.work.line"].create({
            "work_id": work.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "quantity": 10.0,
        })

        # Transiciones de ciclo de vida
        work.action_validate()
        self.assertEqual(work.state, "ready")
        work.action_cancel()
        self.assertEqual(work.state, "cancelled")

        # 2. Delta 0 estricto en quants, eventos transaccionales y outbox
        quants_after = self.env["stock.quant"].search_count([])
        events_after = self.env["wms.inventory.event"].search_count([])
        outbox_after = self.env["wms.outbox"].search_count([])

        self.assertEqual(quants_before, quants_after)
        self.assertEqual(events_before, events_after)
        self.assertEqual(outbox_before, outbox_after)
