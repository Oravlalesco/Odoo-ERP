from odoo.tests.common import TransactionCase


class TestModuleInstallation(TransactionCase):
    """Verificar instalación de wms_warehouse_master y disponibilidad de dependencias.

    WM-001: Estos tests demuestran que el módulo está correctamente
    instalado y que las dependencias Odoo stock y WMS Core son operacionales.
    """

    def test_wm_01_module_is_installed(self):
        """TEST-WM-001: wms_warehouse_master existe y state=installed."""
        module = self.env["ir.module.module"].search(
            [("name", "=", "wms_warehouse_master")], limit=1
        )
        self.assertTrue(
            module, "wms_warehouse_master no encontrado en ir.module.module"
        )
        self.assertEqual(
            module.state,
            "installed",
            f"wms_warehouse_master debería estar 'installed' pero está '{module.state}'",
        )

    def test_wm_02_stock_location_available(self):
        """TEST-WM-002: stock.location está disponible en el ORM."""
        self.assertIn(
            "stock.location",
            self.env,
            "Modelo stock.location no disponible — la dependencia stock podría faltar",
        )

    def test_wm_03_wms_core_available(self):
        """TEST-WM-003: los grupos de WMS Core son resolubles."""
        operator = self.env.ref("wms_core.group_wms_operator")
        self.assertTrue(
            operator,
            "wms_core.group_wms_operator no resoluble — la dependencia wms_core podría faltar",
        )
