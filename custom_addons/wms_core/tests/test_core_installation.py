from odoo.tests.common import TransactionCase


class TestCoreInstallation(TransactionCase):
    """Verify wms_core module installation and ORM availability.

    CORE-001: These tests prove that wms_core is correctly installed
    and that the ORM environment is functional under it.
    """

    def test_01_module_is_installed(self):
        """TEST-001: wms_core exists in ir.module.module and state=installed."""
        module = self.env["ir.module.module"].search(
            [("name", "=", "wms_core")], limit=1
        )
        self.assertTrue(module, "wms_core not found in ir.module.module")
        self.assertEqual(
            module.state,
            "installed",
            f"wms_core should be 'installed' but is '{module.state}'",
        )

    def test_02_orm_basic_operational(self):
        """TEST-002: ORM basic — env.company is accessible."""
        company = self.env.company
        self.assertTrue(company, "env.company is not accessible")
        self.assertTrue(company.name, "env.company.name is empty")
