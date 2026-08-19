from lxml import etree

from odoo.tests.common import TransactionCase


class TestStockLocationZoneUI(TransactionCase):
    """WM-007: Validar la UI de asignación de zona en stock.location.

    Estos tests inspeccionan el arch XML compilado de la vista
    heredada para verificar estructura, grupos, visibilidad,
    domain, options y no-regresión de wms_location_role.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.view = cls.env.ref(
            "wms_warehouse_master.view_location_form_wms_role"
        )
        cls.arch = etree.fromstring(cls.view.arch)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_fields(self, field_name):
        """Retorna todos los elementos <field name='field_name'> en el arch."""
        return self.arch.xpath(f"//field[@name='{field_name}']")

    # ------------------------------------------------------------------
    # TEST-ZONE-UI-LOC-001: View metadata
    # ------------------------------------------------------------------

    def test_zone_ui_loc_01_view_metadata(self):
        """TEST-ZONE-UI-LOC-001: vista hereda stock.view_location_form
        y contiene wms_zone_id."""
        self.assertEqual(self.view.model, "stock.location")
        parent = self.env.ref("stock.view_location_form")
        self.assertEqual(self.view.inherit_id, parent)
        zone_fields = self._find_fields("wms_zone_id")
        self.assertTrue(
            len(zone_fields) > 0,
            "wms_zone_id debe estar presente en la vista heredada.",
        )

    # ------------------------------------------------------------------
    # TEST-ZONE-UI-LOC-002: warehouse_id helper invisible
    # ------------------------------------------------------------------

    def test_zone_ui_loc_02_warehouse_helper_invisible(self):
        """TEST-ZONE-UI-LOC-002: warehouse_id existe como helper invisible."""
        wh_fields = self._find_fields("warehouse_id")
        self.assertEqual(
            len(wh_fields), 1,
            "warehouse_id debe tener exactamente 1 aparición.",
        )
        wh = wh_fields[0]
        self.assertEqual(wh.get("invisible"), "1")

    # ------------------------------------------------------------------
    # TEST-ZONE-UI-LOC-003: Exactly 2 occurrences of wms_zone_id
    # ------------------------------------------------------------------

    def test_zone_ui_loc_03_zone_dual_occurrence(self):
        """TEST-ZONE-UI-LOC-003: exactamente 2 apariciones de wms_zone_id."""
        zone_fields = self._find_fields("wms_zone_id")
        self.assertEqual(
            len(zone_fields), 2,
            "wms_zone_id debe tener exactamente 2 apariciones "
            "(editable + readonly).",
        )

    # ------------------------------------------------------------------
    # TEST-ZONE-UI-LOC-004: Editable occurrence groups
    # ------------------------------------------------------------------

    def test_zone_ui_loc_04_editable_occurrence_groups(self):
        """TEST-ZONE-UI-LOC-004: occurrence editable tiene groups correcto
        y no tiene readonly='1'."""
        zone_fields = self._find_fields("wms_zone_id")
        editable = [f for f in zone_fields if f.get("readonly") != "1"]
        self.assertEqual(
            len(editable), 1,
            "Debe haber exactamente 1 occurrence editable de wms_zone_id.",
        )
        groups = editable[0].get("groups", "")
        self.assertIn("wms_core.group_wms_manager", groups)
        self.assertIn("base.group_system", groups)

    # ------------------------------------------------------------------
    # TEST-ZONE-UI-LOC-005: Readonly occurrence groups
    # ------------------------------------------------------------------

    def test_zone_ui_loc_05_readonly_occurrence_groups(self):
        """TEST-ZONE-UI-LOC-005: occurrence readonly tiene readonly='1'
        y groups correcto."""
        zone_fields = self._find_fields("wms_zone_id")
        readonly = [f for f in zone_fields if f.get("readonly") == "1"]
        self.assertEqual(
            len(readonly), 1,
            "Debe haber exactamente 1 occurrence readonly de wms_zone_id.",
        )
        groups = readonly[0].get("groups", "")
        self.assertIn("base.group_user", groups)
        self.assertIn("!wms_core.group_wms_manager", groups)
        self.assertIn("!base.group_system", groups)

    # ------------------------------------------------------------------
    # TEST-ZONE-UI-LOC-006: Both occurrences visibility
    # ------------------------------------------------------------------

    def test_zone_ui_loc_06_both_invisible_expressions(self):
        """TEST-ZONE-UI-LOC-006: ambas apariciones tienen invisible que
        cubre usage, warehouse_id y company_id."""
        zone_fields = self._find_fields("wms_zone_id")
        for field in zone_fields:
            inv = field.get("invisible", "")
            # Normalize whitespace for comparison
            inv_normalized = " ".join(inv.split())
            self.assertIn("usage", inv_normalized,
                          "invisible debe verificar usage")
            self.assertIn("warehouse_id", inv_normalized,
                          "invisible debe verificar warehouse_id")
            self.assertIn("company_id", inv_normalized,
                          "invisible debe verificar company_id")

    # ------------------------------------------------------------------
    # TEST-ZONE-UI-LOC-007: Both occurrences domain and options
    # ------------------------------------------------------------------

    def test_zone_ui_loc_07_domain_and_options(self):
        """TEST-ZONE-UI-LOC-007: ambas apariciones tienen domain con
        warehouse_id + company_id, y no_create=True."""
        zone_fields = self._find_fields("wms_zone_id")
        for field in zone_fields:
            domain = field.get("domain", "")
            domain_normalized = " ".join(domain.split())
            self.assertIn("warehouse_id", domain_normalized,
                          "domain debe filtrar por warehouse_id")
            self.assertIn("company_id", domain_normalized,
                          "domain debe filtrar por company_id")
            options = field.get("options", "")
            self.assertIn("no_create", options,
                          "options debe incluir no_create")

    # ------------------------------------------------------------------
    # TEST-ZONE-UI-LOC-008: wms_location_role regression
    # ------------------------------------------------------------------

    def test_zone_ui_loc_08_role_regression(self):
        """TEST-ZONE-UI-LOC-008: wms_location_role mantiene patrón WM-003."""
        role_fields = self._find_fields("wms_location_role")
        self.assertEqual(
            len(role_fields), 2,
            "wms_location_role debe tener exactamente 2 apariciones.",
        )
        # Editable: Manager/System, no readonly
        editable = [f for f in role_fields if f.get("readonly") != "1"]
        self.assertEqual(len(editable), 1)
        groups_edit = editable[0].get("groups", "")
        self.assertIn("wms_core.group_wms_manager", groups_edit)
        self.assertIn("base.group_system", groups_edit)
        inv_edit = editable[0].get("invisible", "")
        self.assertIn("usage", inv_edit)

        # Readonly: base.group_user exclusions
        readonly = [f for f in role_fields if f.get("readonly") == "1"]
        self.assertEqual(len(readonly), 1)
        groups_ro = readonly[0].get("groups", "")
        self.assertIn("base.group_user", groups_ro)
        self.assertIn("!wms_core.group_wms_manager", groups_ro)
        self.assertIn("!base.group_system", groups_ro)
        inv_ro = readonly[0].get("invisible", "")
        self.assertIn("usage", inv_ro)
