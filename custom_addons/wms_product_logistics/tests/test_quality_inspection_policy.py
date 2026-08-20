from psycopg2 import IntegrityError

from odoo.tests.common import TransactionCase


class TestQualityInspectionPolicy(TransactionCase):
    """PLM-006A: Validar política maestra de inspección de calidad.

    Cubre:
    - Contrato de campos (Boolean, Selection con VISUAL/DIMENSIONAL/SAMPLING, Float, opcionales, sin índices).
    - Perfil sin política configurada (False / False / 0.0) es válido.
    - Independencia de los tres campos de política.
    - Persistencia de los tipos de inspección.
    - Límites válidos de porcentaje de muestreo (0.0, 50.0, 100.0).
    - Rechazo de porcentaje de muestreo negativo (< 0) por DB CHECK.
    - Rechazo de porcentaje de muestreo mayor a 100 (> 100) por DB CHECK y reseteo a 0.0.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.WPL = cls.env["wms.product.logistics"]
        cls.PT = cls.env["product.template"]
        cls.company = cls.env.company

        cls.product_1 = cls.PT.create({
            "name": "Quality Policy Product 1",
            "company_id": cls.company.id,
        })
        cls.product_2 = cls.PT.create({
            "name": "Quality Policy Product 2",
            "company_id": cls.company.id,
        })
        cls.product_3 = cls.PT.create({
            "name": "Quality Policy Product 3",
            "company_id": cls.company.id,
        })

    # ------------------------------------------------------------------
    # TEST-PLM-053: Contrato de campos
    # ------------------------------------------------------------------

    def test_plm_053_field_contract(self):
        """PLM-006A-053: tipos exactos, Selection exacta, opcionales, sin índices ni defaults explícitos."""
        WPL = self.env["wms.product.logistics"]

        # requires_quality_inspection
        f_req = WPL._fields["requires_quality_inspection"]
        self.assertEqual(f_req.type, "boolean", "requires_quality_inspection must be Boolean")
        self.assertFalse(f_req.required, "requires_quality_inspection must be optional")
        self.assertFalse(f_req.index, "requires_quality_inspection must not be indexed")
        self.assertFalse(f_req.default, "requires_quality_inspection must not have explicit default")

        # quality_inspection_type
        f_type = WPL._fields["quality_inspection_type"]
        self.assertEqual(f_type.type, "selection", "quality_inspection_type must be Selection")
        expected_selection = [
            ("VISUAL", "Visual"),
            ("DIMENSIONAL", "Dimensional"),
            ("SAMPLING", "Muestreo"),
        ]
        self.assertEqual(f_type.selection, expected_selection, "quality_inspection_type selection mismatch")
        self.assertFalse(f_type.required, "quality_inspection_type must be optional")
        self.assertFalse(f_type.index, "quality_inspection_type must not be indexed")
        self.assertFalse(f_type.default, "quality_inspection_type must not have explicit default")

        # quality_sampling_rate
        f_rate = WPL._fields["quality_sampling_rate"]
        self.assertEqual(f_rate.type, "float", "quality_sampling_rate must be Float")
        self.assertFalse(f_rate.required, "quality_sampling_rate must be optional")
        self.assertFalse(f_rate.index, "quality_sampling_rate must not be indexed")
        self.assertFalse(f_rate.default, "quality_sampling_rate must not have explicit default")

    # ------------------------------------------------------------------
    # TEST-PLM-054: Perfil sin política configurada es válido
    # ------------------------------------------------------------------

    def test_plm_054_empty_policy_is_valid(self):
        """PLM-006A-054: perfil sin política tiene False / False / 0.0 y es válido."""
        p = self.PT.create({"name": "Empty Quality Product", "company_id": self.company.id})
        profile = self.WPL.create({
            "product_tmpl_id": p.id,
        })
        self.assertTrue(profile.id)
        self.assertFalse(profile.requires_quality_inspection)
        self.assertFalse(profile.quality_inspection_type)
        self.assertEqual(profile.quality_sampling_rate, 0.0)

    # ------------------------------------------------------------------
    # TEST-PLM-055: Campos de política son independientes
    # ------------------------------------------------------------------

    def test_plm_055_policy_fields_are_independent(self):
        """PLM-006A-055: combinaciones independientes válidas sin constraints artificiales."""
        # 1. requires=True sin type ni rate
        p1 = self.PT.create({"name": "Indep Product 1", "company_id": self.company.id})
        prof1 = self.WPL.create({
            "product_tmpl_id": p1.id,
            "requires_quality_inspection": True,
        })
        self.assertTrue(prof1.requires_quality_inspection)
        self.assertFalse(prof1.quality_inspection_type)
        self.assertEqual(prof1.quality_sampling_rate, 0.0)

        # 2. requires=False con type y rate
        p2 = self.PT.create({"name": "Indep Product 2", "company_id": self.company.id})
        prof2 = self.WPL.create({
            "product_tmpl_id": p2.id,
            "requires_quality_inspection": False,
            "quality_inspection_type": "VISUAL",
            "quality_sampling_rate": 10.0,
        })
        self.assertFalse(prof2.requires_quality_inspection)
        self.assertEqual(prof2.quality_inspection_type, "VISUAL")
        self.assertEqual(prof2.quality_sampling_rate, 10.0)

        # 3. requires=True con SAMPLING y rate
        p3 = self.PT.create({"name": "Indep Product 3", "company_id": self.company.id})
        prof3 = self.WPL.create({
            "product_tmpl_id": p3.id,
            "requires_quality_inspection": True,
            "quality_inspection_type": "SAMPLING",
            "quality_sampling_rate": 25.5,
        })
        self.assertTrue(prof3.requires_quality_inspection)
        self.assertEqual(prof3.quality_inspection_type, "SAMPLING")
        self.assertEqual(prof3.quality_sampling_rate, 25.5)

    # ------------------------------------------------------------------
    # TEST-PLM-056: Persistencia de tipos de inspección
    # ------------------------------------------------------------------

    def test_plm_056_inspection_types_persist(self):
        """PLM-006A-056: VISUAL, DIMENSIONAL y SAMPLING persisten correctamente."""
        for code in ("VISUAL", "DIMENSIONAL", "SAMPLING"):
            p = self.PT.create({"name": f"Type Product {code}", "company_id": self.company.id})
            profile = self.WPL.create({
                "product_tmpl_id": p.id,
                "quality_inspection_type": code,
            })
            self.assertEqual(profile.quality_inspection_type, code)

            # Actualización
            profile.write({"quality_inspection_type": False})
            self.assertFalse(profile.quality_inspection_type)

    # ------------------------------------------------------------------
    # TEST-PLM-057: Límites válidos de porcentaje de muestreo
    # ------------------------------------------------------------------

    def test_plm_057_sampling_rate_boundaries_valid(self):
        """PLM-006A-057: 0.0, 50.0 y 100.0 son válidos y persisten."""
        p = self.PT.create({"name": "Boundaries Product", "company_id": self.company.id})
        profile = self.WPL.create({
            "product_tmpl_id": p.id,
            "quality_sampling_rate": 0.0,
        })
        self.assertEqual(profile.quality_sampling_rate, 0.0)

        profile.write({"quality_sampling_rate": 50.0})
        self.assertEqual(profile.quality_sampling_rate, 50.0)

        profile.write({"quality_sampling_rate": 100.0})
        self.assertEqual(profile.quality_sampling_rate, 100.0)

    # ------------------------------------------------------------------
    # TEST-PLM-058: Porcentaje de muestreo negativo rechazado
    # ------------------------------------------------------------------

    def test_plm_058_negative_sampling_rate_rejected(self):
        """PLM-006A-058: DB CHECK rechaza quality_sampling_rate < 0."""
        p = self.PT.create({"name": "Negative Rate Product", "company_id": self.company.id})

        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.WPL.create({
                    "product_tmpl_id": p.id,
                    "quality_sampling_rate": -0.01,
                })

        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.WPL.create({
                    "product_tmpl_id": p.id,
                    "quality_sampling_rate": -10.0,
                })

    # ------------------------------------------------------------------
    # TEST-PLM-059: Porcentaje de muestreo mayor a 100 rechazado y reseteo
    # ------------------------------------------------------------------

    def test_plm_059_sampling_rate_above_100_rejected(self):
        """PLM-006A-059: DB CHECK rechaza quality_sampling_rate > 100; reset a 0.0 es válido."""
        p = self.PT.create({"name": "Above 100 Product", "company_id": self.company.id})

        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.WPL.create({
                    "product_tmpl_id": p.id,
                    "quality_sampling_rate": 100.01,
                })

        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.WPL.create({
                    "product_tmpl_id": p.id,
                    "quality_sampling_rate": 150.0,
                })

        # Configurar valor válido y luego resetear a 0.0
        profile = self.WPL.create({
            "product_tmpl_id": self.product_3.id,
            "quality_sampling_rate": 75.0,
        })
        self.assertEqual(profile.quality_sampling_rate, 75.0)

        profile.write({"quality_sampling_rate": 0.0})
        self.assertEqual(profile.quality_sampling_rate, 0.0)
