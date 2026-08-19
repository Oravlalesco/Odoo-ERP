from odoo.tests.common import TransactionCase


class TestProductLogisticsModuleInstallation(TransactionCase):
    """Verificar instalación de wms_product_logistics y disponibilidad de dependencias.

    PLM-001: Demuestra que el módulo está correctamente instalado y que los
    modelos base requeridos de la dependencia product están disponibles en el ORM.
    """

    def test_plm_01_module_is_installed(self):
        """TEST-PLM-001: wms_product_logistics existe y state=installed."""
        module = self.env["ir.module.module"].search(
            [("name", "=", "wms_product_logistics")], limit=1
        )
        self.assertTrue(
            module, "wms_product_logistics no encontrado en ir.module.module"
        )
        self.assertEqual(
            module.state,
            "installed",
            f"wms_product_logistics debería estar 'installed' pero está '{module.state}'",
        )

    def test_plm_02_required_models_available(self):
        """TEST-PLM-002: product.template y product.uom están disponibles en el ORM."""
        self.assertIn(
            "product.template",
            self.env,
            "Modelo product.template no disponible — la dependencia product podría faltar",
        )
        self.assertIn(
            "product.uom",
            self.env,
            "Modelo product.uom no disponible — la dependencia product podría faltar",
        )
