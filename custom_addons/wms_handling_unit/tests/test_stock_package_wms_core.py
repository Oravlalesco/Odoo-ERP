from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestStockPackageWmsCore(TransactionCase):
    """Pruebas unitarias para los metadatos WMS en stock.package (HU-002).

    Valida:
    - TEST-HU-003: _inherit = stock.package, existencia exclusiva de hu_state y hu_class,
                   ausencia de campos diferidos y no modelo paralelo.
    - TEST-HU-004: hu_state: selection exacta de 7 claves, opcional, valor inicial False.
    - TEST-HU-005: hu_class: selection exacta de 5 claves, opcional, valor inicial False.
    - TEST-HU-006: Persistencia: asignación, lectura, actualización y reseteo a False.
    - TEST-HU-007: Contenido nativo: agregar/retirar quants no auto-muta hu_state ni hu_class.
    - TEST-HU-008: Independencia de package_type_id y PLM: package_type_id no auto-infiere hu_class;
                   PLM no ejecuta enforcement automático.
    - TEST-HU-009: Seguridad heredada: Plain Internal y WMS Operator leen pero no escriben (AccessError);
                   Stock User lee y escribe.
    - TEST-HU-010: Integridad de contrato nativo: name, parent_path, location_id, company_id, valid_sscc
                   y métodos nativos (unpack) intactos.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Package = cls.env["stock.package"]
        cls.PackageType = cls.env["stock.package.type"]
        cls.Location = cls.env["stock.location"]
        cls.Product = cls.env["product.product"]
        cls.Quant = cls.env["stock.quant"]
        cls.Users = cls.env["res.users"]
        cls.Company = cls.env.company

        # Ubicación interna
        cls.loc_internal = cls.Location.create({
            "name": "LOC-HU-INTERNAL",
            "usage": "internal",
            "company_id": cls.Company.id,
        })

        # Tipos de paquete nativos
        cls.pkg_type_pallet = cls.PackageType.create({
            "name": "Euro Pallet Standard",
            "barcode": "PKG-TYPE-PALLET-01",
        })
        cls.pkg_type_box = cls.PackageType.create({
            "name": "Cardboard Box Standard",
            "barcode": "PKG-TYPE-BOX-01",
        })

        # Producto
        cls.product_a = cls.Product.create({
            "name": "Product Alpha HU",
            "type": "consu",
            "is_storable": True,
            "company_id": cls.Company.id,
        })

        # Grupos y usuarios para RBAC
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_stock_user = cls.env.ref("stock.group_stock_user")

        cls.user_plain = cls.Users.create({
            "name": "WMS HU Plain Internal",
            "login": "wms_hu_plain",
            "email": "hu_plain@test.com",
            "company_id": cls.Company.id,
            "company_ids": [(6, 0, [cls.Company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id])],
        })
        cls.user_operator = cls.Users.create({
            "name": "WMS HU Operator",
            "login": "wms_hu_operator",
            "email": "hu_operator@test.com",
            "company_id": cls.Company.id,
            "company_ids": [(6, 0, [cls.Company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_operator.id])],
        })
        cls.user_stock = cls.Users.create({
            "name": "WMS HU Stock User",
            "login": "wms_hu_stock_user",
            "email": "hu_stock_user@test.com",
            "company_id": cls.Company.id,
            "company_ids": [(6, 0, [cls.Company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_stock_user.id])],
        })

    # ------------------------------------------------------------------
    # TEST-HU-003: Extensión de modelo y límites estrictos de alcance
    # ------------------------------------------------------------------

    def test_hu_03_model_extension_and_scope_boundary(self):
        """HU-003: _inherit = stock.package, existen exactamente hu_state y hu_class, y no campos diferidos."""
        # 1. Existencia de campos WMS en stock.package
        self.assertIn("hu_state", self.Package._fields)
        self.assertIn("hu_class", self.Package._fields)

        # 2. Ausencia de campos deliberadamente diferidos
        deferred_fields = [
            "seal_number",
            "sscc",
            "gtin",
            "label_state",
            "current_work_id",
            "last_work_id",
            "weight_gross",
            "weight_net",
        ]
        for f in deferred_fields:
            self.assertNotIn(f, self.Package._fields, f"El campo '{f}' debe estar diferido y no existir en HU-002")

        # 3. Invariante ADR-013: Prohibido modelo paralelo
        self.assertNotIn("wms.handling.unit", self.env)

    # ------------------------------------------------------------------
    # TEST-HU-004: Catálogo y valor inicial de hu_state
    # ------------------------------------------------------------------

    def test_hu_04_hu_state_selection_and_initial_value(self):
        """HU-004: hu_state tiene 7 valores exactos, required=False e inicializa en False."""
        field = self.Package._fields["hu_state"]
        self.assertEqual(field.type, "selection")
        self.assertFalse(field.required)
        self.assertTrue(field.index)
        self.assertFalse(field.copy)

        expected_states = {
            "EMPTY": "Vacía",
            "OPEN": "Abierta",
            "CLOSED": "Cerrada",
            "IN_TRANSIT": "En tránsito",
            "SHIPPED": "Despachada",
            "RETURNED": "Devuelta",
            "DISPOSED": "Dada de baja",
        }
        selection_dict = dict(field.selection)
        self.assertEqual(selection_dict, expected_states)

        # Creación sin hu_state -> False inicial (lifecycle WMS no inicializado)
        pkg = self.Package.create({"name": "PKG-STATE-TEST-01"})
        self.assertFalse(pkg.hu_state)
        self.assertIs(pkg.hu_state, False)

    # ------------------------------------------------------------------
    # TEST-HU-005: Catálogo y valor inicial de hu_class
    # ------------------------------------------------------------------

    def test_hu_05_hu_class_selection_and_initial_value(self):
        """HU-005: hu_class tiene 5 valores exactos, required=False e inicializa en False."""
        field = self.Package._fields["hu_class"]
        self.assertEqual(field.type, "selection")
        self.assertFalse(field.required)
        self.assertTrue(field.index)
        self.assertFalse(field.copy)

        expected_classes = {
            "PALLET": "Pallet",
            "CASE": "Caja",
            "TOTE": "Tote",
            "CONTAINER": "Contenedor",
            "MIXED": "Mixta",
        }
        selection_dict = dict(field.selection)
        self.assertEqual(selection_dict, expected_classes)

        # Creación sin hu_class -> False inicial (sin clasificación asignada)
        pkg = self.Package.create({"name": "PKG-CLASS-TEST-01"})
        self.assertFalse(pkg.hu_class)
        self.assertIs(pkg.hu_class, False)

    # ------------------------------------------------------------------
    # TEST-HU-006: Persistencia y reseteo de metadatos WMS
    # ------------------------------------------------------------------

    def test_hu_06_metadata_persistence_and_reset(self):
        """HU-006: hu_state y hu_class pueden asignarse, leerse, actualizarse y limpiarse a False."""
        pkg = self.Package.create({
            "name": "PKG-PERSIST-01",
            "hu_state": "OPEN",
            "hu_class": "PALLET",
        })
        original_id = pkg.id
        original_name = pkg.name
        self.assertEqual(pkg.hu_state, "OPEN")
        self.assertEqual(pkg.hu_class, "PALLET")

        # Actualización de valores
        pkg.write({
            "hu_state": "CLOSED",
            "hu_class": "CONTAINER",
        })
        self.assertEqual(pkg.hu_state, "CLOSED")
        self.assertEqual(pkg.hu_class, "CONTAINER")

        # Reseteo a False
        pkg.write({
            "hu_state": False,
            "hu_class": False,
        })
        self.assertFalse(pkg.hu_state)
        self.assertFalse(pkg.hu_class)
        self.assertEqual(pkg.id, original_id)
        self.assertEqual(pkg.name, original_name)

    # ------------------------------------------------------------------
    # TEST-HU-007: Mutación de contenido nativo no altera metadatos WMS
    # ------------------------------------------------------------------

    def test_hu_07_native_content_mutation_no_automatic_wms_state(self):
        """HU-007: Agregar o retirar quants nativos no muta automáticamente hu_state ni hu_class."""
        pkg = self.Package.create({"name": "PKG-CONTENT-TEST-01"})
        self.assertFalse(pkg.hu_state)
        self.assertFalse(pkg.hu_class)

        # 1. Agregar contenido físico mediante API nativa
        self.Quant._update_available_quantity(self.product_a, self.loc_internal, 10.0, package_id=pkg)
        pkg.invalidate_recordset(["quant_ids", "hu_state", "hu_class"])
        self.assertTrue(pkg.quant_ids)
        self.assertFalse(pkg.hu_state, "Agregar contenido no debe auto-mutar hu_state a OPEN ni EMPTY")
        self.assertFalse(pkg.hu_class, "Agregar contenido no debe auto-mutar hu_class")

        # 2. Retirar contenido físico mediante API nativa
        self.Quant._update_available_quantity(self.product_a, self.loc_internal, -10.0, package_id=pkg)
        pkg.invalidate_recordset(["quant_ids", "hu_state", "hu_class"])
        self.assertFalse(pkg.quant_ids)
        self.assertFalse(pkg.hu_state, "Retirar contenido no debe auto-mutar hu_state a EMPTY")
        self.assertFalse(pkg.hu_class, "Retirar contenido no debe auto-mutar hu_class")

    # ------------------------------------------------------------------
    # TEST-HU-008: Independencia de package_type_id y PLM
    # ------------------------------------------------------------------

    def test_hu_08_package_type_and_plm_independence(self):
        """HU-008: package_type_id no auto-infiere hu_class y restricciones PLM no se ejecutan automáticamente."""
        # 1. Asignar package_type_id Euro Pallet -> hu_class permanece False
        pkg = self.Package.create({
            "name": "PKG-TYPE-TEST-01",
            "package_type_id": self.pkg_type_pallet.id,
        })
        self.assertFalse(pkg.hu_class, "package_type_id no debe auto-inferir hu_class")

        # Cambiar package_type_id a Box -> hu_class sigue False
        pkg.write({"package_type_id": self.pkg_type_box.id})
        self.assertFalse(pkg.hu_class)

        # 2. Perfil PLM con restricciones de HU
        plm = self.env["wms.product.logistics"].create({
            "product_tmpl_id": self.product_a.product_tmpl_id.id,
            "allowed_hu_type_ids": [(6, 0, [self.pkg_type_pallet.id])],
            "default_hu_type_id": self.pkg_type_pallet.id,
        })
        self.assertEqual(plm.default_hu_type_id, self.pkg_type_pallet)

        # Crear paquete con pkg_type_box (no permitido por PLM) no lanza error porque HU-002 no tiene auto-enforcement
        pkg_unrestricted = self.Package.create({
            "name": "PKG-PLM-UNRESTRICTED-01",
            "package_type_id": self.pkg_type_box.id,
        })
        self.assertTrue(pkg_unrestricted)
        self.assertFalse(pkg_unrestricted.hu_class)

    # ------------------------------------------------------------------
    # TEST-HU-009: Control de acceso RBAC heredado de stock.package
    # ------------------------------------------------------------------

    def test_hu_09_inherited_rbac_security(self):
        """HU-009: Plain Internal y WMS Operator leen pero no escriben; Stock User tiene lectura y escritura."""
        pkg = self.Package.create({
            "name": "PKG-RBAC-01",
            "hu_state": "OPEN",
            "hu_class": "TOTE",
        })

        # 1. Plain Internal: Lectura permitida, Escritura prohibida (AccessError)
        read_data = pkg.with_user(self.user_plain).read(["hu_state", "hu_class"])
        self.assertEqual(read_data[0]["hu_state"], "OPEN")
        self.assertEqual(read_data[0]["hu_class"], "TOTE")
        with self.assertRaises(AccessError):
            pkg.with_user(self.user_plain).write({"hu_state": "CLOSED"})

        # 2. WMS Operator: Lectura permitida, Escritura prohibida sin stock.group_stock_user (AccessError)
        read_op = pkg.with_user(self.user_operator).read(["hu_state", "hu_class"])
        self.assertEqual(read_op[0]["hu_state"], "OPEN")
        with self.assertRaises(AccessError):
            pkg.with_user(self.user_operator).write({"hu_state": "CLOSED"})

        # 3. Stock User: Lectura y Escritura permitidas
        pkg.with_user(self.user_stock).write({
            "hu_state": "CLOSED",
            "hu_class": "MIXED",
        })
        self.assertEqual(pkg.hu_state, "CLOSED")
        self.assertEqual(pkg.hu_class, "MIXED")

    # ------------------------------------------------------------------
    # TEST-HU-010: Integridad del contrato y métodos nativos de paquete
    # ------------------------------------------------------------------

    def test_hu_010_native_package_contract_integrity(self):
        """HU-010: Metadatos WMS no alteran name, jerarquía, location_id, company_id, valid_sscc ni unpack()."""
        parent_pkg = self.Package.create({
            "name": "PARENT-PKG-01",
            "hu_state": "OPEN",
            "hu_class": "PALLET",
        })
        child_pkg = self.Package.create({
            "name": "CHILD-PKG-01",
            "parent_package_id": parent_pkg.id,
            "hu_state": "OPEN",
            "hu_class": "CASE",
        })

        # Nombres de paquete intactos
        self.assertEqual(parent_pkg.name, "PARENT-PKG-01")
        self.assertEqual(child_pkg.name, "CHILD-PKG-01")

        # Jerarquía nativa
        self.assertEqual(child_pkg.parent_package_id, parent_pkg)
        self.assertIn(child_pkg, parent_pkg.child_package_ids)
        self.assertTrue(child_pkg.parent_path.startswith(parent_pkg.parent_path))

        # Agregar quant en child_pkg
        self.Quant._update_available_quantity(self.product_a, self.loc_internal, 5.0, package_id=child_pkg)
        self.assertEqual(child_pkg.location_id, self.loc_internal)
        self.assertEqual(parent_pkg.location_id, self.loc_internal)
        self.assertEqual(child_pkg.company_id, self.Company)
        self.assertEqual(parent_pkg.company_id, self.Company)
        self.assertEqual(parent_pkg.name, "PARENT-PKG-01")
        self.assertEqual(child_pkg.name, "CHILD-PKG-01")

        # valid_sscc nativo funciona normalmente
        self.assertFalse(parent_pkg.valid_sscc)

        # Desempaquetado nativo (unpack) funciona normalmente
        child_pkg.unpack()
        self.assertFalse(child_pkg.quant_ids)
