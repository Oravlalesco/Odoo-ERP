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

    @staticmethod
    def _parse_groups(field):
        """Extraer grupos como set normalizado."""
        return {g.strip() for g in field.get("groups", "").split(",") if g.strip()}

    @staticmethod
    def _normalize_expr(value):
        """Normalizar whitespace de una expresión XML."""
        return " ".join(value.split())

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
        groups = self._parse_groups(editable[0])
        self.assertEqual(
            groups,
            {"wms_core.group_wms_manager", "base.group_system"},
        )

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
        groups = self._parse_groups(readonly[0])
        self.assertEqual(
            groups,
            {
                "base.group_user",
                "!wms_core.group_wms_manager",
                "!base.group_system",
            },
        )

    # ------------------------------------------------------------------
    # TEST-ZONE-UI-LOC-006: Both occurrences visibility
    # ------------------------------------------------------------------

    def test_zone_ui_loc_06_both_invisible_expressions(self):
        """TEST-ZONE-UI-LOC-006: ambas apariciones tienen la expresión
        invisible exacta aprobada."""
        expected = (
            "usage != 'internal' or "
            "not warehouse_id or "
            "not company_id"
        )
        zone_fields = self._find_fields("wms_zone_id")
        for field in zone_fields:
            self.assertEqual(
                self._normalize_expr(field.get("invisible", "")),
                expected,
            )

    # ------------------------------------------------------------------
    # TEST-ZONE-UI-LOC-007: Both occurrences domain and options
    # ------------------------------------------------------------------

    def test_zone_ui_loc_07_domain_and_options(self):
        """TEST-ZONE-UI-LOC-007: ambas apariciones tienen domain y options
        exactos."""
        expected_domain = (
            "[('warehouse_id', '=', warehouse_id), "
            "('company_id', '=', company_id)]"
        )
        zone_fields = self._find_fields("wms_zone_id")
        for field in zone_fields:
            self.assertEqual(
                self._normalize_expr(field.get("domain", "")),
                expected_domain,
            )
            self.assertEqual(
                field.get("options"),
                "{'no_create': True}",
            )

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
        expected_role_invisible = "usage != 'internal'"

        # Editable: Manager/System, no readonly
        editable = [f for f in role_fields if f.get("readonly") != "1"]
        self.assertEqual(len(editable), 1)
        self.assertEqual(
            self._parse_groups(editable[0]),
            {"wms_core.group_wms_manager", "base.group_system"},
        )
        self.assertEqual(
            self._normalize_expr(editable[0].get("invisible", "")),
            expected_role_invisible,
        )

        # Readonly: base.group_user exclusions
        readonly = [f for f in role_fields if f.get("readonly") == "1"]
        self.assertEqual(len(readonly), 1)
        self.assertEqual(
            self._parse_groups(readonly[0]),
            {
                "base.group_user",
                "!wms_core.group_wms_manager",
                "!base.group_system",
            },
        )
        self.assertEqual(
            self._normalize_expr(readonly[0].get("invisible", "")),
            expected_role_invisible,
        )
