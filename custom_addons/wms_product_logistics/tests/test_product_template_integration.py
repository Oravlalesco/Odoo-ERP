from lxml import etree

from odoo.tests.common import TransactionCase
from odoo.tools.safe_eval import safe_eval


class TestProductTemplateIntegration(TransactionCase):
    """PLM-007C: Validar integración contextual desde product.template hacia wms.product.logistics.

    Cubre:
    - Registro de la vista heredada (model, inherit_id, type).
    - Contrato del stat button (type action, class, icon, string, invisible, groups).
    - Contrato de la acción contextual dedicada (domain, context con active_test=False).
    - Protección de la acción administrativa global (sin domain/context contextual).
    - Búsqueda contextual con perfil existente (retorna exactamente el perfil del producto).
    - Búsqueda contextual sin perfil y default_get (retorna 0 perfiles, default correcto).
    - Preservación del lifecycle de producto archivado (active_test=False).
    - Visibilidad real del botón por rol WMS vs usuario interno plano.
    - Cero auto-creación y ausencia de campos auxiliares en product.template.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.PT = cls.env["product.template"]
        cls.WPL = cls.env["wms.product.logistics"]
        cls.Users = cls.env["res.users"]
        cls.company = cls.env.company

        # Vistas y Acciones
        cls.inherited_view = cls.env.ref("wms_product_logistics.view_product_template_form_wms_logistics")
        cls.parent_view = cls.env.ref("product.product_template_only_form_view")
        cls.action_from_product = cls.env.ref("wms_product_logistics.action_wms_product_logistics_from_product")
        cls.action_admin = cls.env.ref("wms_product_logistics.action_wms_product_logistics")
        cls.search_view = cls.env.ref("wms_product_logistics.view_wms_product_logistics_search")

        cls.view_arch = etree.fromstring(cls.inherited_view.arch)

        # Grupos
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_op = cls.env.ref("wms_core.group_wms_operator")
        cls.group_sup = cls.env.ref("wms_core.group_wms_supervisor")
        cls.group_mgr = cls.env.ref("wms_core.group_wms_manager")
        cls.group_system = cls.env.ref("base.group_system")

        # Usuarios de prueba
        cls.user_operator = cls.Users.create({
            "name": "Test Operator Product Integration",
            "login": "test_op_prod_integ",
            "email": "op_prod_integ@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_op.id])],
        })
        cls.user_supervisor = cls.Users.create({
            "name": "Test Supervisor Product Integration",
            "login": "test_sup_prod_integ",
            "email": "sup_prod_integ@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_sup.id])],
        })
        cls.user_manager = cls.Users.create({
            "name": "Test Manager Product Integration",
            "login": "test_mgr_prod_integ",
            "email": "mgr_prod_integ@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_mgr.id])],
        })
        cls.user_plain_internal = cls.Users.create({
            "name": "Test Plain Internal Product Integration",
            "login": "test_plain_prod_integ",
            "email": "plain_prod_integ@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id])],
        })

    # ------------------------------------------------------------------
    # TEST-PLM-076: Product Template View Registry Contract
    # ------------------------------------------------------------------

    def test_plm_076_product_template_view_registry_contract(self):
        """PLM-007C-076: Registro y tipos de la vista heredada en product.template."""
        self.assertTrue(self.inherited_view, "view_product_template_form_wms_logistics must exist")
        self.assertEqual(self.inherited_view.model, "product.template")
        self.assertEqual(self.inherited_view.inherit_id, self.parent_view)
        self.assertEqual(self.inherited_view.type, "form")

    # ------------------------------------------------------------------
    # TEST-PLM-077: Product Template Button Contract
    # ------------------------------------------------------------------

    def test_plm_077_product_template_button_contract(self):
        """PLM-007C-077: Contrato del botón estadístico (type, class, icon, string, invisible, groups)."""
        buttons = self.view_arch.xpath("//button")
        self.assertEqual(len(buttons), 1, "Must declare exactly 1 stat button in inherited view")

        btn = buttons[0]
        self.assertEqual(btn.get("type"), "action", "Button must be type='action' (not object)")
        self.assertIn("oe_stat_button", btn.get("class", ""), "Button must include class 'oe_stat_button'")
        self.assertEqual(btn.get("icon"), "fa-truck", "Button icon must be 'fa-truck'")
        self.assertEqual(btn.get("string"), "Logística WMS", "Button string must be 'Logística WMS'")
        self.assertEqual(btn.get("invisible"), "not id", "Button invisible condition must be 'not id'")

        # Action reference in button name
        expected_names = {
            str(self.action_from_product.id),
            f"%(action_wms_product_logistics_from_product)d",
            f"%(wms_product_logistics.action_wms_product_logistics_from_product)d",
        }
        self.assertIn(btn.get("name"), expected_names, "Button name must reference action_wms_product_logistics_from_product")

        # Groups exactos
        raw_groups = {g.strip() for g in btn.get("groups", "").split(",") if g.strip()}
        self.assertEqual(
            raw_groups,
            {"wms_core.group_wms_operator", "base.group_system"},
            "Button groups must match exactly Operator and System Admin",
        )

    # ------------------------------------------------------------------
    # TEST-PLM-078: Contextual Action Contract & Admin Boundary
    # ------------------------------------------------------------------

    def test_plm_078_contextual_action_contract(self):
        """PLM-007C-078: action_wms_product_logistics_from_product tiene domain/context exactos y la acción admin permanece intacta."""
        # 1. Acción contextual
        self.assertEqual(self.action_from_product.res_model, "wms.product.logistics")
        self.assertEqual(self.action_from_product.view_mode, "list,form")
        self.assertEqual(self.action_from_product.search_view_id, self.search_view)

        # Domain exacto
        norm_domain = " ".join(self.action_from_product.domain.split())
        self.assertEqual(norm_domain, "[('product_tmpl_id', '=', active_id)]")
        eval_domain = safe_eval(self.action_from_product.domain, {"active_id": 99})
        self.assertEqual(eval_domain, [("product_tmpl_id", "=", 99)])

        # Context exacto (evaluación exacta sin claves espurias ni omisiones)
        eval_context = safe_eval(self.action_from_product.context, {"active_id": 99})
        self.assertEqual(
            eval_context,
            {"default_product_tmpl_id": 99, "active_test": False},
            "Context must evaluate to exactly {'default_product_tmpl_id': active_id, 'active_test': False}",
        )

        # 2. Boundary: Acción administrativa global permanece limpia
        self.assertFalse(
            self.action_admin.domain,
            "Administrative action must not have a contextual domain",
        )
        if self.action_admin.context:
            self.assertNotIn(
                "active_id",
                self.action_admin.context,
                "Administrative action context must not contain active_id",
            )

    # ------------------------------------------------------------------
    # TEST-PLM-079: Existing Profile Context
    # ------------------------------------------------------------------

    def test_plm_079_existing_profile_context(self):
        """PLM-007C-079: Búsqueda contextual con active_id retorna exactamente el único perfil del producto."""
        prod_a = self.PT.create({"name": "Product A", "company_id": self.company.id})
        profile_a = self.WPL.create({"product_tmpl_id": prod_a.id})

        prod_other = self.PT.create({"name": "Product Other", "company_id": self.company.id})
        profile_other = self.WPL.create({"product_tmpl_id": prod_other.id})

        # Evaluar domain y contexto de la acción contextual para prod_a
        ctx = {"default_product_tmpl_id": prod_a.id, "active_test": False}
        domain = [("product_tmpl_id", "=", prod_a.id)]
        results = self.WPL.with_context(**ctx).search(domain)

        self.assertEqual(len(results), 1, "Must return exactly 1 profile")
        self.assertEqual(results, profile_a, "Must return profile of Product A")
        self.assertNotIn(profile_other, results, "Must not return profile of other products")

    # ------------------------------------------------------------------
    # TEST-PLM-080: Missing Profile Default Context
    # ------------------------------------------------------------------

    def test_plm_080_missing_profile_default_context(self):
        """PLM-007C-080: Producto sin perfil retorna 0 registros y default_get provee el producto actual."""
        prod_b = self.PT.create({"name": "Product B Without Profile", "company_id": self.company.id})

        # Domain contextual retorna 0
        ctx = {"default_product_tmpl_id": prod_b.id, "active_test": False}
        domain = [("product_tmpl_id", "=", prod_b.id)]
        results = self.WPL.with_context(**ctx).search(domain)
        self.assertEqual(len(results), 0, "Missing profile must return empty search result")

        # default_get con el contexto provee product_tmpl_id
        defaults = self.WPL.with_context(**ctx).default_get(["product_tmpl_id"])
        self.assertEqual(defaults.get("product_tmpl_id"), prod_b.id, "default_get must return current product ID")

        # No hay auto-creación: el perfil aún no existe
        existing = self.WPL.search([("product_tmpl_id", "=", prod_b.id)])
        self.assertFalse(existing, "Evaluating action context must not auto-create profile")

    # ------------------------------------------------------------------
    # TEST-PLM-081: Archived Product Profile Context
    # ------------------------------------------------------------------

    def test_plm_081_archived_product_profile_context(self):
        """PLM-007C-081: Producto archivado conserva acceso a su perfil gracias a active_test=False."""
        prod_c = self.PT.create({"name": "Product C To Archive", "company_id": self.company.id})
        profile_c = self.WPL.create({"product_tmpl_id": prod_c.id})

        # Archivar producto
        prod_c.active = False

        # El perfil también queda archivado por related store (PLM-002)
        self.assertFalse(profile_c.active, "Profile must be archived when product is archived")

        # Búsqueda normal sin active_test=False no encuentra el perfil archivado
        normal_search = self.WPL.search([("product_tmpl_id", "=", prod_c.id)])
        self.assertFalse(normal_search, "Normal search must exclude archived profile")

        # Búsqueda con el contexto de la acción contextual (active_test=False) SÍ lo encuentra
        ctx = {"default_product_tmpl_id": prod_c.id, "active_test": False}
        domain = [("product_tmpl_id", "=", prod_c.id)]
        contextual_search = self.WPL.with_context(**ctx).search(domain)

        self.assertEqual(len(contextual_search), 1, "Contextual search with active_test=False must find archived profile")
        self.assertEqual(contextual_search, profile_c)

    # ------------------------------------------------------------------
    # TEST-PLM-082: Button Role Visibility
    # ------------------------------------------------------------------

    def test_plm_082_button_role_visibility(self):
        """PLM-007C-082: Botón presente en formulario para roles WMS y ausente para usuario interno plano."""
        # 1. Comprobación de grupos en raw inherited arch
        raw_groups = {g.strip() for g in self.view_arch.xpath("//button/@groups")[0].split(",") if g.strip()}
        self.assertEqual(
            raw_groups,
            {"wms_core.group_wms_operator", "base.group_system"},
            "Raw inherited button groups must match exactly Operator and System Admin",
        )

        # 2. Comprobación en formulario procesado por usuario (get_view)
        admin_user = self.env.ref("base.user_admin")
        for user, expected_visible in [
            (self.user_operator, True),
            (self.user_supervisor, True),
            (self.user_manager, True),
            (admin_user, True),
            (self.user_plain_internal, False),
        ]:
            view_info = self.PT.with_user(user).get_view(self.parent_view.id, "form")
            processed_arch = etree.fromstring(view_info["arch"])
            matching_buttons = processed_arch.xpath(
                f"//button[@name='{self.action_from_product.id}' or @icon='fa-truck']"
            )
            if expected_visible:
                self.assertTrue(
                    matching_buttons,
                    f"WMS stat button must be present for user {user.name}",
                )
            else:
                self.assertFalse(
                    matching_buttons,
                    f"WMS stat button must be ABSENT for plain internal user {user.name}",
                )

    # ------------------------------------------------------------------
    # TEST-PLM-083: No Auto-Create & No Helper Fields
    # ------------------------------------------------------------------

    def test_plm_083_no_auto_create_and_no_helper_fields(self):
        """PLM-007C-083: No hay auto-creación de perfiles y product.template no adquiere campos helper."""
        count_before = self.WPL.search_count([])

        prod_test = self.PT.create({"name": "Test Prod No Auto", "company_id": self.company.id})

        # Simular lectura de vista y acción contextual
        ctx = {"default_product_tmpl_id": prod_test.id, "active_test": False}
        domain = [("product_tmpl_id", "=", prod_test.id)]
        _ = self.WPL.with_context(**ctx).search(domain)
        _ = self.WPL.with_context(**ctx).default_get(["product_tmpl_id"])

        count_after = self.WPL.search_count([])
        self.assertEqual(
            count_before,
            count_after,
            "Evaluating contextual action or defaults must NOT create records",
        )

        # Ausencia de helper fields en product.template
        for prohibited_field in [
            "wms_product_logistics_id",
            "wms_logistics_profile_id",
            "logistics_profile_id",
        ]:
            self.assertNotIn(
                prohibited_field,
                self.PT._fields,
                f"Prohibited helper field '{prohibited_field}' must not exist on product.template",
            )
