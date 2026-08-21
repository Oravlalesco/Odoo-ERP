from odoo.tests.common import TransactionCase


class TestWmsCoreNavigation(TransactionCase):
    """CORE-NAV: Validar el menú raíz compartido del WMS."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root_menu = cls.env.ref("wms_core.menu_wms_root")

    def test_core_nav_01_root_registry_contract(self):
        """CORE-NAV-001: Verificar registro y atributos del menú raíz WMS."""
        self.assertTrue(self.root_menu, "wms_core.menu_wms_root must exist")
        self.assertEqual(self.root_menu._name, "ir.ui.menu")
        self.assertEqual(self.root_menu.name, "WMS")
        self.assertFalse(self.root_menu.parent_id, "Root menu must not have a parent")
        self.assertFalse(self.root_menu.action, "Root menu must not have a direct action")
        self.assertEqual(self.root_menu.sequence, 145)

    def test_core_nav_02_root_rbac_contract(self):
        """CORE-NAV-002: Verificar que los grupos del menú raíz sean exactamente Operator y System Admin."""
        expected_groups = {
            self.env.ref("wms_core.group_wms_operator"),
            self.env.ref("base.group_system"),
        }
        self.assertEqual(
            set(self.root_menu.group_ids),
            expected_groups,
            "Root menu groups must match exactly Operator and System Admin (no additional groups allowed)",
        )
