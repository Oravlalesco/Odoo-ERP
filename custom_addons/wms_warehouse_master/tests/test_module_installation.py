from odoo.tests.common import TransactionCase


class TestModuleInstallation(TransactionCase):
    """Verify wms_warehouse_master installation and dependency availability.

    WM-001: These tests prove that the module is correctly installed
    and that both Odoo stock and WMS Core dependencies are operational.
    """

    def test_wm_01_module_is_installed(self):
        """TEST-WM-001: wms_warehouse_master exists and state=installed."""
        module = self.env["ir.module.module"].search(
            [("name", "=", "wms_warehouse_master")], limit=1
        )
        self.assertTrue(
            module, "wms_warehouse_master not found in ir.module.module"
        )
        self.assertEqual(
            module.state,
            "installed",
            f"wms_warehouse_master should be 'installed' but is '{module.state}'",
        )

    def test_wm_02_stock_location_available(self):
        """TEST-WM-002: stock.location is available in the ORM."""
        self.assertIn(
            "stock.location",
            self.env,
            "stock.location model not available — stock dependency may be missing",
        )

    def test_wm_03_wms_core_available(self):
        """TEST-WM-003: WMS Core groups are resolvable."""
        operator = self.env.ref("wms_core.group_wms_operator")
        self.assertTrue(
            operator,
            "wms_core.group_wms_operator not resolvable — wms_core dependency may be missing",
        )
