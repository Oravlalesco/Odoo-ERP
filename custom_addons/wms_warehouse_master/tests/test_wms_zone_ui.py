from lxml import etree

from odoo.tests.common import TransactionCase


class TestWmsZoneUI(TransactionCase):
    """Verificar la UI administrativa de wms.zone.

    WM-005: Estos tests validan que las vistas, acción y menú
    existen con la configuración correcta, y que la seguridad
    subyacente no fue alterada.
    """

    # ------------------------------------------------------------------
    # Vistas
    # ------------------------------------------------------------------

    def test_zone_ui_01_list_view_exists(self):
        """TEST-ZONE-UI-001: list view existe y apunta a wms.zone."""
        view = self.env.ref("wms_warehouse_master.view_wms_zone_list")
        self.assertTrue(view)
        self.assertEqual(view.model, "wms.zone")
        self.assertEqual(view.type, "list")

    def test_zone_ui_02_form_view_exists(self):
        """TEST-ZONE-UI-002: form view existe y apunta a wms.zone."""
        view = self.env.ref("wms_warehouse_master.view_wms_zone_form")
        self.assertTrue(view)
        self.assertEqual(view.model, "wms.zone")
        self.assertEqual(view.type, "form")

    def test_zone_ui_03_search_view_exists(self):
        """TEST-ZONE-UI-003: search view existe y apunta a wms.zone."""
        view = self.env.ref("wms_warehouse_master.view_wms_zone_search")
        self.assertTrue(view)
        self.assertEqual(view.model, "wms.zone")
        self.assertEqual(view.type, "search")

    # ------------------------------------------------------------------
    # Acción
    # ------------------------------------------------------------------

    def test_zone_ui_04_action_exists(self):
        """TEST-ZONE-UI-004: action apunta a wms.zone con list,form."""
        action = self.env.ref("wms_warehouse_master.action_wms_zone")
        self.assertTrue(action)
        self.assertEqual(action.res_model, "wms.zone")
        self.assertIn("list", action.view_mode)
        self.assertIn("form", action.view_mode)
        search_view = self.env.ref(
            "wms_warehouse_master.view_wms_zone_search"
        )
        self.assertEqual(action.search_view_id, search_view)

    # ------------------------------------------------------------------
    # Menú
    # ------------------------------------------------------------------

    def test_zone_ui_05_menu_exists(self):
        """TEST-ZONE-UI-005: menú bajo stock.menu_warehouse_config."""
        menu = self.env.ref("wms_warehouse_master.menu_wms_zone")
        self.assertTrue(menu)
        parent = self.env.ref("stock.menu_warehouse_config")
        self.assertEqual(menu.parent_id, parent)
        action = self.env.ref("wms_warehouse_master.action_wms_zone")
        self.assertEqual(menu.action, action)

    def test_zone_ui_06_menu_groups_correct(self):
        """TEST-ZONE-UI-006: menú concedido sólo a Manager WMS y System Admin."""
        menu = self.env.ref("wms_warehouse_master.menu_wms_zone")
        group_manager = self.env.ref("wms_core.group_wms_manager")
        group_system = self.env.ref("base.group_system")
        group_operator = self.env.ref("wms_core.group_wms_operator")
        group_supervisor = self.env.ref("wms_core.group_wms_supervisor")
        group_stock_mgr = self.env.ref("stock.group_stock_manager")

        menu_groups = menu.group_ids
        self.assertIn(group_manager, menu_groups)
        self.assertIn(group_system, menu_groups)
        self.assertNotIn(group_operator, menu_groups)
        self.assertNotIn(group_supervisor, menu_groups)
        self.assertNotIn(group_stock_mgr, menu_groups)

    # ------------------------------------------------------------------
    # Campos en vistas
    # ------------------------------------------------------------------

    def test_zone_ui_07_views_contain_expected_fields(self):
        """TEST-ZONE-UI-007: vistas contienen los campos mínimos."""
        # List view
        list_view = self.env.ref("wms_warehouse_master.view_wms_zone_list")
        list_arch = etree.fromstring(list_view.arch)
        list_fields = {f.get("name") for f in list_arch.iter("field")}
        for field in ("sequence", "code", "name", "warehouse_id",
                      "company_id", "active"):
            self.assertIn(
                field, list_fields,
                f"Campo '{field}' no encontrado en list view",
            )

        # Form view
        form_view = self.env.ref("wms_warehouse_master.view_wms_zone_form")
        form_arch = etree.fromstring(form_view.arch)
        form_fields = {f.get("name") for f in form_arch.iter("field")}
        for field in ("name", "code", "warehouse_id", "company_id",
                      "sequence", "active"):
            self.assertIn(
                field, form_fields,
                f"Campo '{field}' no encontrado en form view",
            )

        # Search view
        search_view = self.env.ref(
            "wms_warehouse_master.view_wms_zone_search"
        )
        search_arch = etree.fromstring(search_view.arch)
        search_fields = {f.get("name") for f in search_arch.iter("field")}
        for field in ("name", "code", "warehouse_id", "company_id"):
            self.assertIn(
                field, search_fields,
                f"Campo '{field}' no encontrado en search view",
            )

    # ------------------------------------------------------------------
    # Regresión de seguridad
    # ------------------------------------------------------------------

    def test_zone_ui_08_security_regression(self):
        """TEST-ZONE-UI-008: ACL y record rule no fueron alteradas."""
        # ACL: Operator read-only
        acl_op = self.env["ir.model.access"].search([
            ("model_id.model", "=", "wms.zone"),
            ("group_id", "=",
             self.env.ref("wms_core.group_wms_operator").id),
        ], limit=1)
        self.assertTrue(acl_op)
        self.assertTrue(acl_op.perm_read)
        self.assertFalse(acl_op.perm_write)
        self.assertFalse(acl_op.perm_create)
        self.assertFalse(acl_op.perm_unlink)

        # ACL: Manager CRUD
        acl_mgr = self.env["ir.model.access"].search([
            ("model_id.model", "=", "wms.zone"),
            ("group_id", "=",
             self.env.ref("wms_core.group_wms_manager").id),
        ], limit=1)
        self.assertTrue(acl_mgr)
        self.assertTrue(acl_mgr.perm_read)
        self.assertTrue(acl_mgr.perm_write)
        self.assertTrue(acl_mgr.perm_create)
        self.assertTrue(acl_mgr.perm_unlink)

        # ACL: System Admin CRUD
        acl_sys = self.env["ir.model.access"].search([
            ("model_id.model", "=", "wms.zone"),
            ("group_id", "=",
             self.env.ref("base.group_system").id),
        ], limit=1)
        self.assertTrue(acl_sys)
        self.assertTrue(acl_sys.perm_read)
        self.assertTrue(acl_sys.perm_write)
        self.assertTrue(acl_sys.perm_create)
        self.assertTrue(acl_sys.perm_unlink)

        # Record rule: global multi-company
        rule = self.env.ref(
            "wms_warehouse_master.wms_zone_company_rule"
        )
        self.assertTrue(rule)
        self.assertTrue(rule["global"])
        self.assertIn("company_ids", rule.domain_force)
