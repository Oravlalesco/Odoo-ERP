from odoo.tests.common import TransactionCase


class TestCanary(TransactionCase):
    """Canary tests verifying the complete development pipeline.

    BOOT-005: These tests prove four things:
    1. Addon discovery    — wms_canary was found in /mnt/extra-addons
    2. Module installation — wms_canary is in 'installed' state
    3. ORM availability    — env['res.company'] works, env.company exists
    4. Test discovery      — this test class was found and executed by the runner

    This module will be removed after BOOT-GATE when wms_core is operational.
    """

    def test_01_module_is_installed(self):
        """Verify that wms_canary module is installed (proves addon discovery + installation)."""
        module = self.env["ir.module.module"].search(
            [("name", "=", "wms_canary")], limit=1
        )
        self.assertTrue(module, "wms_canary module not found in ir.module.module")
        self.assertEqual(
            module.state,
            "installed",
            f"wms_canary should be 'installed' but is '{module.state}'",
        )

    def test_02_orm_environment_available(self):
        """Verify that the ORM environment is functional (res.company exists)."""
        companies = self.env["res.company"].search([])
        self.assertTrue(
            companies,
            "No companies found — ORM environment may not be properly initialized",
        )

    def test_03_env_company_accessible(self):
        """Verify that env.company is accessible (standard Odoo context)."""
        company = self.env.company
        self.assertTrue(company, "env.company is not accessible")
        self.assertTrue(company.name, "env.company.name is empty")

    def test_04_canary_model_registered(self):
        """Verify that wms.canary transient model is registered in the ORM."""
        self.assertIn(
            "wms.canary",
            self.env,
            "wms.canary model not registered in the ORM registry",
        )
        # Verify we can create a record
        record = self.env["wms.canary"].create({"name": "boot-005-test"})
        self.assertEqual(record.name, "boot-005-test")
