from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestHuTypeRestrictions(TransactionCase):
    """PLM-005B: Validar restricciones de tipos de HU (Handling Units).

    Cubre:
    - Contrato de campos (Many2many y Many2one a stock.package.type, ondelete=restrict, opcionales).
    - Allowlist vacío significa sin restricción.
    - Persistencia de tipos permitidos.
    - Semántica del tipo HU por defecto (opcional, en allowlist cuando no está vacío).
    - Rechazo de default fuera de allowlist y soporte de escrituras coordinadas.
    - Reglas multi-compañía para productos de compañía específica (global + misma compañía).
    - Reglas multi-compañía para productos globales (solo tipos globales).
    - Revalidación ante reasignación de producto y transiciones coordinadas.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.WPL = cls.env["wms.product.logistics"]
        cls.PT = cls.env["product.template"]
        cls.SPT = cls.env["stock.package.type"]
        cls.Company = cls.env["res.company"]

        cls.company_a = cls.env.company
        cls.company_b = cls.Company.create({
            "name": "WMS Test Company B",
        })

        # Package types
        cls.pkg_type_global_1 = cls.SPT.create({
            "name": "Global Pallet Type 1",
            "company_id": False,
        })
        cls.pkg_type_global_2 = cls.SPT.create({
            "name": "Global Box Type 2",
            "company_id": False,
        })
        cls.pkg_type_global_3 = cls.SPT.create({
            "name": "Global Tote Type 3",
            "company_id": False,
        })

        cls.pkg_type_comp_a = cls.SPT.create({
            "name": "Company A Specific Box",
            "company_id": cls.company_a.id,
        })
        cls.pkg_type_comp_b = cls.SPT.create({
            "name": "Company B Specific Box",
            "company_id": cls.company_b.id,
        })

        # Products
        cls.product_comp_a = cls.PT.create({
            "name": "Company A Product",
            "company_id": cls.company_a.id,
        })
        cls.product_comp_b = cls.PT.create({
            "name": "Company B Product",
            "company_id": cls.company_b.id,
        })
        cls.product_global = cls.PT.create({
            "name": "Global Product",
            "company_id": False,
        })

    # ------------------------------------------------------------------
    # TEST-PLM-045: Contrato de campos
    # ------------------------------------------------------------------

    def test_plm_045_field_contract(self):
        """PLM-005B-045: M2M/M2O a stock.package.type, opcionales, ondelete=restrict, sin defaults."""
        WPL = self.env["wms.product.logistics"]

        # allowed_hu_type_ids
        f_allowed = WPL._fields["allowed_hu_type_ids"]
        self.assertEqual(f_allowed.type, "many2many", "allowed_hu_type_ids must be Many2many")
        self.assertEqual(f_allowed.comodel_name, "stock.package.type", "comodel must be stock.package.type")
        self.assertFalse(f_allowed.required, "allowed_hu_type_ids must be optional")
        self.assertFalse(f_allowed.default, "allowed_hu_type_ids must not have default")

        # default_hu_type_id
        f_default = WPL._fields["default_hu_type_id"]
        self.assertEqual(f_default.type, "many2one", "default_hu_type_id must be Many2one")
        self.assertEqual(f_default.comodel_name, "stock.package.type", "comodel must be stock.package.type")
        self.assertFalse(f_default.required, "default_hu_type_id must be optional")
        self.assertEqual(f_default.ondelete, "restrict", "default_hu_type_id must have ondelete='restrict'")
        self.assertFalse(f_default.default, "default_hu_type_id must not have default")

    # ------------------------------------------------------------------
    # TEST-PLM-046: Allowlist vacío significa sin restricción
    # ------------------------------------------------------------------

    def test_plm_046_empty_allowlist_is_unrestricted(self):
        """PLM-005B-046: allowed_hu_type_ids vacío y default_hu_type_id=False es válido."""
        p = self.PT.create({"name": "Unrestricted HU Product", "company_id": self.company_a.id})
        profile = self.WPL.create({
            "product_tmpl_id": p.id,
        })
        self.assertTrue(profile.id)
        self.assertFalse(profile.allowed_hu_type_ids)
        self.assertFalse(profile.default_hu_type_id)

    # ------------------------------------------------------------------
    # TEST-PLM-047: Persistencia de tipos permitidos
    # ------------------------------------------------------------------

    def test_plm_047_allowed_hu_types_persist(self):
        """PLM-005B-047: varios tipos permitidos persisten correctamente."""
        p = self.PT.create({"name": "Multi HU Product", "company_id": self.company_a.id})
        profile = self.WPL.create({
            "product_tmpl_id": p.id,
            "allowed_hu_type_ids": [(6, 0, [self.pkg_type_global_1.id, self.pkg_type_global_2.id])],
        })
        self.assertEqual(len(profile.allowed_hu_type_ids), 2)
        self.assertIn(self.pkg_type_global_1, profile.allowed_hu_type_ids)
        self.assertIn(self.pkg_type_global_2, profile.allowed_hu_type_ids)

    # ------------------------------------------------------------------
    # TEST-PLM-048: Semántica del default
    # ------------------------------------------------------------------

    def test_plm_048_default_semantics(self):
        """PLM-005B-048: default válido con allowlist vacío y default miembro de allowlist no vacío."""
        # Caso 1: allowlist vacío, default configurado
        p1 = self.PT.create({"name": "Default Only Product", "company_id": self.company_a.id})
        profile1 = self.WPL.create({
            "product_tmpl_id": p1.id,
            "default_hu_type_id": self.pkg_type_global_1.id,
        })
        self.assertEqual(profile1.default_hu_type_id, self.pkg_type_global_1)
        self.assertFalse(profile1.allowed_hu_type_ids)

        # Caso 2: allowlist con tipos, default es uno de los permitidos
        p2 = self.PT.create({"name": "Allowed + Default Product", "company_id": self.company_a.id})
        profile2 = self.WPL.create({
            "product_tmpl_id": p2.id,
            "allowed_hu_type_ids": [(6, 0, [self.pkg_type_global_1.id, self.pkg_type_global_2.id])],
            "default_hu_type_id": self.pkg_type_global_2.id,
        })
        self.assertEqual(profile2.default_hu_type_id, self.pkg_type_global_2)
        self.assertIn(profile2.default_hu_type_id, profile2.allowed_hu_type_ids)

    # ------------------------------------------------------------------
    # TEST-PLM-049: Default fuera de allowlist rechazado
    # ------------------------------------------------------------------

    def test_plm_049_default_outside_allowlist_rejected(self):
        """PLM-005B-049: default fuera de allowlist rechazado; escritura coordinada válida aceptada."""
        p = self.PT.create({"name": "Strict Allowlist Product", "company_id": self.company_a.id})

        # Creación con default fuera de allowlist
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": p.id,
                "allowed_hu_type_ids": [(6, 0, [self.pkg_type_global_1.id])],
                "default_hu_type_id": self.pkg_type_global_2.id,
            })

        # Creación válida
        profile = self.WPL.create({
            "product_tmpl_id": p.id,
            "allowed_hu_type_ids": [(6, 0, [self.pkg_type_global_1.id])],
            "default_hu_type_id": self.pkg_type_global_1.id,
        })

        # Modificación que desalinea default
        with self.assertRaises(ValidationError):
            profile.write({
                "default_hu_type_id": self.pkg_type_global_2.id,
            })

        # Modificación coordinada válida
        profile.write({
            "allowed_hu_type_ids": [(4, self.pkg_type_global_2.id)],
            "default_hu_type_id": self.pkg_type_global_2.id,
        })
        self.assertEqual(profile.default_hu_type_id, self.pkg_type_global_2)
        self.assertIn(self.pkg_type_global_2, profile.allowed_hu_type_ids)

    # ------------------------------------------------------------------
    # TEST-PLM-050: Alcance de producto con compañía específica
    # ------------------------------------------------------------------

    def test_plm_050_company_specific_scope(self):
        """PLM-005B-050: perfil company A acepta global + company A; rechaza company B."""
        p_a = self.PT.create({"name": "Comp A Product Scope", "company_id": self.company_a.id})

        # Válido: global y company A
        profile = self.WPL.create({
            "product_tmpl_id": p_a.id,
            "allowed_hu_type_ids": [(6, 0, [self.pkg_type_global_1.id, self.pkg_type_comp_a.id])],
            "default_hu_type_id": self.pkg_type_comp_a.id,
        })
        self.assertTrue(profile.id)

        # Inválido: allowed contiene tipo de company B
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": self.product_comp_a.id,
                "allowed_hu_type_ids": [(6, 0, [self.pkg_type_comp_b.id])],
            })

        # Inválido: default es tipo de company B
        p_a2 = self.PT.create({"name": "Comp A Product Scope 2", "company_id": self.company_a.id})
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": p_a2.id,
                "default_hu_type_id": self.pkg_type_comp_b.id,
            })

    # ------------------------------------------------------------------
    # TEST-PLM-051: Alcance de producto global
    # ------------------------------------------------------------------

    def test_plm_051_global_product_scope(self):
        """PLM-005B-051: perfil global acepta tipos globales y rechaza company-specific."""
        p_glob = self.PT.create({"name": "Global Product Scope", "company_id": False})

        # Válido: tipos globales
        profile = self.WPL.create({
            "product_tmpl_id": p_glob.id,
            "allowed_hu_type_ids": [(6, 0, [self.pkg_type_global_1.id, self.pkg_type_global_2.id])],
            "default_hu_type_id": self.pkg_type_global_1.id,
        })
        self.assertTrue(profile.id)

        # Inválido: allowed contiene tipo específico de compañía
        p_glob2 = self.PT.create({"name": "Global Product Scope 2", "company_id": False})
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": p_glob2.id,
                "allowed_hu_type_ids": [(6, 0, [self.pkg_type_comp_a.id])],
            })

        # Inválido: default es tipo específico de compañía
        p_glob3 = self.PT.create({"name": "Global Product Scope 3", "company_id": False})
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": p_glob3.id,
                "default_hu_type_id": self.pkg_type_comp_a.id,
            })

    # ------------------------------------------------------------------
    # TEST-PLM-052: Revalidación al reasignar producto
    # ------------------------------------------------------------------

    def test_plm_052_product_reassignment_revalidates(self):
        """PLM-005B-052: cambio de product_tmpl_id revalida restricciones HU."""
        p_a = self.PT.create({"name": "Reassign Product A", "company_id": self.company_a.id})
        p_b = self.PT.create({"name": "Reassign Product B", "company_id": self.company_b.id})

        profile = self.WPL.create({
            "product_tmpl_id": p_a.id,
            "allowed_hu_type_ids": [(6, 0, [self.pkg_type_comp_a.id])],
            "default_hu_type_id": self.pkg_type_comp_a.id,
        })

        # Reasignar a producto de company B sin cambiar tipos HU falla
        with self.assertRaises(ValidationError):
            profile.write({
                "product_tmpl_id": p_b.id,
            })

        # Transición coordinada a company B succeeds
        profile.write({
            "product_tmpl_id": p_b.id,
            "allowed_hu_type_ids": [(6, 0, [self.pkg_type_comp_b.id])],
            "default_hu_type_id": self.pkg_type_comp_b.id,
        })
        self.assertEqual(profile.product_tmpl_id, p_b)
        self.assertEqual(profile.default_hu_type_id, self.pkg_type_comp_b)

        # Transición limpiando allowlist y default también succeeds
        p_a2 = self.PT.create({"name": "Reassign Product A2", "company_id": self.company_a.id})
        profile.write({
            "product_tmpl_id": p_a2.id,
            "allowed_hu_type_ids": [(5, 0, 0)],
            "default_hu_type_id": False,
        })
        self.assertEqual(profile.product_tmpl_id, p_a2)
        self.assertFalse(profile.allowed_hu_type_ids)
        self.assertFalse(profile.default_hu_type_id)
