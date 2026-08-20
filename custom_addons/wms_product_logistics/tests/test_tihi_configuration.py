from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestTiHiConfiguration(TransactionCase):
    """PLM-003B: Validar configuración Ti-Hi y cantidades derivadas.

    Cubre: contrato de campos (configuración WMS vs derivados Odoo),
    cálculo de cantidades derivadas de Odoo UOM, Ti-Hi no configurado (0, 0),
    rechazo de configuración parcial, rechazo de valores negativos,
    requisito de UOMs de case y pallet, configuración Ti-Hi válida,
    y rechazo de Ti-Hi inconsistente (incluyendo reasignación de UOM).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.WPL = cls.env["wms.product.logistics"]
        cls.PT = cls.env["product.template"]
        cls.UOM = cls.env["uom.uom"]
        cls.company = cls.env.company

        # UOMs jerárquicas en Odoo 19
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")

        cls.uom_case_12 = cls.UOM.create({
            "name": "Case of 12",
            "relative_uom_id": cls.uom_unit.id,
            "relative_factor": 12.0,
        })
        cls.uom_pallet_576 = cls.UOM.create({
            "name": "Pallet of 576",
            "relative_uom_id": cls.uom_unit.id,
            "relative_factor": 576.0,
        })
        cls.uom_pallet_480 = cls.UOM.create({
            "name": "Pallet of 480",
            "relative_uom_id": cls.uom_unit.id,
            "relative_factor": 480.0,
        })

        # Producto con packagings
        cls.product_a = cls.PT.create({
            "name": "Product A",
            "company_id": cls.company.id,
            "uom_id": cls.uom_unit.id,
            "uom_ids": [(6, 0, [
                cls.uom_case_12.id,
                cls.uom_pallet_576.id,
                cls.uom_pallet_480.id,
            ])],
        })

    # ------------------------------------------------------------------
    # TEST-PLM-023: Contrato de campos Ti-Hi y derivados
    # ------------------------------------------------------------------

    def test_plm_023_field_contract(self):
        """PLM-003B-023: contrato de campos de configuración y derivados."""
        WPL = self.env["wms.product.logistics"]

        # WMS-owned configuration: cases_per_layer, layers_per_pallet
        for field_name in ("cases_per_layer", "layers_per_pallet"):
            f = WPL._fields[field_name]
            self.assertEqual(f.type, "integer", f"{field_name} must be Integer")
            self.assertFalse(f.required, f"{field_name} must be optional")

        # Derived quantities from Odoo UOM: readonly, non-stored compute
        for field_name in ("base_qty_per_case", "cases_per_pallet", "base_qty_per_pallet"):
            f = WPL._fields[field_name]
            self.assertEqual(f.type, "float", f"{field_name} must be Float")
            self.assertTrue(f.compute, f"{field_name} must be computed")
            self.assertTrue(f.readonly, f"{field_name} must be readonly")
            self.assertFalse(f.store, f"{field_name} must NOT be stored")

    # ------------------------------------------------------------------
    # TEST-PLM-024: Cantidades derivadas de Odoo UOM
    # ------------------------------------------------------------------

    def test_plm_024_derived_uom_quantities(self):
        """PLM-003B-024: derivación exacta de cantidades base y cajas por pallet."""
        profile = self.WPL.create({
            "product_tmpl_id": self.product_a.id,
            "case_uom_id": self.uom_case_12.id,
            "pallet_uom_id": self.uom_pallet_576.id,
        })
        self.assertEqual(profile.base_qty_per_case, 12.0)
        self.assertEqual(profile.cases_per_pallet, 48.0)
        self.assertEqual(profile.base_qty_per_pallet, 576.0)

    # ------------------------------------------------------------------
    # TEST-PLM-025: Ti-Hi no configurado es válido
    # ------------------------------------------------------------------

    def test_plm_025_no_tihi_is_valid(self):
        """PLM-003B-025: Ti=0 y Hi=0 es válido y mantiene cantidades derivadas."""
        profile = self.WPL.create({
            "product_tmpl_id": self.product_a.id,
            "case_uom_id": self.uom_case_12.id,
            "pallet_uom_id": self.uom_pallet_576.id,
            "cases_per_layer": 0,
            "layers_per_pallet": 0,
        })
        self.assertTrue(profile.id)
        self.assertEqual(profile.cases_per_layer, 0)
        self.assertEqual(profile.layers_per_pallet, 0)
        self.assertEqual(profile.base_qty_per_case, 12.0)
        self.assertEqual(profile.cases_per_pallet, 48.0)
        self.assertEqual(profile.base_qty_per_pallet, 576.0)

    # ------------------------------------------------------------------
    # TEST-PLM-026: Configuración parcial de Ti-Hi rechazada
    # ------------------------------------------------------------------

    def test_plm_026_partial_tihi_rejected(self):
        """PLM-003B-026: Ti > 0 con Hi = 0 o viceversa se rechaza."""
        # Ti > 0, Hi = 0
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "case_uom_id": self.uom_case_12.id,
                "pallet_uom_id": self.uom_pallet_576.id,
                "cases_per_layer": 8,
                "layers_per_pallet": 0,
            })

        # Ti = 0, Hi > 0
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "case_uom_id": self.uom_case_12.id,
                "pallet_uom_id": self.uom_pallet_576.id,
                "cases_per_layer": 0,
                "layers_per_pallet": 6,
            })

    # ------------------------------------------------------------------
    # TEST-PLM-027: Valores negativos de Ti/Hi rechazados
    # ------------------------------------------------------------------

    def test_plm_027_negative_tihi_rejected(self):
        """PLM-003B-027: valores negativos de Ti o Hi se rechazan."""
        # Ti negativo
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "case_uom_id": self.uom_case_12.id,
                "pallet_uom_id": self.uom_pallet_576.id,
                "cases_per_layer": -1,
                "layers_per_pallet": 6,
            })

        # Hi negativo
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "case_uom_id": self.uom_case_12.id,
                "pallet_uom_id": self.uom_pallet_576.id,
                "cases_per_layer": 8,
                "layers_per_pallet": -1,
            })

        # Ambos negativos
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "case_uom_id": self.uom_case_12.id,
                "pallet_uom_id": self.uom_pallet_576.id,
                "cases_per_layer": -8,
                "layers_per_pallet": -6,
            })

    # ------------------------------------------------------------------
    # TEST-PLM-028: Ti-Hi requiere case_uom_id y pallet_uom_id
    # ------------------------------------------------------------------

    def test_plm_028_tihi_requires_case_and_pallet_uom(self):
        """PLM-003B-028: Ti-Hi configurado exige case_uom_id y pallet_uom_id."""
        # Sin case_uom_id
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "pallet_uom_id": self.uom_pallet_576.id,
                "cases_per_layer": 8,
                "layers_per_pallet": 6,
            })

        # Sin pallet_uom_id
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "case_uom_id": self.uom_case_12.id,
                "cases_per_layer": 8,
                "layers_per_pallet": 6,
            })

        # Sin ninguno
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "cases_per_layer": 8,
                "layers_per_pallet": 6,
            })

    # ------------------------------------------------------------------
    # TEST-PLM-029: Configuración Ti-Hi válida
    # ------------------------------------------------------------------

    def test_plm_029_valid_tihi(self):
        """PLM-003B-029: Ti=8, Hi=6 reconcilia con 48 cases/pallet."""
        profile = self.WPL.create({
            "product_tmpl_id": self.product_a.id,
            "case_uom_id": self.uom_case_12.id,
            "pallet_uom_id": self.uom_pallet_576.id,
            "cases_per_layer": 8,
            "layers_per_pallet": 6,
        })
        self.assertTrue(profile.id)
        self.assertEqual(profile.cases_per_layer, 8)
        self.assertEqual(profile.layers_per_pallet, 6)
        self.assertEqual(profile.base_qty_per_case, 12.0)
        self.assertEqual(profile.cases_per_pallet, 48.0)
        self.assertEqual(profile.base_qty_per_pallet, 576.0)

    # ------------------------------------------------------------------
    # TEST-PLM-030: Ti-Hi inconsistente rechazado
    # ------------------------------------------------------------------

    def test_plm_030_inconsistent_tihi_rejected(self):
        """PLM-003B-030: Ti × Hi != cases_per_pallet se rechaza en create y write."""
        # Create inconsistente: 8 × 5 = 40 != 48
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "case_uom_id": self.uom_case_12.id,
                "pallet_uom_id": self.uom_pallet_576.id,
                "cases_per_layer": 8,
                "layers_per_pallet": 5,
            })

        # Create válido inicialmente: 8 × 6 = 48 == 48
        profile = self.WPL.create({
            "product_tmpl_id": self.product_a.id,
            "case_uom_id": self.uom_case_12.id,
            "pallet_uom_id": self.uom_pallet_576.id,
            "cases_per_layer": 8,
            "layers_per_pallet": 6,
        })

        # Reasignar pallet_uom_id a pallet de 480 (40 cajas) -> 8 × 6 != 40 -> reject
        with self.assertRaises(ValidationError):
            profile.write({
                "pallet_uom_id": self.uom_pallet_480.id,
            })

        # Confirmar que sigue intacto
        self.assertEqual(profile.pallet_uom_id, self.uom_pallet_576)

        # Modificar Ti a valor incompatible -> reject
        with self.assertRaises(ValidationError):
            profile.write({
                "cases_per_layer": 7,
            })

        # Reconfigurar coordinadamente a pallet_480 con Ti=8, Hi=5 (8*5 = 40) -> accepted
        profile.write({
            "pallet_uom_id": self.uom_pallet_480.id,
            "cases_per_layer": 8,
            "layers_per_pallet": 5,
        })
        self.assertEqual(profile.pallet_uom_id, self.uom_pallet_480)
        self.assertEqual(profile.cases_per_layer, 8)
        self.assertEqual(profile.layers_per_pallet, 5)
        self.assertEqual(profile.cases_per_pallet, 40.0)
        self.assertEqual(profile.base_qty_per_pallet, 480.0)
