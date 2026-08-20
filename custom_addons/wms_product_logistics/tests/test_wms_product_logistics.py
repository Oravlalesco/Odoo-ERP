from psycopg2 import IntegrityError

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestWmsProductLogistics(TransactionCase):
    """PLM-002: Validar modelo wms.product.logistics.

    Cubre: contrato del modelo, 1:1 constraint, lifecycle
    (cascade, archive, reactivate, delete profile), RBAC
    y multi-company con productos globales.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.WPL = cls.env["wms.product.logistics"]
        cls.ProductTemplate = cls.env["product.template"]

        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({
            "name": "PLM Test Company B",
        })

        # Products
        cls.product_a = cls.ProductTemplate.create({
            "name": "Product A",
            "company_id": cls.company_a.id,
        })
        cls.product_global = cls.ProductTemplate.create({
            "name": "Product Global",
            "company_id": False,
        })

        # Grupos
        wms_operator_group = cls.env.ref("wms_core.group_wms_operator")
        wms_supervisor_group = cls.env.ref("wms_core.group_wms_supervisor")
        wms_manager_group = cls.env.ref("wms_core.group_wms_manager")

        cls.operator_user = cls.env["res.users"].create({
            "name": "PLM Operator",
            "login": "test_plm_operator",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [
                (6, 0, [wms_operator_group.id]),
            ],
        })
        cls.supervisor_user = cls.env["res.users"].create({
            "name": "PLM Supervisor",
            "login": "test_plm_supervisor",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [
                (6, 0, [wms_supervisor_group.id]),
            ],
        })
        cls.manager_user = cls.env["res.users"].create({
            "name": "PLM Manager",
            "login": "test_plm_manager",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [
                (6, 0, [wms_manager_group.id]),
            ],
        })
        cls.admin_user = cls.env.ref("base.user_admin")

        # Reference profile
        cls.profile_a = cls.WPL.create({
            "product_tmpl_id": cls.product_a.id,
        })

    # ------------------------------------------------------------------
    # PLM-002-001: Model contract
    # ------------------------------------------------------------------

    def test_plm_001_model_contract(self):
        """PLM-002-001: modelo registrado con campos y metadatos correctos."""
        WPL = self.env["wms.product.logistics"]
        self.assertEqual(WPL._name, "wms.product.logistics")
        self.assertEqual(
            WPL._description, "Perfil logístico WMS de producto",
        )
        self.assertEqual(WPL._rec_name, "product_tmpl_id")

        # product_tmpl_id
        f = WPL._fields["product_tmpl_id"]
        self.assertEqual(f.comodel_name, "product.template")
        self.assertTrue(f.required)
        self.assertTrue(f.index)
        self.assertEqual(f.ondelete, "cascade")

        # company_id — related to product_tmpl_id.company_id, stored, readonly
        co_f = WPL._fields["company_id"]
        self.assertEqual(co_f.comodel_name, "res.company")
        self.assertTrue(co_f.store)
        self.assertTrue(co_f.readonly)
        self.assertTrue(co_f.index)
        self.assertTrue(co_f.related)
        self.assertEqual(
            co_f.related.split("."),
            ["product_tmpl_id", "company_id"],
        )

        # active — related to product_tmpl_id.active, stored, readonly
        active_f = WPL._fields["active"]
        self.assertTrue(active_f.store)
        self.assertTrue(active_f.readonly)
        self.assertTrue(active_f.related)
        self.assertEqual(
            active_f.related.split("."),
            ["product_tmpl_id", "active"],
        )

    # ------------------------------------------------------------------
    # PLM-002-002: Minimal create
    # ------------------------------------------------------------------

    def test_plm_002_minimal_create(self):
        """PLM-002-002: crear perfil con defaults correctos."""
        product = self.ProductTemplate.create({
            "name": "Minimal Create Test",
            "company_id": self.company_a.id,
        })
        profile = self.WPL.create({
            "product_tmpl_id": product.id,
        })
        self.assertEqual(profile.company_id, self.company_a)
        self.assertTrue(profile.active)
        # rec_name based on product
        self.assertIn("Minimal Create Test", profile.display_name)

    # ------------------------------------------------------------------
    # PLM-002-003: Duplicate rejected at DB
    # ------------------------------------------------------------------

    def test_plm_003_duplicate_rejected(self):
        """PLM-002-003: segundo perfil para el mismo product → IntegrityError."""
        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.WPL.create({
                    "product_tmpl_id": self.product_a.id,
                })

    # ------------------------------------------------------------------
    # PLM-002-004: Different products allowed
    # ------------------------------------------------------------------

    def test_plm_004_different_products_allowed(self):
        """PLM-002-004: diferentes productos pueden tener perfil."""
        product_2 = self.ProductTemplate.create({
            "name": "Product 2",
            "company_id": self.company_a.id,
        })
        profile_2 = self.WPL.create({
            "product_tmpl_id": product_2.id,
        })
        self.assertTrue(profile_2.id)
        self.assertNotEqual(profile_2.id, self.profile_a.id)

    # ------------------------------------------------------------------
    # PLM-002-005: Product delete → cascade profile
    # ------------------------------------------------------------------

    def test_plm_005_product_delete_cascades(self):
        """PLM-002-005: eliminar producto elimina perfil (cascade)."""
        product = self.ProductTemplate.create({
            "name": "Cascade Test",
            "company_id": self.company_a.id,
        })
        profile = self.WPL.create({
            "product_tmpl_id": product.id,
        })
        profile_id = profile.id
        product.unlink()
        self.assertFalse(self.WPL.browse(profile_id).exists())

    # ------------------------------------------------------------------
    # PLM-002-006: Profile delete → product survives
    # ------------------------------------------------------------------

    def test_plm_006_profile_delete_product_survives(self):
        """PLM-002-006: eliminar perfil no elimina producto."""
        product = self.ProductTemplate.create({
            "name": "Survive Test",
            "company_id": self.company_a.id,
        })
        profile = self.WPL.create({
            "product_tmpl_id": product.id,
        })
        profile.unlink()
        self.assertTrue(product.exists())
        self.assertEqual(product.name, "Survive Test")

    # ------------------------------------------------------------------
    # PLM-002-007: Archive / reactivate lifecycle
    # ------------------------------------------------------------------

    def test_plm_007_archive_reactivate_lifecycle(self):
        """PLM-002-007: archive/reactivate con active_test completo."""
        product = self.ProductTemplate.create({
            "name": "Lifecycle Test",
            "company_id": self.company_a.id,
        })
        profile = self.WPL.create({
            "product_tmpl_id": product.id,
        })
        self.assertTrue(profile.active)

        # Archive product
        product.write({"active": False})
        profile.invalidate_recordset()
        self.assertFalse(profile.active)

        # Profile disappears from normal search (active_test=True)
        visible = self.WPL.search([("id", "=", profile.id)])
        self.assertFalse(visible)

        # Profile still exists with active_test=False
        hidden = self.WPL.with_context(active_test=False).search([
            ("id", "=", profile.id),
        ])
        self.assertEqual(hidden, profile)

        # Reactivate product
        product.write({"active": True})
        profile.invalidate_recordset()
        self.assertTrue(profile.active)

        # Profile visible again in normal search
        visible_again = self.WPL.search([("id", "=", profile.id)])
        self.assertEqual(visible_again, profile)

    # ------------------------------------------------------------------
    # PLM-002-008: Operator read-only
    # ------------------------------------------------------------------

    def test_plm_008_operator_read_only(self):
        """PLM-002-008: Operator puede leer, create/write/unlink denegados."""
        profiles = self.WPL.with_user(self.operator_user).search([])
        self.assertTrue(len(profiles) > 0)

        # Create denied
        with self.assertRaises(AccessError):
            self.WPL.with_user(self.operator_user).create({
                "product_tmpl_id": self.product_global.id,
            })
        # Write denied
        product_wr = self.ProductTemplate.create({
            "name": "Op Write Test",
            "company_id": self.company_a.id,
        })
        profile_wr = self.WPL.create({
            "product_tmpl_id": product_wr.id,
        })
        with self.assertRaises(AccessError):
            profile_wr.with_user(self.operator_user).write({
                "product_tmpl_id": self.product_global.id,
            })
        # Unlink denied
        with self.assertRaises(AccessError):
            profile_wr.with_user(self.operator_user).unlink()

    # ------------------------------------------------------------------
    # PLM-002-009: Supervisor read-only
    # ------------------------------------------------------------------

    def test_plm_009_supervisor_read_only(self):
        """PLM-002-009: Supervisor puede leer, create/write/unlink denegados."""
        profiles = self.WPL.with_user(self.supervisor_user).search([])
        self.assertTrue(len(profiles) > 0)

        # Create denied
        with self.assertRaises(AccessError):
            self.WPL.with_user(self.supervisor_user).create({
                "product_tmpl_id": self.product_global.id,
            })
        # Write denied
        product_wr = self.ProductTemplate.create({
            "name": "Sup Write Test",
            "company_id": self.company_a.id,
        })
        profile_wr = self.WPL.create({
            "product_tmpl_id": product_wr.id,
        })
        with self.assertRaises(AccessError):
            profile_wr.with_user(self.supervisor_user).write({
                "product_tmpl_id": self.product_global.id,
            })
        # Unlink denied
        with self.assertRaises(AccessError):
            profile_wr.with_user(self.supervisor_user).unlink()

    # ------------------------------------------------------------------
    # PLM-002-010: Manager CRUD
    # ------------------------------------------------------------------

    def test_plm_010_manager_crud(self):
        """PLM-002-010: Manager puede CRUD completo incluyendo write."""
        product = self.ProductTemplate.create({
            "name": "Manager CRUD",
            "company_id": self.company_a.id,
        })
        product_2 = self.ProductTemplate.create({
            "name": "Manager CRUD Target",
            "company_id": self.company_a.id,
        })
        # Create
        profile = self.WPL.with_user(self.manager_user).create({
            "product_tmpl_id": product.id,
        })
        self.assertTrue(profile.id)
        # Read
        profile.with_user(self.manager_user).read(["product_tmpl_id"])
        # Update
        profile.with_user(self.manager_user).write({
            "product_tmpl_id": product_2.id,
        })
        self.assertEqual(profile.product_tmpl_id, product_2)
        # Delete
        profile.with_user(self.manager_user).unlink()
        self.assertFalse(profile.exists())

    # ------------------------------------------------------------------
    # PLM-002-011: System Admin CRUD
    # ------------------------------------------------------------------

    def test_plm_011_system_admin_crud(self):
        """PLM-002-011: System Admin puede CRUD completo incluyendo write."""
        product = self.ProductTemplate.create({
            "name": "Admin CRUD",
            "company_id": self.company_a.id,
        })
        product_2 = self.ProductTemplate.create({
            "name": "Admin CRUD Target",
            "company_id": self.company_a.id,
        })
        # Create
        profile = self.WPL.with_user(self.admin_user).create({
            "product_tmpl_id": product.id,
        })
        self.assertTrue(profile.id)
        # Read
        profile.with_user(self.admin_user).read(["product_tmpl_id"])
        # Update
        profile.with_user(self.admin_user).write({
            "product_tmpl_id": product_2.id,
        })
        self.assertEqual(profile.product_tmpl_id, product_2)
        # Delete
        profile.with_user(self.admin_user).unlink()
        self.assertFalse(profile.exists())

    # ------------------------------------------------------------------
    # PLM-002-012: Multi-company + global product
    # ------------------------------------------------------------------

    def test_plm_012_multi_company_and_global_product(self):
        """PLM-002-012: aislamiento multi-company + producto global visible."""
        # Profile for global product
        profile_g = self.WPL.create({
            "product_tmpl_id": self.product_global.id,
        })
        self.assertFalse(profile_g.company_id)

        # Product in Company B (with profile)
        product_b = self.ProductTemplate.with_company(
            self.company_b,
        ).create({
            "name": "Product B Only",
            "company_id": self.company_b.id,
        })
        profile_b = self.WPL.with_company(self.company_b).create({
            "product_tmpl_id": product_b.id,
        })

        # Second product in Company B WITHOUT profile (for create test)
        product_b2 = self.ProductTemplate.with_company(
            self.company_b,
        ).create({
            "name": "Product B2 No Profile",
            "company_id": self.company_b.id,
        })

        # User A only — sees A + global, NOT B
        user_a = self.env["res.users"].create({
            "name": "PLM User A Only",
            "login": "test_plm_user_a_only",
            "company_id": self.company_a.id,
            "company_ids": [(6, 0, [self.company_a.id])],
            "group_ids": [
                (6, 0, [
                    self.env.ref("wms_core.group_wms_manager").id,
                ]),
            ],
        })
        visible = self.WPL.with_user(user_a).search([])
        self.assertIn(self.profile_a, visible)
        self.assertIn(profile_g, visible)
        self.assertNotIn(profile_b, visible)

        # Direct read of profile_b by User A → AccessError
        with self.assertRaises(AccessError):
            self.WPL.with_user(user_a).browse(profile_b.id).read(
                ["product_tmpl_id"],
            )

        # Manager A creating profile on B2 product → AccessError
        with self.assertRaises(AccessError):
            self.WPL.with_user(user_a).create({
                "product_tmpl_id": product_b2.id,
            })

        # User A+B — sees all
        user_ab = self.env["res.users"].create({
            "name": "PLM User A+B",
            "login": "test_plm_user_ab",
            "company_id": self.company_a.id,
            "company_ids": [(6, 0, [
                self.company_a.id, self.company_b.id,
            ])],
            "group_ids": [
                (6, 0, [
                    self.env.ref("wms_core.group_wms_manager").id,
                ]),
            ],
        })
        visible_ab = self.WPL.with_user(user_ab).search([])
        self.assertIn(self.profile_a, visible_ab)
        self.assertIn(profile_g, visible_ab)
        self.assertIn(profile_b, visible_ab)
