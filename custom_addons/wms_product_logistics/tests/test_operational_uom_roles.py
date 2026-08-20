from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestOperationalUomRoles(TransactionCase):
    """PLM-003A: Validar roles UOM operacionales en wms.product.logistics.

    Cubre: contrato de campos, perfiles sin UOM, pick con base/packaging,
    case/pallet sólo packaging, rechazos de UOM ajena/base,
    y reasignación de product_tmpl_id con validación cruzada.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.WPL = cls.env["wms.product.logistics"]
        cls.PT = cls.env["product.template"]
        cls.UOM = cls.env["uom.uom"]
        cls.company = cls.env.company

        # UOM references — Odoo 19 uses relative_uom_id + relative_factor
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")

        cls.uom_box = cls.UOM.create({
            "name": "Box of 12",
            "relative_uom_id": cls.uom_unit.id,
            "relative_factor": 12.0,
        })
        cls.uom_case = cls.UOM.create({
            "name": "Case of 24",
            "relative_uom_id": cls.uom_unit.id,
            "relative_factor": 24.0,
        })
        cls.uom_pallet = cls.UOM.create({
            "name": "Pallet of 576",
            "relative_uom_id": cls.uom_unit.id,
            "relative_factor": 576.0,
        })

        # UOM ajena (no asociada al producto)
        cls.uom_alien = cls.UOM.create({
            "name": "Alien UOM",
            "relative_uom_id": cls.uom_unit.id,
            "relative_factor": 999.0,
        })

        # Producto con packagings
        cls.product_a = cls.PT.create({
            "name": "Product A",
            "company_id": cls.company.id,
            "uom_id": cls.uom_unit.id,
            "uom_ids": [(6, 0, [
                cls.uom_box.id,
                cls.uom_case.id,
                cls.uom_pallet.id,
            ])],
        })

        # Producto B con packagings distintos
        cls.uom_box_b = cls.UOM.create({
            "name": "Box B",
            "relative_uom_id": cls.uom_unit.id,
            "relative_factor": 6.0,
        })
        cls.product_b = cls.PT.create({
            "name": "Product B",
            "company_id": cls.company.id,
            "uom_id": cls.uom_unit.id,
            "uom_ids": [(6, 0, [cls.uom_box_b.id])],
        })

    # ------------------------------------------------------------------
    # TEST-PLM-015: Contrato de los 3 campos
    # ------------------------------------------------------------------

    def test_plm_015_field_contract(self):
        """PLM-003A-015: comodel uom.uom, optional, ondelete=restrict."""
        WPL = self.env["wms.product.logistics"]

        for field_name in ("pick_uom_id", "case_uom_id", "pallet_uom_id"):
            f = WPL._fields[field_name]
            self.assertEqual(
                f.comodel_name, "uom.uom",
                f"{field_name} must point to uom.uom",
            )
            self.assertFalse(
                f.required,
                f"{field_name} must be optional",
            )
            self.assertEqual(
                f.ondelete, "restrict",
                f"{field_name} must use ondelete=restrict",
            )

    # ------------------------------------------------------------------
    # TEST-PLM-016: Perfil sin UOM sigue válido
    # ------------------------------------------------------------------

    def test_plm_016_profile_without_uom_valid(self):
        """PLM-003A-016: perfil sin UOM operacionales es válido."""
        profile = self.WPL.create({
            "product_tmpl_id": self.product_a.id,
        })
        self.assertTrue(profile.id)
        self.assertFalse(profile.pick_uom_id)
        self.assertFalse(profile.case_uom_id)
        self.assertFalse(profile.pallet_uom_id)

    # ------------------------------------------------------------------
    # TEST-PLM-017: pick_uom_id acepta UOM base
    # ------------------------------------------------------------------

    def test_plm_017_pick_accepts_base_uom(self):
        """PLM-003A-017: pick_uom_id acepta product.uom_id base."""
        profile = self.WPL.create({
            "product_tmpl_id": self.product_a.id,
            "pick_uom_id": self.uom_unit.id,
        })
        self.assertEqual(profile.pick_uom_id, self.uom_unit)

    # ------------------------------------------------------------------
    # TEST-PLM-018: pick/case/pallet aceptan uom_ids válidas
    # ------------------------------------------------------------------

    def test_plm_018_all_accept_valid_packaging_uoms(self):
        """PLM-003A-018: pick/case/pallet aceptan uom_ids válidas."""
        profile = self.WPL.create({
            "product_tmpl_id": self.product_a.id,
            "pick_uom_id": self.uom_box.id,
            "case_uom_id": self.uom_case.id,
            "pallet_uom_id": self.uom_pallet.id,
        })
        self.assertEqual(profile.pick_uom_id, self.uom_box)
        self.assertEqual(profile.case_uom_id, self.uom_case)
        self.assertEqual(profile.pallet_uom_id, self.uom_pallet)

    # ------------------------------------------------------------------
    # TEST-PLM-019: pick_uom_id rechaza UOM ajena
    # ------------------------------------------------------------------

    def test_plm_019_pick_rejects_alien_uom(self):
        """PLM-003A-019: pick_uom_id rechaza UOM ajena al producto."""
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "pick_uom_id": self.uom_alien.id,
            })

    # ------------------------------------------------------------------
    # TEST-PLM-020: case_uom_id rechaza UOM base y ajena
    # ------------------------------------------------------------------

    def test_plm_020_case_rejects_base_and_alien(self):
        """PLM-003A-020: case_uom_id rechaza UOM base y UOM ajena."""
        # Base UOM rejected
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "case_uom_id": self.uom_unit.id,
            })

        # Alien UOM rejected
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "case_uom_id": self.uom_alien.id,
            })

    # ------------------------------------------------------------------
    # TEST-PLM-021: pallet_uom_id rechaza UOM base y ajena
    # ------------------------------------------------------------------

    def test_plm_021_pallet_rejects_base_and_alien(self):
        """PLM-003A-021: pallet_uom_id rechaza UOM base y UOM ajena."""
        # Base UOM rejected
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "pallet_uom_id": self.uom_unit.id,
            })

        # Alien UOM rejected
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_a.id,
                "pallet_uom_id": self.uom_alien.id,
            })

    # ------------------------------------------------------------------
    # TEST-PLM-022: Reasignar product_tmpl_id invalida UOM
    # ------------------------------------------------------------------

    def test_plm_022_reassign_product_rejects_invalid_uom(self):
        """PLM-003A-022: reasignar product_tmpl_id rechaza UOM inválida."""
        # Perfil de Product A con case válido
        profile = self.WPL.create({
            "product_tmpl_id": self.product_a.id,
            "case_uom_id": self.uom_case.id,
        })

        # Reasignar a Product B: uom_case no pertenece a B → reject
        with self.assertRaises(ValidationError):
            profile.write({
                "product_tmpl_id": self.product_b.id,
            })

        # Confirm profile unchanged
        self.assertEqual(profile.product_tmpl_id, self.product_a)

        # Reasignar clearing the UOM simultaneously → accepted
        profile.write({
            "product_tmpl_id": self.product_b.id,
            "case_uom_id": False,
        })
        self.assertEqual(profile.product_tmpl_id, self.product_b)
        self.assertFalse(profile.case_uom_id)
