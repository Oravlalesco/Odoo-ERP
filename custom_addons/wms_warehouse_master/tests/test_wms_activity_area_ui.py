from lxml import etree

from odoo.tests.common import TransactionCase


class TestWmsActivityAreaUI(TransactionCase):
    """WM-009: Validar la UI administrativa de wms.activity.area.

    Estos tests inspeccionan vistas, acción, menú y estructura XML
    para verificar configuración correcta sin alterar modelo ni seguridad.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_expr(value):
        """Normalizar whitespace de una expresión XML."""
        return " ".join(value.split())

    # ------------------------------------------------------------------
    # TEST-AA-UI-001: List view
    # ------------------------------------------------------------------

    def test_aa_ui_01_list_view_exists(self):
        """TEST-AA-UI-001: list view existe y apunta a wms.activity.area."""
        view = self.env.ref(
            "wms_warehouse_master.view_wms_activity_area_list"
        )
        self.assertTrue(view)
        self.assertEqual(view.model, "wms.activity.area")
        self.assertEqual(view.type, "list")

    # ------------------------------------------------------------------
    # TEST-AA-UI-002: Form view
    # ------------------------------------------------------------------

    def test_aa_ui_02_form_view_exists(self):
        """TEST-AA-UI-002: form view existe y apunta a wms.activity.area."""
        view = self.env.ref(
            "wms_warehouse_master.view_wms_activity_area_form"
        )
        self.assertTrue(view)
        self.assertEqual(view.model, "wms.activity.area")
        self.assertEqual(view.type, "form")

    # ------------------------------------------------------------------
    # TEST-AA-UI-003: Search view
    # ------------------------------------------------------------------

    def test_aa_ui_03_search_view_exists(self):
        """TEST-AA-UI-003: search view existe y apunta a wms.activity.area."""
        view = self.env.ref(
            "wms_warehouse_master.view_wms_activity_area_search"
        )
        self.assertTrue(view)
        self.assertEqual(view.model, "wms.activity.area")
        self.assertEqual(view.type, "search")

    # ------------------------------------------------------------------
    # TEST-AA-UI-004: Action
    # ------------------------------------------------------------------

    def test_aa_ui_04_action(self):
        """TEST-AA-UI-004: action con res_model, view_mode y search_view
        exactos."""
        action = self.env.ref(
            "wms_warehouse_master.action_wms_activity_area"
        )
        self.assertEqual(action.res_model, "wms.activity.area")
        self.assertEqual(action.view_mode, "list,form")
        search_view = self.env.ref(
            "wms_warehouse_master.view_wms_activity_area_search"
        )
        self.assertEqual(action.search_view_id, search_view)

    # ------------------------------------------------------------------
    # TEST-AA-UI-005: Menu
    # ------------------------------------------------------------------

    def test_aa_ui_05_menu(self):
        """TEST-AA-UI-005: menú parent, action y sequence exactos."""
        menu = self.env.ref(
            "wms_warehouse_master.menu_wms_activity_area"
        )
        parent = self.env.ref("stock.menu_warehouse_config")
        self.assertEqual(menu.parent_id, parent)
        action = self.env.ref(
            "wms_warehouse_master.action_wms_activity_area"
        )
        self.assertEqual(menu.action, action)
        self.assertEqual(menu.sequence, 51)

    # ------------------------------------------------------------------
    # TEST-AA-UI-006: Menu groups exact
    # ------------------------------------------------------------------

    def test_aa_ui_06_menu_groups_exact(self):
        """TEST-AA-UI-006: menú groups exactos Manager/System."""
        menu = self.env.ref(
            "wms_warehouse_master.menu_wms_activity_area"
        )
        expected = {
            self.env.ref("wms_core.group_wms_manager"),
            self.env.ref("base.group_system"),
        }
        self.assertEqual(set(menu.group_ids), expected)

    # ------------------------------------------------------------------
    # TEST-AA-UI-007: View fields and attributes
    # ------------------------------------------------------------------

    def test_aa_ui_07_view_fields_and_attributes(self):
        """TEST-AA-UI-007: list/form fields y atributos exactos."""
        # --- List ---
        list_view = self.env.ref(
            "wms_warehouse_master.view_wms_activity_area_list"
        )
        list_arch = etree.fromstring(list_view.arch)
        list_fields = {f.get("name") for f in list_arch.iter("field")}
        for field in ("sequence", "code", "name", "zone_id",
                      "warehouse_id", "company_id", "active"):
            self.assertIn(
                field, list_fields,
                f"Campo '{field}' no encontrado en list view",
            )

        # --- Form ---
        form_view = self.env.ref(
            "wms_warehouse_master.view_wms_activity_area_form"
        )
        form_arch = etree.fromstring(form_view.arch)
        form_fields_map = {
            f.get("name"): f for f in form_arch.iter("field")
        }
        for field in ("name", "code", "zone_id", "warehouse_id",
                      "company_id", "sequence", "active"):
            self.assertIn(
                field, form_fields_map,
                f"Campo '{field}' no encontrado en form view",
            )

        # warehouse_id readonly="1"
        self.assertEqual(
            form_fields_map["warehouse_id"].get("readonly"), "1",
        )
        # company_id readonly="1"
        self.assertEqual(
            form_fields_map["company_id"].get("readonly"), "1",
        )
        # zone_id options exact
        self.assertEqual(
            form_fields_map["zone_id"].get("options"),
            "{'no_create': True}",
        )
        # zone_id NO custom domain
        self.assertIsNone(
            form_fields_map["zone_id"].get("domain"),
        )

    # ------------------------------------------------------------------
    # TEST-AA-UI-008: Search structure exact
    # ------------------------------------------------------------------

    def test_aa_ui_08_search_structure_exact(self):
        """TEST-AA-UI-008: search fields, filter archived y group-by exactos."""
        search_view = self.env.ref(
            "wms_warehouse_master.view_wms_activity_area_search"
        )
        search_arch = etree.fromstring(search_view.arch)

        # Search fields
        search_fields = {
            f.get("name") for f in search_arch.iter("field")
        }
        for field in ("name", "code", "zone_id", "warehouse_id",
                      "company_id"):
            self.assertIn(
                field, search_fields,
                f"Campo '{field}' no encontrado en search view",
            )

        # Filters
        filters = {
            f.get("name"): f for f in search_arch.iter("filter")
        }

        # Archived filter
        self.assertIn("inactive", filters)
        self.assertEqual(
            self._normalize_expr(filters["inactive"].get("domain", "")),
            "[('active', '=', False)]",
        )

        # Group By Zone
        self.assertIn("group_zone", filters)
        self.assertEqual(
            self._normalize_expr(
                filters["group_zone"].get("context", "")
            ),
            "{'group_by': 'zone_id'}",
        )

        # Group By Warehouse
        self.assertIn("group_warehouse", filters)
        self.assertEqual(
            self._normalize_expr(
                filters["group_warehouse"].get("context", "")
            ),
            "{'group_by': 'warehouse_id'}",
        )

        # Group By Company
        self.assertIn("group_company", filters)
        self.assertEqual(
            self._normalize_expr(
                filters["group_company"].get("context", "")
            ),
            "{'group_by': 'company_id'}",
        )
