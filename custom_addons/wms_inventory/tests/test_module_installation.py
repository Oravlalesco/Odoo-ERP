from odoo.tests.common import TransactionCase


class TestInventoryModuleInstallation(TransactionCase):
    """Verificar instalación de wms_inventory y disponibilidad de dependencias.

    INV-001: Demuestra que el módulo está correctamente instalado, que las
    dependencias requeridas (wms_core, wms_warehouse_master, stock) están
    instaladas, los modelos base disponibles en el ORM y la semántica de
    ubicación (wms_location_role) accesible.
    """

    def test_inv_01_module_is_installed(self):
        """TEST-INV-001: wms_inventory existe en ir.module.module y state=installed."""
        module = self.env["ir.module.module"].search(
            [("name", "=", "wms_inventory")], limit=1
        )
        self.assertTrue(module, "wms_inventory no encontrado en ir.module.module")
        self.assertEqual(
            module.state,
            "installed",
            f"wms_inventory debería estar 'installed' pero está '{module.state}'",
        )

    def test_inv_02_required_dependencies_available(self):
        """TEST-INV-002: dependencias wms_core, wms_warehouse_master y stock instaladas y modelos disponibles."""
        # 1. Módulos dependientes instalados
        for dep_name in ["wms_core", "wms_warehouse_master", "stock"]:
            dep_mod = self.env["ir.module.module"].search(
                [("name", "=", dep_name)], limit=1
            )
            self.assertTrue(
                dep_mod,
                f"Módulo dependiente '{dep_name}' no encontrado en ir.module.module",
            )
            self.assertEqual(
                dep_mod.state,
                "installed",
                f"Módulo dependiente '{dep_name}' debe estar instalado pero está '{dep_mod.state}'",
            )

        # 2. Modelos en registry
        for model_name in ["stock.quant", "stock.move", "stock.move.line", "stock.location"]:
            self.assertIn(
                model_name,
                self.env,
                f"Modelo '{model_name}' no disponible en el registry de Odoo",
            )

        # 3. Semántica de ubicación de wms_warehouse_master disponible
        self.assertIn(
            "wms_location_role",
            self.env["stock.location"]._fields,
            "El campo 'wms_location_role' debe existir en stock.location aportado por wms_warehouse_master",
        )
