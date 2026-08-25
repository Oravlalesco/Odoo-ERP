# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta
from psycopg2.errors import CheckViolation, UniqueViolation

from odoo.exceptions import ValidationError
from odoo.tools import mute_logger

from .common import WorkCommon


class TestWorkCore(WorkCommon):
    """Pruebas unitarias para la persistencia del modelo wms.work (WORK-002)."""

    def test_work_03_registry_and_fields(self):
        """TEST-WORK-003: Registry, metadatos y campos exactos de wms.work."""
        self.assertIn("wms.work", self.env, "El modelo 'wms.work' debe existir en el registry.")
        Work = self.env["wms.work"]
        self.assertEqual(Work._description, "Trabajo Dirigido WMS")
        self.assertEqual(Work._rec_name, "reference")
        self.assertEqual(Work._order, "priority desc, deadline asc, id")

        standard_fields = {
            "id", "display_name", "create_uid", "create_date",
            "write_uid", "write_date", "__last_update",
        }
        actual_functional_fields = set(Work._fields.keys()) - standard_fields
        expected_functional_fields = {
            "reference",
            "warehouse_id",
            "company_id",
            "state",
            "priority",
            "deadline",
            "line_ids",
        }
        self.assertEqual(actual_functional_fields, expected_functional_fields)

        # Validar propiedades de los campos
        self.assertTrue(Work._fields["reference"].required)
        self.assertTrue(Work._fields["reference"].readonly)
        self.assertFalse(Work._fields["reference"].copy)

        self.assertTrue(Work._fields["warehouse_id"].required)
        self.assertEqual(Work._fields["warehouse_id"].ondelete, "restrict")
        self.assertTrue(Work._fields["warehouse_id"].check_company)

        self.assertTrue(Work._fields["company_id"].readonly)
        self.assertTrue(Work._fields["company_id"].store)

        self.assertTrue(Work._fields["state"].required)
        self.assertTrue(Work._fields["state"].readonly)
        self.assertFalse(Work._fields["state"].copy)

        self.assertTrue(Work._fields["priority"].required)

    def test_work_04_defaults_company_and_reference(self):
        """TEST-WORK-004: Defaults, compañía derivada y referencia automática."""
        work = self.env["wms.work"].create({
            "warehouse_id": self.warehouse_a.id,
        })
        self.assertTrue(work.reference, "Debe haberse asignado una referencia.")
        self.assertNotEqual(work.reference, "/", "La referencia debe haberse consumido de la secuencia.")
        self.assertTrue(work.reference.startswith("WORK/"), f"La referencia debe iniciar con 'WORK/': {work.reference}")
        self.assertEqual(work.company_id, self.company_a, "La compañía debe ser derivada de warehouse_id.company_id.")
        self.assertEqual(work.state, "draft", "El estado por defecto debe ser 'draft'.")
        self.assertEqual(work.priority, 50, "La prioridad por defecto debe ser 50.")
        self.assertFalse(work.deadline, "El deadline por defecto debe ser False.")

    def test_work_05_multi_create_and_explicit_reference(self):
        """TEST-WORK-005: Multi-create, unicidad y consumo correcto de secuencia."""
        works = self.env["wms.work"].create([
            {
                "warehouse_id": self.warehouse_a.id,
                "reference": "WORK-MANUAL-001",
            },
            {
                "warehouse_id": self.warehouse_a.id,
            },
        ])
        self.assertEqual(len(works), 2)
        self.assertEqual(
            works[0].reference,
            "WORK-MANUAL-001",
            "Una referencia explícita debe ser preservada sin sobrescribirse.",
        )
        self.assertTrue(
            works[1].reference.startswith("WORK/"),
            "El registro sin referencia debe recibir un valor de la secuencia.",
        )

        # Unicidad de referencia
        with mute_logger("odoo.sql_db"), self.assertRaises(UniqueViolation):
            self.env["wms.work"].create({
                "warehouse_id": self.warehouse_a.id,
                "reference": "WORK-MANUAL-001",
            })

    def test_work_06_priority_range_and_ordering(self):
        """TEST-WORK-006: Prioridad 0/100 válida, -1/101 rechazada y ordenamiento determinista."""
        work_0 = self.env["wms.work"].create({
            "warehouse_id": self.warehouse_a.id,
            "priority": 0,
        })
        self.assertEqual(work_0.priority, 0)

        work_100 = self.env["wms.work"].create({
            "warehouse_id": self.warehouse_a.id,
            "priority": 100,
        })
        self.assertEqual(work_100.priority, 100)

        # Prioridad negativa rechazada
        with mute_logger("odoo.sql_db"), self.assertRaises(CheckViolation):
            self.env["wms.work"].create({
                "warehouse_id": self.warehouse_a.id,
                "priority": -1,
            })

        # Prioridad superior a 100 rechazada
        with mute_logger("odoo.sql_db"), self.assertRaises(CheckViolation):
            self.env["wms.work"].create({
                "warehouse_id": self.warehouse_a.id,
                "priority": 101,
            })

        # Ordenamiento determinista: priority desc, deadline asc, id
        now = datetime.now()
        w_low = self.env["wms.work"].create({
            "warehouse_id": self.warehouse_a.id,
            "priority": 10,
            "deadline": now + timedelta(days=2),
        })
        w_high_later = self.env["wms.work"].create({
            "warehouse_id": self.warehouse_a.id,
            "priority": 90,
            "deadline": now + timedelta(days=5),
        })
        w_high_sooner = self.env["wms.work"].create({
            "warehouse_id": self.warehouse_a.id,
            "priority": 90,
            "deadline": now + timedelta(days=1),
        })

        found = self.env["wms.work"].search([("id", "in", [w_low.id, w_high_later.id, w_high_sooner.id])])
        self.assertEqual(
            found.ids,
            [w_high_sooner.id, w_high_later.id, w_low.id],
            "El orden de búsqueda debe respetar 'priority desc, deadline asc, id'.",
        )

    def test_work_07_canonical_states_catalog(self):
        """TEST-WORK-007: Catálogo de 9 estados canónicos; ausencia de claimed y done."""
        selection_dict = dict(self.env["wms.work"]._fields["state"].selection)
        expected_keys = {
            "draft",
            "ready",
            "assigned",
            "in_progress",
            "completed",
            "exception",
            "reclaimable",
            "reconciliation_required",
            "cancelled",
        }
        self.assertEqual(
            set(selection_dict.keys()),
            expected_keys,
            "El catálogo de estados debe contener exactamente los 9 estados canónicos de Work Execution v1.2.",
        )
        self.assertNotIn("claimed", selection_dict, "'claimed' está prohibido como estado persistido.")
        self.assertNotIn("done", selection_dict, "'done' está prohibido (el estado canónico es 'completed').")
