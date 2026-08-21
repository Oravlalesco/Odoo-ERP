from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools.barcode import check_barcode_encoding


class TestStockPackageSsccAssignment(TransactionCase):
    """Pruebas unitarias para la asignación de SSCC a stock.package (HU-003B).

    Valida:
    - TEST-HU-020: Existencia de API assign_sscc(), cero campos/modelos nuevos, contrato estricto de ID.
    - TEST-HU-021: Happy path: asignación de SSCC a paquete company-bound, valid_sscc=True, 1 consumo.
    - TEST-HU-022: Idempotencia: segunda llamada no consume allocator; SSCC externo preexistente no se reemplaza.
    - TEST-HU-023: Company guard: rechazo ante company_id=False y company mismatch antes de next_sscc().
    - TEST-HU-024: Matriz RBAC de intersección WMS + Stock User exacta; cero sudo.
    - TEST-HU-025: Guard de colisión visible lanza ValidationError, 1 intento, target package intacto.
    - TEST-HU-026: Fallos del allocator (inactivo, config inválida, capacidad agotada) dejan el paquete intacto.
    - TEST-HU-027: Preservación integral de atributos, jerarquía, ubicación, metadata WMS y quants.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.SsccSequence = cls.env["wms.sscc.sequence"]
        cls.IrSequence = cls.env["ir.sequence"]
        cls.Package = cls.env["stock.package"]
        cls.PackageType = cls.env["stock.package.type"]
        cls.Location = cls.env["stock.location"]
        cls.Product = cls.env["product.product"]
        cls.Quant = cls.env["stock.quant"]
        cls.PackageHistory = cls.env["stock.package.history"]
        cls.Company = cls.env.company
        cls.Users = cls.env["res.users"]

        # Segunda compañía para pruebas multi-compañía
        cls.company_secondary = cls.env["res.company"].create({
            "name": "Secondary Co SSCC Assignment",
        })

        # Ubicaciones internas
        cls.loc_main = cls.Location.search([
            ("usage", "=", "internal"),
            ("company_id", "in", [cls.Company.id, False]),
        ], limit=1)
        if not cls.loc_main:
            cls.loc_main = cls.Location.create({
                "name": "Main Internal Loc",
                "usage": "internal",
                "company_id": cls.Company.id,
            })

        cls.loc_sec = cls.Location.create({
            "name": "Sec Internal Loc",
            "usage": "internal",
            "company_id": cls.company_secondary.id,
        })

        # Producto para contenido de prueba
        cls.product = cls.Product.create({
            "name": "Standard Test Product",
            "is_storable": True,
        })

        # Tipo de paquete
        cls.package_type = cls.PackageType.create({
            "name": "Euro Pallet Type",
            "packaging_length": 1200,
            "width": 800,
            "height": 144,
            "base_weight": 25.0,
            "max_weight": 1500.0,
        })

        # Secuencia e ir.sequence para compañía principal
        cls.raw_seq_main = cls.IrSequence.create({
            "name": "Raw SSCC Seq Main",
            "code": "wms.sscc.raw.assign.main",
            "company_id": cls.Company.id,
            "number_increment": 1,
            "number_next_actual": 1,
            "use_date_range": False,
        })
        cls.allocator_main = cls.SsccSequence.create({
            "name": "SSCC Allocator Main",
            "company_id": cls.Company.id,
            "gs1_company_prefix": "7601234",
            "extension_digit": "0",
            "sequence_id": cls.raw_seq_main.id,
        })

        # Secuencia e ir.sequence para compañía secundaria
        cls.raw_seq_sec = cls.IrSequence.create({
            "name": "Raw SSCC Seq Sec",
            "code": "wms.sscc.raw.assign.sec",
            "company_id": cls.company_secondary.id,
            "number_increment": 1,
            "number_next_actual": 1,
            "use_date_range": False,
        })
        cls.allocator_sec = cls.SsccSequence.create({
            "name": "SSCC Allocator Sec",
            "company_id": cls.company_secondary.id,
            "gs1_company_prefix": "8412345",
            "extension_digit": "1",
            "sequence_id": cls.raw_seq_sec.id,
        })

        # Grupos de seguridad
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_supervisor = cls.env.ref("wms_core.group_wms_supervisor")
        cls.group_manager = cls.env.ref("wms_core.group_wms_manager")
        cls.group_stock_user = cls.env.ref("stock.group_stock_user")
        cls.group_stock_manager = cls.env.ref("stock.group_stock_manager")

        # Usuarios para matriz RBAC
        # 1. WMS Only
        cls.user_wms_operator_only = cls._create_test_user("u_wms_op_only", [cls.group_operator.id])
        cls.user_wms_supervisor_only = cls._create_test_user("u_wms_sup_only", [cls.group_supervisor.id])
        cls.user_wms_manager_only = cls._create_test_user("u_wms_mgr_only", [cls.group_manager.id])

        # 2. Stock Only
        cls.user_stock_user_only = cls._create_test_user("u_stock_usr_only", [cls.group_stock_user.id])
        cls.user_stock_manager_only = cls._create_test_user("u_stock_mgr_only", [cls.group_stock_manager.id])

        # 3. Intersección WMS + Stock User
        cls.user_wms_op_stock_user = cls._create_test_user(
            "u_wms_op_stk_usr", [cls.group_operator.id, cls.group_stock_user.id]
        )
        cls.user_wms_sup_stock_user = cls._create_test_user(
            "u_wms_sup_stk_usr", [cls.group_supervisor.id, cls.group_stock_user.id]
        )
        cls.user_wms_mgr_stock_user = cls._create_test_user(
            "u_wms_mgr_stk_usr", [cls.group_manager.id, cls.group_stock_user.id]
        )

    @classmethod
    def _create_test_user(cls, login, group_ids):
        """Helper para crear usuario con compañía principal y grupos específicos."""
        all_groups = [cls.group_internal.id] + group_ids
        return cls.Users.create({
            "name": f"User {login}",
            "login": login,
            "email": f"{login}@test.com",
            "company_id": cls.Company.id,
            "company_ids": [(6, 0, [cls.Company.id])],
            "group_ids": [(6, 0, all_groups)],
        })

    def _create_company_bound_package(self, name="PACK-TEST-01", company=None, location=None, hu_state=False, hu_class=False):
        """Crear paquete con quant para garantizar resolución nativa de company_id."""
        target_company = company or self.Company
        target_loc = location or self.loc_main
        pkg = self.Package.create({
            "name": name,
            "hu_state": hu_state,
            "hu_class": hu_class,
        })
        self.Quant.create({
            "product_id": self.product.id,
            "location_id": target_loc.id,
            "package_id": pkg.id,
            "quantity": 10.0,
            "company_id": target_company.id,
        })
        self.assertEqual(pkg.company_id, target_company, "El paquete debe tener compañía resuelta mediante su quant")
        return pkg

    # ------------------------------------------------------------------
    # TEST-HU-020: Existencia de API y contrato estricto de ID
    # ------------------------------------------------------------------

    def test_hu_020_api_existence_and_strict_id_contract(self):
        """HU-020: assign_sscc() existe; cero campos/modelos nuevos; rechaza False, 0, string, recordset y ID inexistente."""
        # 1. API pública callable
        self.assertTrue(callable(getattr(self.Package, "assign_sscc", None)))

        # 2. Cero campos nuevos en stock.package (sscc ausente)
        self.assertNotIn("sscc", self.Package._fields, "El campo 'sscc' no debe existir en stock.package")

        # 3. Invariante ADR-013: Prohibido modelo paralelo
        self.assertNotIn("wms.handling.unit", self.env)

        # 4. Rechazo estricto de argumentos no conformes
        pkg = self._create_company_bound_package(name="PACK-HU020")
        invalid_args = [
            False,
            True,
            0,
            -1,
            "1",
            "invalid",
            self.allocator_main,  # recordset prohibido
            999999,  # ID inexistente
        ]
        for arg in invalid_args:
            with self.assertRaises(ValidationError, msg=f"El argumento '{arg}' no fue rechazado"):
                pkg.assign_sscc(arg)

    # ------------------------------------------------------------------
    # TEST-HU-021: Happy path de asignación de SSCC
    # ------------------------------------------------------------------

    def test_hu_021_happy_path_sscc_assignment(self):
        """HU-021: Happy path: name genérico reemplazado por SSCC válido de 18 dígitos, valid_sscc=True, 1 consumo."""
        pkg = self._create_company_bound_package(name="PACK-GEN-001")
        pkg_id = pkg.id
        self.assertFalse(pkg.valid_sscc)

        with patch.object(type(self.allocator_main), "next_sscc", wraps=self.allocator_main.next_sscc) as spy_alloc:
            assigned_name = pkg.assign_sscc(self.allocator_main.id)
            self.assertEqual(spy_alloc.call_count, 1, "Debe realizarse exactamente 1 llamada al asignador")

        # Verificaciones
        self.assertEqual(pkg.id, pkg_id, "El ID del paquete debe ser exactamente el mismo")
        self.assertEqual(assigned_name, pkg.name)
        self.assertEqual(len(pkg.name), 18)
        self.assertTrue(pkg.name.isascii())
        self.assertTrue(pkg.name.isdigit())
        self.assertTrue(check_barcode_encoding(pkg.name, "sscc"))
        self.assertTrue(pkg.valid_sscc, "El campo computado valid_sscc debe quedar en True")

    # ------------------------------------------------------------------
    # TEST-HU-022: Idempotencia y preservación de SSCC externo
    # ------------------------------------------------------------------

    def test_hu_022_idempotency_and_external_sscc_preservation(self):
        """HU-022: Segunda llamada devuelve mismo name y 0 consumos; SSCC externo tampoco se reemplaza y consume 0."""
        # Caso A: Genérico asignado -> segunda llamada idempotente
        pkg_a = self._create_company_bound_package(name="PACK-IDEMP-01")
        sscc_first = pkg_a.assign_sscc(self.allocator_main.id)
        self.assertTrue(pkg_a.valid_sscc)

        with patch.object(type(self.allocator_main), "next_sscc", wraps=self.allocator_main.next_sscc) as spy_alloc:
            sscc_second = pkg_a.assign_sscc(self.allocator_main.id)
            self.assertEqual(spy_alloc.call_count, 0, "La llamada idempotente no debe consumir el asignador")
            self.assertEqual(sscc_first, sscc_second, "El SSCC retornado debe ser idéntico")
            self.assertEqual(pkg_a.name, sscc_first)

        # Caso B: Paquete con SSCC externo preexistente
        external_valid_sscc = "176012340000000011"  # 18 dígitos con check digit válido
        self.assertTrue(check_barcode_encoding(external_valid_sscc, "sscc"))
        pkg_b = self._create_company_bound_package(name=external_valid_sscc)
        self.assertTrue(pkg_b.valid_sscc)

        with patch.object(type(self.allocator_main), "next_sscc", wraps=self.allocator_main.next_sscc) as spy_alloc:
            sscc_ext_result = pkg_b.assign_sscc(self.allocator_main.id)
            self.assertEqual(spy_alloc.call_count, 0, "SSCC externo válido no debe consumir el asignador")
            self.assertEqual(sscc_ext_result, external_valid_sscc)
            self.assertEqual(pkg_b.name, external_valid_sscc)

    # ------------------------------------------------------------------
    # TEST-HU-023: Guards de resolución y coherencia de compañía
    # ------------------------------------------------------------------

    def test_hu_023_company_resolution_and_mismatch_guards(self):
        """HU-023: Paquete con company_id=False o company mismatch fallan con ValidationError antes de llamar next_sscc."""
        # 1. Paquete vacío sin quants (company_id=False)
        empty_pkg = self.Package.create({"name": "PACK-EMPTY-NOCOMP"})
        self.assertFalse(empty_pkg.company_id)

        with patch.object(type(self.allocator_main), "next_sscc", wraps=self.allocator_main.next_sscc) as spy_alloc:
            with self.assertRaises(ValidationError):
                empty_pkg.assign_sscc(self.allocator_main.id)
            self.assertEqual(spy_alloc.call_count, 0, "No debe llamarse next_sscc si company_id es False")

        # 2. Company mismatch: paquete de compañía principal con asignador de compañía secundaria
        pkg_main = self._create_company_bound_package(name="PACK-MAIN-MISMATCH", company=self.Company)
        with patch.object(type(self.allocator_sec), "next_sscc", wraps=self.allocator_sec.next_sscc) as spy_alloc:
            with self.assertRaises(ValidationError):
                pkg_main.assign_sscc(self.allocator_sec.id)
            self.assertEqual(spy_alloc.call_count, 0, "No debe llamarse next_sscc si hay discrepancia de compañía")

    # ------------------------------------------------------------------
    # TEST-HU-024: Matriz RBAC de intersección WMS + Stock User
    # ------------------------------------------------------------------

    def test_hu_024_rbac_intersection_matrix(self):
        """HU-024: WMS-only y Stock-only reciben AccessError; la intersección WMS + Stock User permite asignación exitosa."""
        pkg = self._create_company_bound_package(name="PACK-RBAC-01")

        # 1. WMS puro (sin Stock User) -> AccessError al intentar write sobre stock.package
        with self.assertRaises(AccessError):
            pkg.with_user(self.user_wms_operator_only).assign_sscc(self.allocator_main.id)

        with self.assertRaises(AccessError):
            pkg.with_user(self.user_wms_supervisor_only).assign_sscc(self.allocator_main.id)

        with self.assertRaises(AccessError):
            pkg.with_user(self.user_wms_manager_only).assign_sscc(self.allocator_main.id)

        # 2. Stock puro (sin rol WMS) -> AccessError al intentar read sobre wms.sscc.sequence
        with self.assertRaises(AccessError):
            pkg.with_user(self.user_stock_user_only).assign_sscc(self.allocator_main.id)

        with self.assertRaises(AccessError):
            pkg.with_user(self.user_stock_manager_only).assign_sscc(self.allocator_main.id)

        # 3. Intersección WMS + Stock User -> Asignación exitosa
        pkg_op = self._create_company_bound_package(name="PACK-RBAC-OP")
        sscc_op = pkg_op.with_user(self.user_wms_op_stock_user).assign_sscc(self.allocator_main.id)
        self.assertTrue(check_barcode_encoding(sscc_op, "sscc"))

        pkg_sup = self._create_company_bound_package(name="PACK-RBAC-SUP")
        sscc_sup = pkg_sup.with_user(self.user_wms_sup_stock_user).assign_sscc(self.allocator_main.id)
        self.assertTrue(check_barcode_encoding(sscc_sup, "sscc"))

        pkg_mgr = self._create_company_bound_package(name="PACK-RBAC-MGR")
        sscc_mgr = pkg_mgr.with_user(self.user_wms_mgr_stock_user).assign_sscc(self.allocator_main.id)
        self.assertTrue(check_barcode_encoding(sscc_mgr, "sscc"))

    # ------------------------------------------------------------------
    # TEST-HU-025: Guard de colisión visible
    # ------------------------------------------------------------------

    def test_hu_025_visible_collision_guard(self):
        """HU-025: Colisión con otro paquete visible lanza ValidationError, 1 intento, sin retry y target name intacto."""
        collision_sscc = "076012340000000052"
        self.assertTrue(check_barcode_encoding(collision_sscc, "sscc"))

        # Paquete preexistente ocupando el código
        self._create_company_bound_package(name=collision_sscc)

        # Paquete objetivo
        pkg_target = self._create_company_bound_package(name="PACK-TARGET-COLLIDE")

        # Forzar que el allocator devuelva el SSCC colisionante
        with patch.object(type(self.allocator_main), "next_sscc", return_value=collision_sscc) as spy_alloc:
            with self.assertRaises(ValidationError):
                pkg_target.assign_sscc(self.allocator_main.id)
            self.assertEqual(spy_alloc.call_count, 1, "Debe realizarse exactamente 1 intento sin reintento automático")

        # El paquete objetivo conserva su nombre original intacto
        self.assertEqual(pkg_target.name, "PACK-TARGET-COLLIDE")
        self.assertFalse(pkg_target.valid_sscc)

    # ------------------------------------------------------------------
    # TEST-HU-026: Fallos del allocator dejan el paquete intacto
    # ------------------------------------------------------------------

    def test_hu_026_allocator_failure_leaves_package_unchanged(self):
        """HU-026: Allocator inactivo, config inválida o capacidad agotada lanzan ValidationError y dejan el paquete intacto en cada caso."""
        pkg = self._create_company_bound_package(
            name="PACK-FAIL-SAFE",
            hu_state="OPEN",
            hu_class="PALLET",
        )
        orig_name = pkg.name
        orig_state = pkg.hu_state
        orig_class = pkg.hu_class
        orig_quants = pkg.quant_ids
        orig_qty = pkg.quant_ids.quantity

        def _assert_package_invariants(msg_context):
            self.assertEqual(pkg.name, orig_name, f"El nombre del paquete debe permanecer intacto tras fallo ({msg_context})")
            self.assertEqual(pkg.hu_state, orig_state, f"El hu_state debe permanecer intacto tras fallo ({msg_context})")
            self.assertEqual(pkg.hu_class, orig_class, f"El hu_class debe permanecer intacto tras fallo ({msg_context})")
            self.assertEqual(pkg.quant_ids, orig_quants, f"Los quants deben permanecer intactos tras fallo ({msg_context})")
            self.assertEqual(pkg.quant_ids.quantity, orig_qty, f"La cantidad del quant debe permanecer intacta tras fallo ({msg_context})")

        # 1. Allocator inactivo
        self.allocator_main.write({"active": False})
        with self.assertRaises(ValidationError):
            pkg.assign_sscc(self.allocator_main.id)
        _assert_package_invariants("allocator inactivo")
        self.allocator_main.write({"active": True})

        # 2. Configuración de ir.sequence inválida (con prefijo)
        self.raw_seq_main.write({"prefix": "PRE-"})
        with self.assertRaises(ValidationError):
            pkg.assign_sscc(self.allocator_main.id)
        _assert_package_invariants("configuración inválida con prefijo")
        self.raw_seq_main.write({"prefix": False})

        # 3. Capacidad de serial agotada (GCP 12 con serial 10000)
        seq_capacity = self.IrSequence.create({
            "name": "Seq Capacity Assignment Fail",
            "company_id": self.Company.id,
            "number_increment": 1,
            "number_next_actual": 10000,
        })
        alloc_exhausted = self.SsccSequence.create({
            "name": "Alloc Exhausted",
            "company_id": self.Company.id,
            "gs1_company_prefix": "001234567890",
            "extension_digit": "9",
            "sequence_id": seq_capacity.id,
        })
        with self.assertRaises(ValidationError):
            pkg.assign_sscc(alloc_exhausted.id)
        _assert_package_invariants("capacidad agotada")

    # ------------------------------------------------------------------
    # TEST-HU-027: Preservación integral de atributos y contenido
    # ------------------------------------------------------------------

    def test_hu_027_assignment_preserves_package_attributes_and_content(self):
        """HU-027: assign_sscc() sólo cambia name; preserva jerarquía, tipo, quants, ubicación, compañía, metadata WMS y 0 history."""
        parent_pkg = self.Package.create({"name": "PARENT-PALLET-HU027"})

        child_pkg = self.Package.create({
            "name": "CHILD-CASE-HU027",
            "package_type_id": self.package_type.id,
            "parent_package_id": parent_pkg.id,
            "hu_state": "OPEN",
            "hu_class": "CASE",
        })

        quant = self.Quant.create({
            "product_id": self.product.id,
            "location_id": self.loc_main.id,
            "package_id": child_pkg.id,
            "quantity": 25.0,
            "company_id": self.Company.id,
        })

        # Captura de estado previo
        pkg_id_orig = child_pkg.id
        pkg_type_orig = child_pkg.package_type_id
        parent_orig = child_pkg.parent_package_id
        quants_orig = child_pkg.quant_ids
        loc_orig = child_pkg.location_id
        comp_orig = child_pkg.company_id
        state_orig = child_pkg.hu_state
        class_orig = child_pkg.hu_class
        total_packages_before = self.Package.search_count([])
        history_before = self.PackageHistory.search_count([])

        # Asignación de SSCC
        new_sscc = child_pkg.assign_sscc(self.allocator_main.id)

        # Verificaciones
        self.assertEqual(child_pkg.id, pkg_id_orig)
        self.assertEqual(child_pkg.name, new_sscc)
        self.assertNotEqual(child_pkg.name, "CHILD-CASE-HU027")
        self.assertTrue(child_pkg.valid_sscc)

        # Invariantes preservados
        self.assertEqual(child_pkg.package_type_id, pkg_type_orig)
        self.assertEqual(child_pkg.parent_package_id, parent_orig)
        self.assertEqual(child_pkg.quant_ids, quants_orig)
        self.assertEqual(child_pkg.quant_ids.quantity, 25.0)
        self.assertEqual(child_pkg.location_id, loc_orig)
        self.assertEqual(child_pkg.company_id, comp_orig)
        self.assertEqual(child_pkg.hu_state, state_orig)
        self.assertEqual(child_pkg.hu_class, class_orig)

        # Cero paquetes adicionales y cero registros de historial creados
        total_packages_after = self.Package.search_count([])
        self.assertEqual(total_packages_before, total_packages_after, "El número total de paquetes no debe cambiar")

        history_after = self.PackageHistory.search_count([])
        self.assertEqual(history_before, history_after, "La asignación de SSCC no debe generar registros en stock.package.history")
