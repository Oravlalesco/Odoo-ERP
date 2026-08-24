from odoo.tests.common import TransactionCase


class TestWorkModuleInstallation(TransactionCase):
    """Verificar instalación de wms_work, dependencias arquitectónicas y contratos base.

    WORK-001: Demuestra que el módulo está correctamente instalado, que las
    dependencias requeridas (wms_core, wms_warehouse_master, wms_inventory,
    wms_handling_unit, stock) están instaladas, y que todos los modelos, campos,
    primitives y roles de seguridad que constituyen las foundations del Work Engine
    están disponibles en el registry de Odoo 19.
    """

    def test_work_01_module_installation(self):
        """TEST-WORK-001: wms_work existe en ir.module.module, state=installed y metadata correcta."""
        module = self.env["ir.module.module"].search(
            [("name", "=", "wms_work")], limit=1
        )
        self.assertTrue(module, "wms_work no encontrado en ir.module.module")
        self.assertEqual(
            module.state,
            "installed",
            f"wms_work debería estar 'installed' pero está '{module.state}'",
        )
        # Versión instalada
        version = module.installed_version or module.latest_version
        self.assertEqual(
            version,
            "19.0.1.0.0",
            f"Versión esperada '19.0.1.0.0', obtenida '{version}'",
        )
        # Propiedades del manifest
        self.assertFalse(
            module.application,
            "wms_work debe ser application=False (sin menú raíz principal independiente)",
        )
        self.assertFalse(
            module.auto_install,
            "wms_work debe ser auto_install=False",
        )

    def test_work_02_foundation_and_dependency_contract(self):
        """TEST-WORK-002: dependencias instaladas, modelos en registry, campos y primitives disponibles."""
        # 1. Módulos dependientes directos instalados
        required_deps = [
            "wms_core",
            "wms_warehouse_master",
            "wms_inventory",
            "wms_handling_unit",
            "stock",
        ]
        for dep_name in required_deps:
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

        # 2. Modelos requeridos presentes en el registry
        required_models = [
            "stock.picking",
            "stock.move",
            "stock.move.line",
            "stock.quant",
            "stock.package",
            "stock.location",
            "stock.warehouse",
            "wms.zone",
            "wms.activity.area",
            "wms.storage.type",
            "wms.inventory.block",
            "wms.inventory.event",
            "wms.outbox",
            "wms.sscc.sequence",
        ]
        for model_name in required_models:
            self.assertIn(
                model_name,
                self.env,
                f"Modelo '{model_name}' no disponible en el registry de Odoo",
            )

        # 3. Campos WMS en stock.location aportados por wms_warehouse_master
        location_fields = [
            "wms_location_role",
            "wms_zone_id",
            "wms_storage_type_id",
        ]
        for field_name in location_fields:
            self.assertIn(
                field_name,
                self.env["stock.location"]._fields,
                f"El campo WMS '{field_name}' debe existir en stock.location",
            )

        # 4. Campos WMS en stock.package aportados por wms_handling_unit
        package_fields = [
            "hu_state",
            "hu_class",
        ]
        for field_name in package_fields:
            self.assertIn(
                field_name,
                self.env["stock.package"]._fields,
                f"El campo WMS '{field_name}' debe existir en stock.package",
            )

        # 5. Primitives físicas de Handling Unit en stock.package
        physical_primitives = [
            "_wms_pack_physical",
            "_wms_unpack_physical",
            "_wms_split_physical",
            "_wms_merge_physical",
        ]
        for method_name in physical_primitives:
            self.assertTrue(
                hasattr(self.env["stock.package"], method_name),
                f"La primitive física '{method_name}' debe existir en stock.package",
            )

        # 6. Boundary de persistencia atómica en wms.inventory.event (ADR-019)
        self.assertTrue(
            hasattr(self.env["wms.inventory.event"], "_append_events_with_outbox"),
            "La API transaccional '_append_events_with_outbox' debe existir en wms.inventory.event",
        )

        # 7. Grupos de seguridad RBAC de wms_core resolubles
        required_groups = [
            "wms_core.group_wms_operator",
            "wms_core.group_wms_supervisor",
            "wms_core.group_wms_manager",
        ]
        for group_xml_id in required_groups:
            group = self.env.ref(group_xml_id, raise_if_not_found=False)
            self.assertTrue(
                group,
                f"El grupo de seguridad '{group_xml_id}' debe ser resoluble en la base de datos",
            )
