from odoo.tests.common import TransactionCase


class TestHandlingUnitModuleInstallation(TransactionCase):
    """Verificar instalación de wms_handling_unit, dependencias y fundamento nativo.

    HU-001: Demuestra que el módulo está correctamente instalado, que las
    dependencias requeridas (wms_core, wms_warehouse_master, wms_product_logistics, stock)
    están instaladas, los modelos base y campos nativos requeridos para Handling Units
    (stock.package, stock.package.type, wms.product.logistics, stock.location) están
    disponibles y que queda prohibido cualquier modelo paralelo wms.handling.unit.
    """

    def test_hu_01_module_is_installed(self):
        """TEST-HU-001: wms_handling_unit existe en ir.module.module y state=installed."""
        module = self.env["ir.module.module"].search(
            [("name", "=", "wms_handling_unit")], limit=1
        )
        self.assertTrue(module, "wms_handling_unit no encontrado en ir.module.module")
        self.assertEqual(
            module.state,
            "installed",
            f"wms_handling_unit debería estar 'installed' pero está '{module.state}'",
        )

    def test_hu_02_native_foundation_and_dependencies(self):
        """TEST-HU-002: dependencias instaladas, modelos en registry, campos nativos de HU y no modelo paralelo."""
        # 1. Módulos dependientes instalados
        for dep_name in ["wms_core", "wms_warehouse_master", "wms_product_logistics", "stock"]:
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
        for model_name in ["stock.package", "stock.package.type", "wms.product.logistics", "stock.location"]:
            self.assertIn(
                model_name,
                self.env,
                f"Modelo '{model_name}' no disponible en el registry de Odoo",
            )

        # 3. Campos nativos de stock.package como fundamento de Handling Unit
        pkg_fields = [
            "parent_package_id",
            "child_package_ids",
            "parent_path",
            "quant_ids",
            "contained_quant_ids",
            "package_type_id",
            "location_id",
            "company_id",
            "owner_id",
            "shipping_weight",
            "pack_date",
            "valid_sscc",
        ]
        for field_name in pkg_fields:
            self.assertIn(
                field_name,
                self.env["stock.package"]._fields,
                f"El campo nativo '{field_name}' debe existir en stock.package",
            )

        # 4. Campos nativos de stock.package.type
        pkg_type_fields = [
            "height",
            "width",
            "packaging_length",
            "base_weight",
            "max_weight",
            "barcode",
            "storage_category_capacity_ids",
        ]
        for field_name in pkg_type_fields:
            self.assertIn(
                field_name,
                self.env["stock.package.type"]._fields,
                f"El campo nativo '{field_name}' debe existir en stock.package.type",
            )

        # 5. Semántica de ubicación aportada por wms_warehouse_master
        self.assertIn(
            "wms_location_role",
            self.env["stock.location"]._fields,
            "El campo 'wms_location_role' debe existir en stock.location aportado por wms_warehouse_master",
        )

        # 6. Perfil logístico PLM aportado por wms_product_logistics
        self.assertIn(
            "allowed_hu_type_ids",
            self.env["wms.product.logistics"]._fields,
            "El campo 'allowed_hu_type_ids' debe existir en wms.product.logistics",
        )
        self.assertIn(
            "default_hu_type_id",
            self.env["wms.product.logistics"]._fields,
            "El campo 'default_hu_type_id' debe existir en wms.product.logistics",
        )

        # 7. Invariante ADR-013: Prohibido modelo paralelo wms.handling.unit
        self.assertNotIn(
            "wms.handling.unit",
            self.env,
            "ADR-013: Queda prohibido crear el modelo paralelo 'wms.handling.unit' (la HU es stock.package)",
        )
