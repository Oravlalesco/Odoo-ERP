import ast
from lxml import etree

from odoo.tests.common import TransactionCase


class TestAdministrativeViews(TransactionCase):
    """PLM-007A: Validar vistas administrativas de wms.product.logistics.

    Cubre:
    - Registro de vistas (list, form, search) y tipos.
    - Contrato de list view (10 columnas exactas, root list, sin editable).
    - Inventario de form view (exactamente 25 campos funcionales, sin duplicados).
    - Semántica readonly en los 5 campos derivados/relacionados.
    - Opciones de seguridad en los 6 campos relacionales configurables (no_create, no_quick_create).
    - Contrato de search view (7 search fields, 2 filtros con domain, 4 agrupadores con context).
    - Contrato de acción de ventana (res_model, view_mode, search_view_id).
    - Ausencia total de campos diferidos de estrategia (PLM-006B).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.list_view = cls.env.ref("wms_product_logistics.view_wms_product_logistics_list")
        cls.form_view = cls.env.ref("wms_product_logistics.view_wms_product_logistics_form")
        cls.search_view = cls.env.ref("wms_product_logistics.view_wms_product_logistics_search")
        cls.action = cls.env.ref("wms_product_logistics.action_wms_product_logistics")

        cls.list_arch = etree.fromstring(cls.list_view.arch)
        cls.form_arch = etree.fromstring(cls.form_view.arch)
        cls.search_arch = etree.fromstring(cls.search_view.arch)

    # ------------------------------------------------------------------
    # TEST-PLM-060: View Registry Contract
    # ------------------------------------------------------------------

    def test_plm_060_view_registry_contract(self):
        """PLM-007A-060: Verificar registro y tipos de las 3 vistas ir.ui.view."""
        self.assertTrue(self.list_view)
        self.assertEqual(self.list_view.model, "wms.product.logistics")
        self.assertEqual(self.list_view.type, "list")

        self.assertTrue(self.form_view)
        self.assertEqual(self.form_view.model, "wms.product.logistics")
        self.assertEqual(self.form_view.type, "form")

        self.assertTrue(self.search_view)
        self.assertEqual(self.search_view.model, "wms.product.logistics")
        self.assertEqual(self.search_view.type, "search")

    # ------------------------------------------------------------------
    # TEST-PLM-061: List View Contract
    # ------------------------------------------------------------------

    def test_plm_061_list_view_contract(self):
        """PLM-007A-061: List view tiene exactamente las 10 columnas contratadas, root <list> y sin editable."""
        self.assertEqual(self.list_arch.tag, "list", "Root tag must be <list>")
        self.assertIsNone(self.list_arch.get("editable"), "List view must not have editable attribute")
        self.assertIsNone(self.list_arch.get("multi_edit"), "List view must not have multi_edit attribute")

        list_fields = [f.get("name") for f in self.list_arch.xpath("//field")]
        expected_fields = [
            "product_tmpl_id",
            "company_id",
            "pick_uom_id",
            "case_uom_id",
            "pallet_uom_id",
            "abc_class",
            "velocity_class",
            "temperature_class",
            "requires_quality_inspection",
            "active",
        ]
        self.assertEqual(len(list_fields), 10, "List view must contain exactly 10 fields")
        self.assertEqual(list_fields, expected_fields, "List view field inventory mismatch")

    # ------------------------------------------------------------------
    # TEST-PLM-062: Form Field Inventory
    # ------------------------------------------------------------------

    def test_plm_062_form_field_inventory(self):
        """PLM-007A-062: Form view contiene exactamente los 25 campos funcionales, una sola vez cada uno."""
        form_fields = self.form_arch.xpath("//field/@name")
        expected_fields = {
            "product_tmpl_id",
            "company_id",
            "active",
            "pick_uom_id",
            "case_uom_id",
            "pallet_uom_id",
            "cases_per_layer",
            "layers_per_pallet",
            "base_qty_per_case",
            "cases_per_pallet",
            "base_qty_per_pallet",
            "abc_class",
            "velocity_class",
            "temperature_class",
            "hazmat_class",
            "stackable",
            "max_stack",
            "fragile",
            "min_shelf_life_receipt_days",
            "min_shelf_life_shipping_days",
            "allowed_hu_type_ids",
            "default_hu_type_id",
            "requires_quality_inspection",
            "quality_inspection_type",
            "quality_sampling_rate",
        }
        self.assertEqual(len(form_fields), 25, "Form view must contain exactly 25 field occurrences")
        self.assertEqual(set(form_fields), expected_fields, "Form view field set mismatch")
        self.assertEqual(len(set(form_fields)), 25, "Form view must not contain duplicate fields")

    # ------------------------------------------------------------------
    # TEST-PLM-063: Readonly Field Semantics
    # ------------------------------------------------------------------

    def test_plm_063_readonly_field_semantics(self):
        """PLM-007A-063: Exactamente los 5 campos readonly esperados tienen readonly='1' en la form."""
        expected_readonly = {
            "company_id",
            "active",
            "base_qty_per_case",
            "cases_per_pallet",
            "base_qty_per_pallet",
        }
        readonly_found = set()
        for field_elem in self.form_arch.xpath("//field"):
            name = field_elem.get("name")
            if field_elem.get("readonly") == "1":
                readonly_found.add(name)

        self.assertEqual(
            readonly_found,
            expected_readonly,
            "Form view readonly fields mismatch",
        )

    # ------------------------------------------------------------------
    # TEST-PLM-064: Relational Field Safety Options
    # ------------------------------------------------------------------

    def test_plm_064_relational_field_safety_options(self):
        """PLM-007A-064: Los 6 campos relacionales configurables tienen no_create y no_quick_create en options."""
        relational_fields = [
            "product_tmpl_id",
            "pick_uom_id",
            "case_uom_id",
            "pallet_uom_id",
            "allowed_hu_type_ids",
            "default_hu_type_id",
        ]
        for field_name in relational_fields:
            nodes = self.form_arch.xpath(f"//field[@name='{field_name}']")
            self.assertEqual(len(nodes), 1, f"Field '{field_name}' must exist once in form")
            options_str = nodes[0].get("options")
            self.assertTrue(options_str, f"Field '{field_name}' must have options attribute")
            options = ast.literal_eval(options_str)
            self.assertTrue(
                options.get("no_create"),
                f"Field '{field_name}' options must have 'no_create': True",
            )
            self.assertTrue(
                options.get("no_quick_create"),
                f"Field '{field_name}' options must have 'no_quick_create': True",
            )

    # ------------------------------------------------------------------
    # TEST-PLM-065: Search View Contract
    # ------------------------------------------------------------------

    def test_plm_065_search_view_contract(self):
        """PLM-007A-065: Search view contiene 7 search fields, 2 filtros y 4 agrupadores con domains/context válidos."""
        # 1. Search fields (7)
        search_fields = self.search_arch.xpath("//search/field/@name")
        expected_search_fields = [
            "product_tmpl_id",
            "company_id",
            "abc_class",
            "velocity_class",
            "temperature_class",
            "hazmat_class",
            "requires_quality_inspection",
        ]
        self.assertEqual(search_fields, expected_search_fields, "Search view search fields mismatch")

        # 2. Filters
        filter_inactive = self.search_arch.xpath("//filter[@name='inactive']")
        self.assertEqual(len(filter_inactive), 1, "Filter 'inactive' must exist")
        self.assertIn("('active', '=', False)", filter_inactive[0].get("domain", ""))

        filter_quality = self.search_arch.xpath("//filter[@name='requires_quality_inspection']")
        self.assertEqual(len(filter_quality), 1, "Filter 'requires_quality_inspection' must exist")
        self.assertIn("('requires_quality_inspection', '=', True)", filter_quality[0].get("domain", ""))

        # 3. Group by filters
        group_company = self.search_arch.xpath("//filter[@name='group_company']")
        self.assertEqual(len(group_company), 1, "Group filter 'group_company' must exist")
        self.assertIn("'group_by': 'company_id'", group_company[0].get("context", ""))

        group_abc = self.search_arch.xpath("//filter[@name='group_abc_class']")
        self.assertEqual(len(group_abc), 1, "Group filter 'group_abc_class' must exist")
        self.assertIn("'group_by': 'abc_class'", group_abc[0].get("context", ""))

        group_vel = self.search_arch.xpath("//filter[@name='group_velocity_class']")
        self.assertEqual(len(group_vel), 1, "Group filter 'group_velocity_class' must exist")
        self.assertIn("'group_by': 'velocity_class'", group_vel[0].get("context", ""))

        group_temp = self.search_arch.xpath("//filter[@name='group_temperature_class']")
        self.assertEqual(len(group_temp), 1, "Group filter 'group_temperature_class' must exist")
        self.assertIn("'group_by': 'temperature_class'", group_temp[0].get("context", ""))

    # ------------------------------------------------------------------
    # TEST-PLM-066: Window Action Contract
    # ------------------------------------------------------------------

    def test_plm_066_window_action_contract(self):
        """PLM-007A-066: action_wms_product_logistics tiene res_model, view_mode y search_view_id correctos."""
        self.assertEqual(self.action.res_model, "wms.product.logistics")
        self.assertEqual(self.action.view_mode, "list,form")
        self.assertEqual(self.action.search_view_id, self.search_view)
        self.assertTrue(self.action.help, "Action help text must not be empty")

    # ------------------------------------------------------------------
    # TEST-PLM-067: Deferred Strategy Fields Absent
    # ------------------------------------------------------------------

    def test_plm_067_deferred_strategy_fields_absent(self):
        """PLM-007A-067: Los campos de estrategia diferidos (PLM-006B) no están presentes en ninguna vista."""
        deferred_fields = {
            "storage_profile",
            "putaway_profile",
            "replenishment_profile",
            "allocation_profile",
        }
        for view_name, arch in [
            ("list", self.list_arch),
            ("form", self.form_arch),
            ("search", self.search_arch),
        ]:
            field_names = set(arch.xpath("//field/@name"))
            found = field_names.intersection(deferred_fields)
            self.assertFalse(
                found,
                f"Deferred fields {found} found in {view_name} view",
            )
            # Also ensure no menuitem in view xml
            menu_items = arch.xpath("//menuitem")
            self.assertEqual(
                len(menu_items),
                0,
                f"No <menuitem> elements allowed in {view_name} view arch",
            )
