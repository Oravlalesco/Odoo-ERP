# Part of Odoo. See LICENSE file for full copyright and licensing details.

from psycopg2.errors import CheckViolation, ForeignKeyViolation, UniqueViolation

from odoo.exceptions import ValidationError, UserError
from odoo.tools import mute_logger

from .common import WorkCommon


class TestWorkLineCore(WorkCommon):
    """Pruebas unitarias para la persistencia del modelo wms.work.line (WORK-002)."""

    def setUp(self):
        super().setUp()
        self.work_a = self.env["wms.work"].create({
            "warehouse_id": self.warehouse_a.id,
        })

    def test_work_08_line_schema_and_actions_catalog(self):
        """TEST-WORK-008: Schema, defaults y catálogo exacto de 8 acciones de línea."""
        self.assertIn("wms.work.line", self.env, "El modelo 'wms.work.line' debe existir en registry.")
        Line = self.env["wms.work.line"]
        self.assertEqual(Line._description, "Línea de Trabajo Dirigido WMS")
        self.assertEqual(Line._order, "work_id, sequence, id")

        expected_fields = [
            "work_id",
            "company_id",
            "sequence",
            "action",
            "source_location_id",
            "dest_location_id",
            "product_id",
            "product_uom_id",
            "lot_id",
            "package_id",
            "result_package_id",
            "owner_id",
            "quantity",
        ]
        for field_name in expected_fields:
            self.assertIn(
                field_name,
                Line._fields,
                f"El campo '{field_name}' debe existir en wms.work.line.",
            )

        # Validar flags requeridos y de compañía
        self.assertTrue(Line._fields["work_id"].required)
        self.assertEqual(Line._fields["work_id"].ondelete, "cascade")
        self.assertTrue(Line._fields["work_id"].check_company)

        self.assertTrue(Line._fields["company_id"].readonly)
        self.assertTrue(Line._fields["company_id"].store)

        self.assertTrue(Line._fields["sequence"].required)
        self.assertEqual(Line._fields["sequence"].default(Line), 10)

        self.assertTrue(Line._fields["action"].required)

        self.assertTrue(Line._fields["source_location_id"].required)
        self.assertEqual(Line._fields["source_location_id"].ondelete, "restrict")
        self.assertTrue(Line._fields["source_location_id"].check_company)

        self.assertEqual(Line._fields["dest_location_id"].ondelete, "restrict")
        self.assertTrue(Line._fields["dest_location_id"].check_company)

        self.assertEqual(Line._fields["product_id"].ondelete, "restrict")
        self.assertTrue(Line._fields["product_id"].check_company)

        self.assertEqual(Line._fields["lot_id"].ondelete, "restrict")
        self.assertTrue(Line._fields["lot_id"].check_company)

        self.assertEqual(Line._fields["package_id"].ondelete, "restrict")
        self.assertTrue(Line._fields["package_id"].check_company)

        self.assertEqual(Line._fields["result_package_id"].ondelete, "restrict")
        self.assertTrue(Line._fields["result_package_id"].check_company)

        self.assertEqual(Line._fields["owner_id"].ondelete, "restrict")
        self.assertTrue(Line._fields["owner_id"].check_company)

        self.assertTrue(Line._fields["quantity"].required)

        # Catálogo exacto de 8 acciones
        actions_dict = dict(Line._fields["action"].selection)
        expected_actions = {
            "pick",
            "put",
            "move",
            "count",
            "replenishment",
            "load",
            "inspect",
            "pack",
        }
        self.assertEqual(
            set(actions_dict.keys()),
            expected_actions,
            "El catálogo de acciones debe contener exactamente las 8 acciones aprobadas.",
        )

    def test_work_09_line_dimensions_persistence(self):
        """TEST-WORK-009: Persistencia de todas las dimensiones físicas."""
        line = self.env["wms.work.line"].create({
            "work_id": self.work_a.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "dest_location_id": self.loc_dest_a.id,
            "product_id": self.product_a.id,
            "product_uom_id": self.uom_unit.id,
            "lot_id": self.lot_a1.id,
            "package_id": self.package_a1.id,
            "result_package_id": self.package_a2.id,
            "owner_id": self.partner_a.id,
            "quantity": 5.0,
        })
        self.assertEqual(line.work_id, self.work_a)
        self.assertEqual(line.company_id, self.company_a)
        self.assertEqual(line.sequence, 10)
        self.assertEqual(line.action, "pick")
        self.assertEqual(line.source_location_id, self.loc_source_a)
        self.assertEqual(line.dest_location_id, self.loc_dest_a)
        self.assertEqual(line.product_id, self.product_a)
        self.assertEqual(line.product_uom_id, self.uom_unit)
        self.assertEqual(line.lot_id, self.lot_a1)
        self.assertEqual(line.package_id, self.package_a1)
        self.assertEqual(line.result_package_id, self.package_a2)
        self.assertEqual(line.owner_id, self.partner_a)
        self.assertEqual(line.quantity, 5.0)

    def test_work_10_sequence_ordering_and_uniqueness(self):
        """TEST-WORK-010: Orden y unicidad de sequence dentro de cada Work."""
        line_20 = self.env["wms.work.line"].create({
            "work_id": self.work_a.id,
            "sequence": 20,
            "action": "put",
            "source_location_id": self.loc_source_a.id,
        })
        line_10 = self.env["wms.work.line"].create({
            "work_id": self.work_a.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
        })
        self.work_a.invalidate_recordset(["line_ids"])
        self.assertEqual(
            self.work_a.line_ids.ids,
            [line_10.id, line_20.id],
            "Las líneas deben ordenarse por work_id, sequence, id.",
        )

        # Unicidad de sequence dentro del mismo work
        with mute_logger("odoo.sql_db"), self.assertRaises(UniqueViolation):
            self.env["wms.work.line"].create({
                "work_id": self.work_a.id,
                "sequence": 10,
                "action": "count",
                "source_location_id": self.loc_source_a.id,
            })

        # Misma secuencia en un work distinto está permitida
        work_other = self.env["wms.work"].create({
            "warehouse_id": self.warehouse_a.id,
        })
        line_other = self.env["wms.work.line"].create({
            "work_id": work_other.id,
            "sequence": 10,
            "action": "count",
            "source_location_id": self.loc_source_a.id,
        })
        self.assertEqual(line_other.sequence, 10)

    def test_work_11_uom_lot_quantity_invariants(self):
        """TEST-WORK-011: Invariantes dimensionales de UOM, lote y cantidad."""
        # 1. UOM omitida -> autocompleta con product.uom_id
        line_auto_uom = self.env["wms.work.line"].create({
            "work_id": self.work_a.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "quantity": 2.0,
        })
        self.assertEqual(line_auto_uom.product_uom_id, self.product_a.uom_id)

        # 2. UOM base aceptada
        line_base_uom = self.env["wms.work.line"].create({
            "work_id": self.work_a.id,
            "sequence": 20,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "product_uom_id": self.uom_unit.id,
            "quantity": 3.0,
        })
        self.assertEqual(line_base_uom.product_uom_id, self.uom_unit)

        # 3. UOM incluida en product.uom_ids aceptada
        line_extra_uom = self.env["wms.work.line"].create({
            "work_id": self.work_a.id,
            "sequence": 30,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "product_uom_id": self.uom_dozen.id,
            "quantity": 1.0,
        })
        self.assertEqual(line_extra_uom.product_uom_id, self.uom_dozen)

        # 4. UOM ajena no perteneciente a {uom_id} ∪ uom_ids -> rechazada
        with self.assertRaises(ValidationError):
            self.env["wms.work.line"].create({
                "work_id": self.work_a.id,
                "sequence": 40,
                "action": "pick",
                "source_location_id": self.loc_source_a.id,
                "product_id": self.product_a.id,
                "product_uom_id": self.uom_gram.id,
                "quantity": 1.0,
            })

        # 5. UOM de otra magnitud (metros) -> rechazada
        with self.assertRaises(ValidationError):
            self.env["wms.work.line"].create({
                "work_id": self.work_a.id,
                "sequence": 50,
                "action": "pick",
                "source_location_id": self.loc_source_a.id,
                "product_id": self.product_a.id,
                "product_uom_id": self.uom_meter.id,
                "quantity": 1.0,
            })

        # 5b. UOM existente SOLO en product.uom (barcode packaging) y no en product.uom_ids -> rechazada
        self.assertIn(self.uom_dozen, self.product_a.uom_ids)
        self.assertNotIn(self.uom_box, self.product_a.uom_ids)
        with self.assertRaises(ValidationError):
            self.env["wms.work.line"].create({
                "work_id": self.work_a.id,
                "sequence": 55,
                "action": "pick",
                "source_location_id": self.loc_source_a.id,
                "product_id": self.product_a.id,
                "product_uom_id": self.uom_box.id,
                "quantity": 1.0,
            })

        # 6. Lote de otro producto -> rechazado
        with self.assertRaises(ValidationError):
            self.env["wms.work.line"].create({
                "work_id": self.work_a.id,
                "sequence": 60,
                "action": "pick",
                "source_location_id": self.loc_source_a.id,
                "product_id": self.product_a.id,
                "lot_id": self.lot_b1.id,
                "quantity": 1.0,
            })

        # 7. Sin producto: lote prohibido
        with self.assertRaises(ValidationError):
            self.env["wms.work.line"].create({
                "work_id": self.work_a.id,
                "sequence": 70,
                "action": "move",
                "source_location_id": self.loc_source_a.id,
                "lot_id": self.lot_a1.id,
                "quantity": 0.0,
            })

        # Sin producto: UOM prohibida
        with self.assertRaises(ValidationError):
            self.env["wms.work.line"].create({
                "work_id": self.work_a.id,
                "sequence": 80,
                "action": "move",
                "source_location_id": self.loc_source_a.id,
                "product_uom_id": self.uom_unit.id,
                "quantity": 0.0,
            })

        # Sin producto: cantidad distinta de cero prohibida
        with self.assertRaises(ValidationError):
            self.env["wms.work.line"].create({
                "work_id": self.work_a.id,
                "sequence": 90,
                "action": "move",
                "source_location_id": self.loc_source_a.id,
                "quantity": 5.0,
            })

        # 8. Cantidad cero permitida (conteo ciego)
        line_count = self.env["wms.work.line"].create({
            "work_id": self.work_a.id,
            "sequence": 100,
            "action": "count",
            "source_location_id": self.loc_source_a.id,
            "quantity": 0.0,
        })
        self.assertEqual(line_count.quantity, 0.0)

        # Cantidad negativa rechazada
        with mute_logger("odoo.sql_db"), self.assertRaises(CheckViolation):
            self.env["wms.work.line"].create({
                "work_id": self.work_a.id,
                "sequence": 110,
                "action": "pick",
                "source_location_id": self.loc_source_a.id,
                "product_id": self.product_a.id,
                "quantity": -1.0,
            })

    def test_work_12_company_derivation_and_cross_company_guards(self):
        """TEST-WORK-012: Derivación de compañía y rechazo cross-company en todas las dimensiones."""
        line = self.env["wms.work.line"].create({
            "work_id": self.work_a.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
        })
        self.assertEqual(line.company_id, self.company_a)

        # Intento de mezclar ubicación origen de Company B en Work de Company A
        with self.assertRaises(UserError):
            self.env["wms.work.line"].create({
                "work_id": self.work_a.id,
                "sequence": 20,
                "action": "pick",
                "source_location_id": self.loc_source_b.id,
            })

    def test_work_13_ondelete_contracts(self):
        """TEST-WORK-013: Contratos ondelete: cascade de líneas y restrict de maestros."""
        work_tmp = self.env["wms.work"].create({
            "warehouse_id": self.warehouse_a.id,
        })
        line_tmp = self.env["wms.work.line"].create({
            "work_id": work_tmp.id,
            "sequence": 10,
            "action": "pick",
            "source_location_id": self.loc_source_a.id,
            "product_id": self.product_a.id,
            "lot_id": self.lot_a1.id,
            "package_id": self.package_a1.id,
            "owner_id": self.partner_a.id,
            "quantity": 1.0,
        })
        line_id = line_tmp.id
        work_tmp.unlink()

        # Cascade verificado
        self.assertFalse(
            self.env["wms.work.line"].search([("id", "=", line_id)]),
            "Al eliminar el work, las líneas asociadas deben eliminarse en cascada.",
        )

        # Restrict de almacén
        wh_tmp = self.Warehouse.create({
            "name": "WH Restrict Test",
            "code": "WHRT",
            "company_id": self.company_a.id,
        })
        self.env["wms.work"].create({
            "warehouse_id": wh_tmp.id,
        })
        with mute_logger("odoo.sql_db"), self.assertRaises(ForeignKeyViolation):
            wh_tmp.unlink()
