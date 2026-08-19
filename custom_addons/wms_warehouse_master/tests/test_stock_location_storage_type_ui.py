from lxml import etree

from odoo.tests.common import TransactionCase


class TestStockLocationStorageTypeUI(TransactionCase):
    """WM-014: Validar la UI de wms_storage_type_id en stock.location.

    Inspecciona la vista heredada, grupos, domain, invisibility
    y protege regresión de Role/Zone existente.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_expr(value):
        """Normalizar whitespace de una expresión XML."""
        return " ".join(value.split())

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.view = cls.env.ref(
            "wms_warehouse_master.view_location_form_wms_role"
        )
        cls.arch = etree.fromstring(cls.view.arch)

    # ------------------------------------------------------------------
    # ST-LOC-UI-001: Inherited view
    # ------------------------------------------------------------------

    def test_st_loc_ui_01_inherited_view(self):
        """ST-LOC-UI-001: inherited view exists y apunta a stock.location."""
        self.assertTrue(self.view)
        self.assertEqual(self.view.model, "stock.location")
        parent = self.env.ref("stock.view_location_form")
        self.assertEqual(self.view.inherit_id, parent)

    # ------------------------------------------------------------------
    # ST-LOC-UI-002: Two occurrences
    # ------------------------------------------------------------------

    def test_st_loc_ui_02_two_occurrences(self):
        """ST-LOC-UI-002: exactamente 2 ocurrencias de wms_storage_type_id."""
        st_fields = [
            f for f in self.arch.iter("field")
            if f.get("name") == "wms_storage_type_id"
        ]
        self.assertEqual(len(st_fields), 2)

    # ------------------------------------------------------------------
    # ST-LOC-UI-003: Editable occurrence
    # ------------------------------------------------------------------

    def test_st_loc_ui_03_editable_occurrence(self):
        """ST-LOC-UI-003: ocurrencia editable con grupos exactos."""
        st_fields = [
            f for f in self.arch.iter("field")
            if f.get("name") == "wms_storage_type_id"
        ]
        # Editable = la que NO tiene readonly
        editable = [f for f in st_fields if not f.get("readonly")]
        self.assertEqual(len(editable), 1)
        ed = editable[0]
        # Groups exact
        groups_str = ed.get("groups", "")
        groups_set = {g.strip() for g in groups_str.split(",") if g.strip()}
        self.assertEqual(
            groups_set,
            {"wms_core.group_wms_manager", "base.group_system"},
        )
        # No readonly attribute
        self.assertIsNone(ed.get("readonly"))

    # ------------------------------------------------------------------
    # ST-LOC-UI-004: Readonly occurrence
    # ------------------------------------------------------------------

    def test_st_loc_ui_04_readonly_occurrence(self):
        """ST-LOC-UI-004: ocurrencia readonly con grupos exactos."""
        st_fields = [
            f for f in self.arch.iter("field")
            if f.get("name") == "wms_storage_type_id"
        ]
        readonly = [f for f in st_fields if f.get("readonly") == "1"]
        self.assertEqual(len(readonly), 1)
        ro = readonly[0]
        groups_str = ro.get("groups", "")
        groups_set = {g.strip() for g in groups_str.split(",") if g.strip()}
        self.assertEqual(
            groups_set,
            {
                "base.group_user",
                "!wms_core.group_wms_manager",
                "!base.group_system",
            },
        )

    # ------------------------------------------------------------------
    # ST-LOC-UI-005: Exact domain/options
    # ------------------------------------------------------------------

    def test_st_loc_ui_05_domain_and_options(self):
        """ST-LOC-UI-005: domain y options exactos en ambas ocurrencias."""
        st_fields = [
            f for f in self.arch.iter("field")
            if f.get("name") == "wms_storage_type_id"
        ]
        for field in st_fields:
            domain = self._normalize_expr(field.get("domain", ""))
            self.assertEqual(
                domain,
                "[('company_id', '=', company_id)]",
            )
            # No warehouse in domain
            self.assertNotIn("warehouse_id", domain)

            options = self._normalize_expr(field.get("options", ""))
            self.assertEqual(
                options,
                "{'no_create': True}",
            )

    # ------------------------------------------------------------------
    # ST-LOC-UI-006: Exact invisibility
    # ------------------------------------------------------------------

    def test_st_loc_ui_06_exact_invisibility(self):
        """ST-LOC-UI-006: invisible exacto sin warehouse/zone/role."""
        st_fields = [
            f for f in self.arch.iter("field")
            if f.get("name") == "wms_storage_type_id"
        ]
        for field in st_fields:
            inv = self._normalize_expr(field.get("invisible", ""))
            self.assertEqual(
                inv,
                "usage != 'internal' or not company_id",
            )
            # Must NOT reference these
            self.assertNotIn("warehouse_id", inv)
            self.assertNotIn("wms_zone_id", inv)
            self.assertNotIn("wms_location_role", inv)

    # ------------------------------------------------------------------
    # ST-LOC-UI-007: Role/Zone regression
    # ------------------------------------------------------------------

    def test_st_loc_ui_07_role_zone_regression(self):
        """ST-LOC-UI-007: Role/Zone fields y warehouse helper preservados."""
        # Count occurrences
        role_fields = [
            f for f in self.arch.iter("field")
            if f.get("name") == "wms_location_role"
        ]
        self.assertEqual(len(role_fields), 2)

        zone_fields = [
            f for f in self.arch.iter("field")
            if f.get("name") == "wms_zone_id"
        ]
        self.assertEqual(len(zone_fields), 2)

        wh_fields = [
            f for f in self.arch.iter("field")
            if f.get("name") == "warehouse_id"
        ]
        self.assertEqual(len(wh_fields), 1)

        # Zone domain preserved
        for zf in zone_fields:
            domain = self._normalize_expr(zf.get("domain", ""))
            self.assertEqual(
                domain,
                "[('warehouse_id', '=', warehouse_id), "
                "('company_id', '=', company_id)]",
            )

        # Zone invisible preserved
        for zf in zone_fields:
            inv = self._normalize_expr(zf.get("invisible", ""))
            self.assertEqual(
                inv,
                "usage != 'internal' or not warehouse_id or not company_id",
            )

        # Zone options preserved
        for zf in zone_fields:
            options = self._normalize_expr(zf.get("options", ""))
            self.assertEqual(
                options,
                "{'no_create': True}",
            )

    # ------------------------------------------------------------------
    # ST-LOC-UI-008: No forbidden UI expansion
    # ------------------------------------------------------------------

    def test_st_loc_ui_08_no_forbidden_expansion(self):
        """ST-LOC-UI-008: no action/menu/list/search nuevos para ST."""
        IrModel = self.env["ir.model.data"]

        # No dedicated ST-LOC action
        st_action = IrModel.search([
            ("module", "=", "wms_warehouse_master"),
            ("model", "=", "ir.actions.act_window"),
            ("name", "ilike", "storage_type"),
            ("name", "ilike", "location"),
        ])
        self.assertFalse(st_action)

        # No dedicated ST-LOC menu
        st_menu = IrModel.search([
            ("module", "=", "wms_warehouse_master"),
            ("model", "=", "ir.ui.menu"),
            ("name", "ilike", "storage_type"),
            ("name", "ilike", "location"),
        ])
        self.assertFalse(st_menu)

        # No stock.location list view from this module
        loc_list = IrModel.search([
            ("module", "=", "wms_warehouse_master"),
            ("model", "=", "ir.ui.view"),
            ("name", "ilike", "location"),
            ("name", "ilike", "list"),
        ])
        self.assertFalse(loc_list)

        # No stock.location search view from this module
        loc_search = IrModel.search([
            ("module", "=", "wms_warehouse_master"),
            ("model", "=", "ir.ui.view"),
            ("name", "ilike", "location"),
            ("name", "ilike", "search"),
        ])
        self.assertFalse(loc_search)
