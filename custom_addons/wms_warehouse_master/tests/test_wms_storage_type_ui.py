from lxml import etree

from odoo.tests.common import TransactionCase


class TestWmsStorageTypeUI(TransactionCase):
    """WM-012: Validar la UI administrativa de wms.storage.type.

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
    # TEST-ST-UI-001: List view
    # ------------------------------------------------------------------

    def test_st_ui_01_list_view_exists(self):
        """TEST-ST-UI-001: list view existe y apunta a wms.storage.type."""
        view = self.env.ref(
            "wms_warehouse_master.view_wms_storage_type_list"
        )
        self.assertTrue(view)
        self.assertEqual(view.model, "wms.storage.type")
        self.assertEqual(view.type, "list")

    # ------------------------------------------------------------------
    # TEST-ST-UI-002: Form view
    # ------------------------------------------------------------------

    def test_st_ui_02_form_view_exists(self):
        """TEST-ST-UI-002: form view existe y apunta a wms.storage.type."""
        view = self.env.ref(
            "wms_warehouse_master.view_wms_storage_type_form"
        )
        self.assertTrue(view)
        self.assertEqual(view.model, "wms.storage.type")
        self.assertEqual(view.type, "form")

    # ------------------------------------------------------------------
    # TEST-ST-UI-003: Search view
    # ------------------------------------------------------------------

    def test_st_ui_03_search_view_exists(self):
        """TEST-ST-UI-003: search view existe y apunta a wms.storage.type."""
        view = self.env.ref(
            "wms_warehouse_master.view_wms_storage_type_search"
        )
        self.assertTrue(view)
        self.assertEqual(view.model, "wms.storage.type")
        self.assertEqual(view.type, "search")

    # ------------------------------------------------------------------
    # TEST-ST-UI-004: Action
    # ------------------------------------------------------------------

    def test_st_ui_04_action(self):
        """TEST-ST-UI-004: action con res_model, view_mode y search_view
        exactos."""
        action = self.env.ref(
            "wms_warehouse_master.action_wms_storage_type"
        )
        self.assertEqual(action.res_model, "wms.storage.type")
        self.assertEqual(action.view_mode, "list,form")
        search_view = self.env.ref(
            "wms_warehouse_master.view_wms_storage_type_search"
        )
        self.assertEqual(action.search_view_id, search_view)

    # ------------------------------------------------------------------
    # TEST-ST-UI-005: Menu
    # ------------------------------------------------------------------

    def test_st_ui_05_menu(self):
        """TEST-ST-UI-005: menú parent, action y sequence exactos."""
        menu = self.env.ref(
            "wms_warehouse_master.menu_wms_storage_type"
        )
        parent = self.env.ref("stock.menu_warehouse_config")
        self.assertEqual(menu.parent_id, parent)
        action = self.env.ref(
            "wms_warehouse_master.action_wms_storage_type"
        )
        self.assertEqual(menu.action, action)
        self.assertEqual(menu.sequence, 52)

    # ------------------------------------------------------------------
    # TEST-ST-UI-006: Menu groups exact
    # ------------------------------------------------------------------

    def test_st_ui_06_menu_groups_exact(self):
        """TEST-ST-UI-006: menú groups exactos Manager/System."""
        menu = self.env.ref(
            "wms_warehouse_master.menu_wms_storage_type"
        )
        expected = {
            self.env.ref("wms_core.group_wms_manager"),
            self.env.ref("base.group_system"),
        }
        self.assertEqual(set(menu.group_ids), expected)

    # ------------------------------------------------------------------
    # TEST-ST-UI-007: List/Form fields and attributes exact
    # ------------------------------------------------------------------

    def test_st_ui_07_view_fields_and_attributes(self):
        """TEST-ST-UI-007: list/form fields y atributos exactos."""
        # --- List ---
        list_view = self.env.ref(
            "wms_warehouse_master.view_wms_storage_type_list"
        )
        list_arch = etree.fromstring(list_view.arch)
        list_fields = {f.get("name") for f in list_arch.iter("field")}
        self.assertEqual(
            list_fields,
            {
                "sequence",
                "code",
                "name",
                "company_id",
                "active",
            },
        )
        # No inline editing
        self.assertIsNone(list_arch.get("editable"))

        # sequence widget="handle"
        seq_field = [
            f for f in list_arch.iter("field")
            if f.get("name") == "sequence"
        ][0]
        self.assertEqual(seq_field.get("widget"), "handle")

        # active optional="hide"
        active_field = [
            f for f in list_arch.iter("field")
            if f.get("name") == "active"
        ][0]
        self.assertEqual(active_field.get("optional"), "hide")

        # --- Form ---
        form_view = self.env.ref(
            "wms_warehouse_master.view_wms_storage_type_form"
        )
        form_arch = etree.fromstring(form_view.arch)
        form_fields_map = {
            f.get("name"): f for f in form_arch.iter("field")
        }
        self.assertEqual(
            set(form_fields_map),
            {
                "name",
                "code",
                "company_id",
                "sequence",
                "active",
            },
        )

        # company_id editable (no readonly attribute)
        self.assertIsNone(
            form_fields_map["company_id"].get("readonly"),
        )
        # company_id no custom domain
        self.assertIsNone(
            form_fields_map["company_id"].get("domain"),
        )

    # ------------------------------------------------------------------
    # TEST-ST-UI-008: Search structure exact
    # ------------------------------------------------------------------

    def test_st_ui_08_search_structure_exact(self):
        """TEST-ST-UI-008: search fields, filter y group-by exactos."""
        search_view = self.env.ref(
            "wms_warehouse_master.view_wms_storage_type_search"
        )
        search_arch = etree.fromstring(search_view.arch)

        # Search fields — exact set
        search_fields = {
            f.get("name") for f in search_arch.iter("field")
        }
        self.assertEqual(
            search_fields,
            {
                "name",
                "code",
                "company_id",
            },
        )

        # Filters — exact set
        filters = {
            f.get("name"): f for f in search_arch.iter("filter")
        }
        self.assertEqual(
            set(filters),
            {
                "inactive",
                "group_company",
            },
        )

        # Archived filter domain
        self.assertEqual(
            self._normalize_expr(filters["inactive"].get("domain", "")),
            "[('active', '=', False)]",
        )

        # Group By Company
        self.assertEqual(
            self._normalize_expr(
                filters["group_company"].get("context", "")
            ),
            "{'group_by': 'company_id'}",
        )
