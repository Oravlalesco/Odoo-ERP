from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestNavigationRBAC(TransactionCase):
    """PLM-007B: Validar navegación y exposición RBAC de Product Logistics.

    Cubre:
    - Jerarquía de menús (WMS > Maestros > Perfiles logísticos).
    - Visibilidad y permisos para Operador (R only).
    - Visibilidad y permisos para Supervisor (R only).
    - Visibilidad y permisos para Manager (CRUD).
    - Visibilidad y permisos para Administrador de Sistema (CRUD).
    - Menús ocultos y acceso denegado para usuario interno sin rol WMS.
    - Ausencia de escalación a grupos de Stock (no privilege escalation).
    - Boundary de ownership de menús entre wms_core y wms_product_logistics.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.WPL = cls.env["wms.product.logistics"]
        cls.PT = cls.env["product.template"]
        cls.Users = cls.env["res.users"]
        cls.Menu = cls.env["ir.ui.menu"]

        # Menús
        cls.root_menu = cls.env.ref("wms_core.menu_wms_root")
        cls.master_menu = cls.env.ref("wms_product_logistics.menu_wms_master_data")
        cls.leaf_menu = cls.env.ref("wms_product_logistics.menu_wms_product_logistics")
        cls.action = cls.env.ref("wms_product_logistics.action_wms_product_logistics")

        # Grupos
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_op = cls.env.ref("wms_core.group_wms_operator")
        cls.group_sup = cls.env.ref("wms_core.group_wms_supervisor")
        cls.group_mgr = cls.env.ref("wms_core.group_wms_manager")
        cls.group_system = cls.env.ref("base.group_system")
        cls.group_stock_user = cls.env.ref("stock.group_stock_user")
        cls.group_stock_mgr = cls.env.ref("stock.group_stock_manager")

        # Producto y perfil base para pruebas de permisos
        cls.company = cls.env.company
        cls.test_product = cls.PT.create({
            "name": "Navigation Test Product",
            "company_id": cls.company.id,
        })
        cls.test_profile = cls.WPL.create({
            "product_tmpl_id": cls.test_product.id,
        })

        # Usuarios de prueba por rol
        cls.user_operator = cls.Users.create({
            "name": "Test WMS Operator",
            "login": "test_wms_operator_nav",
            "email": "wms_op_nav@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_op.id])],
        })
        cls.user_supervisor = cls.Users.create({
            "name": "Test WMS Supervisor",
            "login": "test_wms_supervisor_nav",
            "email": "wms_sup_nav@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_sup.id])],
        })
        cls.user_manager = cls.Users.create({
            "name": "Test WMS Manager",
            "login": "test_wms_manager_nav",
            "email": "wms_mgr_nav@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_mgr.id])],
        })
        cls.user_plain_internal = cls.Users.create({
            "name": "Test Plain Internal User",
            "login": "test_plain_internal_nav",
            "email": "plain_internal_nav@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id])],
        })

    # ------------------------------------------------------------------
    # TEST-PLM-068: Menu Hierarchy Contract
    # ------------------------------------------------------------------

    def test_plm_068_menu_hierarchy_contract(self):
        """PLM-007B-068: Jerarquía de 3 niveles, parents, acciones, secuencias y grupos exactos."""
        # 1. Root menu (wms_core)
        self.assertEqual(self.root_menu.name, "WMS")
        self.assertFalse(self.root_menu.parent_id)
        self.assertFalse(self.root_menu.action)
        self.assertEqual(self.root_menu.sequence, 145)

        # 2. Master menu (wms_product_logistics)
        self.assertEqual(self.master_menu.name, "Maestros")
        self.assertEqual(self.master_menu.parent_id, self.root_menu)
        self.assertFalse(self.master_menu.action)
        self.assertEqual(self.master_menu.sequence, 10)
        expected_groups = {self.group_op, self.group_system}
        self.assertEqual(
            set(self.master_menu.group_ids),
            expected_groups,
            "Master menu groups must match exactly Operator and System Admin",
        )

        # 3. Leaf menu (wms_product_logistics)
        self.assertEqual(self.leaf_menu.name, "Perfiles logísticos")
        self.assertEqual(self.leaf_menu.parent_id, self.master_menu)
        self.assertEqual(self.leaf_menu.action, self.action)
        self.assertEqual(self.leaf_menu.sequence, 10)
        self.assertEqual(
            set(self.leaf_menu.group_ids),
            expected_groups,
            "Leaf menu groups must match exactly Operator and System Admin",
        )

    # ------------------------------------------------------------------
    # TEST-PLM-069: Operator Navigation & Read-Only RBAC
    # ------------------------------------------------------------------

    def test_plm_069_operator_navigation_read_only(self):
        """PLM-007B-069: Operador ve los 3 menús WMS pero tiene acceso estrictamente Read-Only al modelo."""
        # A. Navigation visibility
        visible_ids = self.Menu.with_user(self.user_operator)._visible_menu_ids()
        self.assertIn(self.root_menu.id, visible_ids, "Root menu must be visible to Operator")
        self.assertIn(self.master_menu.id, visible_ids, "Master menu must be visible to Operator")
        self.assertIn(self.leaf_menu.id, visible_ids, "Leaf menu must be visible to Operator")

        # B. Model permissions
        wpl_user = self.WPL.with_user(self.user_operator)
        # Read: allowed
        records = wpl_user.search([("id", "=", self.test_profile.id)])
        self.assertEqual(len(records), 1)

        # Create: denied
        prod = self.PT.create({"name": "Op Denied Prod", "company_id": self.company.id})
        with self.assertRaises(AccessError):
            wpl_user.create({"product_tmpl_id": prod.id})

        # Write: denied
        with self.assertRaises(AccessError):
            self.test_profile.with_user(self.user_operator).write({"stackable": True})

        # Unlink: denied
        with self.assertRaises(AccessError):
            self.test_profile.with_user(self.user_operator).unlink()

    # ------------------------------------------------------------------
    # TEST-PLM-070: Supervisor Navigation & Read-Only RBAC
    # ------------------------------------------------------------------

    def test_plm_070_supervisor_navigation_read_only(self):
        """PLM-007B-070: Supervisor ve los 3 menús WMS pero tiene acceso estrictamente Read-Only al modelo."""
        # A. Navigation visibility
        visible_ids = self.Menu.with_user(self.user_supervisor)._visible_menu_ids()
        self.assertIn(self.root_menu.id, visible_ids, "Root menu must be visible to Supervisor")
        self.assertIn(self.master_menu.id, visible_ids, "Master menu must be visible to Supervisor")
        self.assertIn(self.leaf_menu.id, visible_ids, "Leaf menu must be visible to Supervisor")

        # B. Model permissions
        wpl_user = self.WPL.with_user(self.user_supervisor)
        # Read: allowed
        records = wpl_user.search([("id", "=", self.test_profile.id)])
        self.assertEqual(len(records), 1)

        # Create: denied
        prod = self.PT.create({"name": "Sup Denied Prod", "company_id": self.company.id})
        with self.assertRaises(AccessError):
            wpl_user.create({"product_tmpl_id": prod.id})

        # Write: denied
        with self.assertRaises(AccessError):
            self.test_profile.with_user(self.user_supervisor).write({"stackable": True})

        # Unlink: denied
        with self.assertRaises(AccessError):
            self.test_profile.with_user(self.user_supervisor).unlink()

    # ------------------------------------------------------------------
    # TEST-PLM-071: Manager Navigation & Full CRUD RBAC
    # ------------------------------------------------------------------

    def test_plm_071_manager_navigation_crud(self):
        """PLM-007B-071: Manager ve los 3 menús WMS y tiene acceso CRUD completo al modelo."""
        # A. Navigation visibility
        visible_ids = self.Menu.with_user(self.user_manager)._visible_menu_ids()
        self.assertIn(self.root_menu.id, visible_ids, "Root menu must be visible to Manager")
        self.assertIn(self.master_menu.id, visible_ids, "Master menu must be visible to Manager")
        self.assertIn(self.leaf_menu.id, visible_ids, "Leaf menu must be visible to Manager")

        # B. Model permissions
        wpl_user = self.WPL.with_user(self.user_manager)
        # Read: allowed
        records = wpl_user.search([("id", "=", self.test_profile.id)])
        self.assertEqual(len(records), 1)

        # Create: allowed
        prod = self.PT.create({"name": "Mgr Allowed Prod", "company_id": self.company.id})
        new_profile = wpl_user.create({"product_tmpl_id": prod.id, "stackable": True, "max_stack": 2})
        self.assertTrue(new_profile.id)

        # Write: allowed
        new_profile.write({"max_stack": 3})
        self.assertEqual(new_profile.max_stack, 3)

        # Unlink: allowed
        new_profile.unlink()
        self.assertFalse(new_profile.exists())

    # ------------------------------------------------------------------
    # TEST-PLM-072: System Admin Navigation & Full CRUD RBAC
    # ------------------------------------------------------------------

    def test_plm_072_system_admin_navigation_crud(self):
        """PLM-007B-072: System Admin ve los 3 menús WMS y tiene acceso CRUD completo."""
        admin_user = self.env.ref("base.user_admin")

        # A. Navigation visibility
        visible_ids = self.Menu.with_user(admin_user)._visible_menu_ids()
        self.assertIn(self.root_menu.id, visible_ids, "Root menu must be visible to System Admin")
        self.assertIn(self.master_menu.id, visible_ids, "Master menu must be visible to System Admin")
        self.assertIn(self.leaf_menu.id, visible_ids, "Leaf menu must be visible to System Admin")

        # B. Model permissions
        wpl_user = self.WPL.with_user(admin_user)
        # Read: allowed
        records = wpl_user.search([("id", "=", self.test_profile.id)])
        self.assertEqual(len(records), 1)

        # Create: allowed
        prod = self.PT.create({"name": "Admin Allowed Prod", "company_id": self.company.id})
        new_profile = wpl_user.create({"product_tmpl_id": prod.id, "stackable": True, "max_stack": 2})
        self.assertTrue(new_profile.id)

        # Write: allowed
        new_profile.write({"max_stack": 4})
        self.assertEqual(new_profile.max_stack, 4)

        # Unlink: allowed
        new_profile.unlink()
        self.assertFalse(new_profile.exists())

    # ------------------------------------------------------------------
    # TEST-PLM-073: Plain Internal User Hidden & Access Denied
    # ------------------------------------------------------------------

    def test_plm_073_plain_internal_user_hidden(self):
        """PLM-007B-073: Usuario interno sin grupos WMS tiene los 3 menús ocultos y lectura denegada."""
        # A. Navigation: Menús WMS deben estar ocultos
        visible_ids = self.Menu.with_user(self.user_plain_internal)._visible_menu_ids()
        self.assertNotIn(self.root_menu.id, visible_ids, "Root menu must be hidden from plain internal user")
        self.assertNotIn(self.master_menu.id, visible_ids, "Master menu must be hidden from plain internal user")
        self.assertNotIn(self.leaf_menu.id, visible_ids, "Leaf menu must be hidden from plain internal user")

        # B. Model: Lectura denegada
        wpl_user = self.WPL.with_user(self.user_plain_internal)
        with self.assertRaises(AccessError):
            wpl_user.search([("id", "=", self.test_profile.id)])

    # ------------------------------------------------------------------
    # TEST-PLM-074: No Stock Group Escalation
    # ------------------------------------------------------------------

    def test_plm_074_no_stock_group_escalation(self):
        """PLM-007B-074: Grupos WMS no implican grupos de Stock y usuarios WMS limpios no adquieren privilegios de Stock."""
        # 1. Grafo de grupos (directo y transitivo)
        def _get_all_implied(group):
            implied = set(group.implied_ids)
            for g in list(implied):
                implied.update(_get_all_implied(g))
            return implied

        op_implied = _get_all_implied(self.group_op)
        sup_implied = _get_all_implied(self.group_sup)
        mgr_implied = _get_all_implied(self.group_mgr)

        for name, implied_set in [
            ("Operator", op_implied),
            ("Supervisor", sup_implied),
            ("Manager", mgr_implied),
        ]:
            self.assertNotIn(
                self.group_stock_user,
                implied_set,
                f"WMS {name} group must not imply stock.group_stock_user",
            )
            self.assertNotIn(
                self.group_stock_mgr,
                implied_set,
                f"WMS {name} group must not imply stock.group_stock_manager",
            )

        # 2. Comprobación en usuarios limpios
        self.assertTrue(self.user_manager.has_group("wms_core.group_wms_manager"))
        self.assertTrue(self.user_manager.has_group("wms_core.group_wms_supervisor"))
        self.assertTrue(self.user_manager.has_group("wms_core.group_wms_operator"))

        self.assertFalse(
            self.user_manager.has_group("stock.group_stock_user"),
            "WMS Manager must not have stock.group_stock_user",
        )
        self.assertFalse(
            self.user_manager.has_group("stock.group_stock_manager"),
            "WMS Manager must not have stock.group_stock_manager",
        )

    # ------------------------------------------------------------------
    # TEST-PLM-075: Navigation Ownership Boundary
    # ------------------------------------------------------------------

    def test_plm_075_navigation_ownership_boundary(self):
        """PLM-007B-075: wms_core posee exactamente 1 ir.ui.menu y wms_product_logistics posee exactamente 2 ir.ui.menu."""
        IMD = self.env["ir.model.data"]

        # wms_core: exactamente 1 menú propio (menu_wms_root)
        core_menus = IMD.search([
            ("module", "=", "wms_core"),
            ("model", "=", "ir.ui.menu"),
        ])
        self.assertEqual(len(core_menus), 1, "wms_core must own exactly 1 ir.ui.menu")
        self.assertEqual(core_menus.name, "menu_wms_root")

        # wms_product_logistics: exactamente 2 menús propios (menu_wms_master_data, menu_wms_product_logistics)
        plm_menus = IMD.search([
            ("module", "=", "wms_product_logistics"),
            ("model", "=", "ir.ui.menu"),
        ])
        self.assertEqual(len(plm_menus), 2, "wms_product_logistics must own exactly 2 ir.ui.menu records")
        self.assertEqual(
            set(plm_menus.mapped("name")),
            {"menu_wms_master_data", "menu_wms_product_logistics"},
            "wms_product_logistics menu XMLIDs mismatch",
        )

        # Leaf action binding
        self.assertEqual(
            self.leaf_menu.action,
            self.action,
            "Leaf menu action must point to action_wms_product_logistics",
        )
