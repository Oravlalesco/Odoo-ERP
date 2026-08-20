from psycopg2 import IntegrityError

from odoo.tests.common import TransactionCase


class TestShelfLifePolicy(TransactionCase):
    """PLM-005A: Validar política de vida útil (shelf-life).

    Cubre: contrato de campos (Integer, optional, no index, no default),
    perfil sin política (0, 0), umbrales positivos e independientes,
    rechazo de receipt negativo por DB CHECK, rechazo de shipping
    negativo por DB CHECK, y límites de la fuente de verdad (no duplicación
    de campos de fecha Odoo y capacidad de volver a 0).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.WPL = cls.env["wms.product.logistics"]
        cls.PT = cls.env["product.template"]
        cls.company = cls.env.company

        cls.product_1 = cls.PT.create({
            "name": "Shelf Life Test Product 1",
            "company_id": cls.company.id,
        })
        cls.product_2 = cls.PT.create({
            "name": "Shelf Life Test Product 2",
            "company_id": cls.company.id,
        })
        cls.product_3 = cls.PT.create({
            "name": "Shelf Life Test Product 3",
            "company_id": cls.company.id,
        })

    # ------------------------------------------------------------------
    # TEST-PLM-039: Contrato de campos
    # ------------------------------------------------------------------

    def test_plm_039_field_contract(self):
        """PLM-005A-039: ambos campos Integer, opcionales, sin index ni default."""
        WPL = self.env["wms.product.logistics"]

        for field_name in ("min_shelf_life_receipt_days", "min_shelf_life_shipping_days"):
            f = WPL._fields[field_name]
            self.assertEqual(f.type, "integer", f"{field_name} must be Integer")
            self.assertFalse(f.required, f"{field_name} must be optional")
            self.assertFalse(f.index, f"{field_name} must not be indexed")
            self.assertFalse(f.default, f"{field_name} must not have automatic default")

    # ------------------------------------------------------------------
    # TEST-PLM-040: Perfil sin política configurada es válido
    # ------------------------------------------------------------------

    def test_plm_040_profile_without_policy_valid(self):
        """PLM-005A-040: perfil sin política tiene receipt=0 y shipping=0."""
        profile = self.WPL.create({
            "product_tmpl_id": self.product_1.id,
        })
        self.assertTrue(profile.id)
        self.assertEqual(profile.min_shelf_life_receipt_days, 0)
        self.assertEqual(profile.min_shelf_life_shipping_days, 0)

    # ------------------------------------------------------------------
    # TEST-PLM-041: Umbrales positivos e independientes
    # ------------------------------------------------------------------

    def test_plm_041_positive_independent_thresholds(self):
        """PLM-005A-041: receipt y shipping son independientes y persisten."""
        # receipt < shipping
        p1 = self.PT.create({"name": "Shelf Life P1", "company_id": self.company.id})
        profile1 = self.WPL.create({
            "product_tmpl_id": p1.id,
            "min_shelf_life_receipt_days": 30,
            "min_shelf_life_shipping_days": 60,
        })
        self.assertEqual(profile1.min_shelf_life_receipt_days, 30)
        self.assertEqual(profile1.min_shelf_life_shipping_days, 60)

        # receipt > shipping
        p2 = self.PT.create({"name": "Shelf Life P2", "company_id": self.company.id})
        profile2 = self.WPL.create({
            "product_tmpl_id": p2.id,
            "min_shelf_life_receipt_days": 90,
            "min_shelf_life_shipping_days": 45,
        })
        self.assertEqual(profile2.min_shelf_life_receipt_days, 90)
        self.assertEqual(profile2.min_shelf_life_shipping_days, 45)

    # ------------------------------------------------------------------
    # TEST-PLM-042: Receipt negativo rechazado por DB CHECK
    # ------------------------------------------------------------------

    def test_plm_042_negative_receipt_rejected(self):
        """PLM-005A-042: DB CHECK rechaza min_shelf_life_receipt_days < 0."""
        p = self.PT.create({"name": "Negative Receipt Product", "company_id": self.company.id})

        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.WPL.create({
                    "product_tmpl_id": p.id,
                    "min_shelf_life_receipt_days": -1,
                })

    # ------------------------------------------------------------------
    # TEST-PLM-043: Shipping negativo rechazado por DB CHECK
    # ------------------------------------------------------------------

    def test_plm_043_negative_shipping_rejected(self):
        """PLM-005A-043: DB CHECK rechaza min_shelf_life_shipping_days < 0."""
        p = self.PT.create({"name": "Negative Shipping Product", "company_id": self.company.id})

        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.WPL.create({
                    "product_tmpl_id": p.id,
                    "min_shelf_life_shipping_days": -1,
                })

    # ------------------------------------------------------------------
    # TEST-PLM-044: Límites de la fuente de verdad y reseteo a 0
    # ------------------------------------------------------------------

    def test_plm_044_source_of_truth_boundary(self):
        """PLM-005A-044: sin duplicación de campos Odoo y reseteo a 0."""
        WPL = self.env["wms.product.logistics"]

        # wms.product.logistics no contiene campos temporales ni de fecha de Odoo
        forbidden_fields = (
            "shelf_life_uom",
            "expiration_date",
            "use_date",
            "removal_date",
            "alert_date",
            "expiration_time",
        )
        for field_name in forbidden_fields:
            self.assertNotIn(
                field_name,
                WPL._fields,
                f"wms.product.logistics must NOT define '{field_name}'",
            )

        # Configurar y luego resetear a 0
        profile = self.WPL.create({
            "product_tmpl_id": self.product_3.id,
            "min_shelf_life_receipt_days": 180,
            "min_shelf_life_shipping_days": 90,
        })
        self.assertEqual(profile.min_shelf_life_receipt_days, 180)
        self.assertEqual(profile.min_shelf_life_shipping_days, 90)

        profile.write({
            "min_shelf_life_receipt_days": 0,
            "min_shelf_life_shipping_days": 0,
        })
        self.assertEqual(profile.min_shelf_life_receipt_days, 0)
        self.assertEqual(profile.min_shelf_life_shipping_days, 0)
