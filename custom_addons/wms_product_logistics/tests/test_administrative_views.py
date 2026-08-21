import ast
from lxml import etree

from odoo.tests.common import TransactionCase


class TestAdministrativeViews(TransactionCase):
    """PLM-007A: Validar vistas administrativas de wms.product.logistics.

    Cubre:
    - Registro de vistas (list, form, search) y tipos.
    - Contrato de list view (10 columnas exactas, root list, sin editable).
    - Inventario de form view (exactamente 25 campos funcionales, sin duplicados, 6 páginas).
    - Semántica readonly en los 5 campos derivados/relacionados.
    - Opciones de seguridad en los 6 campos relacionales configurables (no_create, no_quick_create).
    - Contrato de search view (7 search fields, exactamente 2 filtros directos, exactamente 4 agrupadores con context).
    - Contrato de acción de ventana (res_model, view_mode, search_view_id).
    - Ausencia total de campos diferidos de estrategia (PLM-006B) y ausencia de etiquetas menuitem en vistas.
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

    @staticmethod
    def _normalize_expr(value):
        """Normalizar whitespace de una expresión XML."""
        if not value:
            return ""
        return " ".join(value.split())

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
    # TEST-PLM-062: Form Field Inventory & Notebook Pages
    # ------------------------------------------------------------------

    def test_plm_062_form_field_inventory(self):
        """PLM-007A-062: Form view contiene exactamente los 25 campos funcionales (una sola vez) y exactamente 6 páginas."""
        # 1. 25 campos únicos
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

        # 2. Exactamente 6 páginas en el notebook
        pages = self.form_arch.xpath("//notebook/page")
        self.assertEqual(len(pages), 6, "Form view must contain exactly 6 notebook pages")
        page_names = [p.get("name") for p in pages]
        expected_page_names = [
            "identity",
            "operational_uom",
            "packaging_tihi",
            "classification_handling",
            "shelf_life_hu",
            "quality",
        ]
        self.assertEqual(page_names, expected_page_names, "Notebook page names mismatch")

        page_strings = [p.get("string") for p in pages]
        expected_page_strings = [
            "Identidad",
            "UOM Operacionales",
            "Packaging & Ti-Hi",
            "Clasificación & Manejo",
            "Vida Útil & HUs",
            "Calidad",
        ]
        self.assertEqual(page_strings, expected_page_strings, "Notebook page strings mismatch")

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
    # TEST-PLM-065: Search View Contract (Exact counts and expressions)
    # ------------------------------------------------------------------

    def test_plm_065_search_view_contract(self):
        """PLM-007A-065: Search view contiene exactamente 7 search fields, exactamente 2 filtros y exactamente 4 agrupadores."""
        # 1. Exactamente 7 search fields
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
        self.assertEqual(len(search_fields), 7, "Search view must contain exactly 7 search fields")
        self.assertEqual(search_fields, expected_search_fields, "Search view search fields mismatch")

        # 2. Exactamente 2 filtros directos
        direct_filters = self.search_arch.xpath("//search/filter[not(ancestor::group)]")
        self.assertEqual(len(direct_filters), 2, "Search view must contain exactly 2 direct filters")
        filter_dict = {f.get("name"): f for f in direct_filters}
        self.assertEqual(
            set(filter_dict.keys()),
            {"inactive", "requires_quality_inspection"},
            "Direct filter names mismatch",
        )
        self.assertEqual(
            self._normalize_expr(filter_dict["inactive"].get("domain")),
            "[('active', '=', False)]",
            "Filter 'inactive' domain mismatch",
        )
        self.assertEqual(
            self._normalize_expr(filter_dict["requires_quality_inspection"].get("domain")),
            "[('requires_quality_inspection', '=', True)]",
            "Filter 'requires_quality_inspection' domain mismatch",
        )

        # 3. Exactamente 4 agrupadores dentro de <group>
        group_elements = self.search_arch.xpath("//search/group")
        self.assertEqual(len(group_elements), 1, "Search view must contain exactly 1 <group> for group-by")
        groupby_filters = self.search_arch.xpath("//search/group/filter")
        self.assertEqual(len(groupby_filters), 4, "Search view must contain exactly 4 group-by filters")
        groupby_dict = {f.get("name"): f for f in groupby_filters}
        self.assertEqual(
            set(groupby_dict.keys()),
            {
                "group_company",
                "group_abc_class",
                "group_velocity_class",
                "group_temperature_class",
            },
            "Group-by filter names mismatch",
        )
        for name, expected_field in [
            ("group_company", "company_id"),
            ("group_abc_class", "abc_class"),
            ("group_velocity_class", "velocity_class"),
            ("group_temperature_class", "temperature_class"),
        ]:
            ctx = ast.literal_eval(groupby_dict[name].get("context", "{}"))
            self.assertEqual(
                ctx,
                {"group_by": expected_field},
                f"Group-by filter '{name}' context mismatch",
            )

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
        """PLM-007A-067: Los campos diferidos (PLM-006B) y etiquetas menuitem no están presentes en los arch de las vistas."""
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
            # Asegurar que no hay etiquetas <menuitem> dentro de los arch
            menu_items = arch.xpath("//menuitem")
            self.assertEqual(
                len(menu_items),
                0,
                f"No <menuitem> elements allowed in {view_name} view arch",
            )

