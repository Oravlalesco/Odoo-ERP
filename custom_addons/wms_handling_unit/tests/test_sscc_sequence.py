from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools.barcode import check_barcode_encoding, get_barcode_check_digit
from odoo.tools.misc import mute_logger


class TestWmsSsccSequence(TransactionCase):
    """Pruebas unitarias para el asignador SSCC-18 wms.sscc.sequence (HU-003A).

    Valida:
    - TEST-HU-011: Modelo, campos funcionales exactos, ausencia de wms.handling.unit y stock.package.sscc.
    - TEST-HU-012: Validación de GCP (4..12 dígitos, leading zeros, rechazo de inválidos).
    - TEST-HU-013: Dígito de extensión 0..9 con catálogo exacto, sin default, unicidad (company, GCP, extension).
    - TEST-HU-014: Generación y estructura de SSCC válido de 18 dígitos verificado con check_barcode_encoding.
    - TEST-HU-015: Longitud de serial según GCP (GCP 4 -> serial 12, GCP 12 -> serial 4, zero-padding).
    - TEST-HU-016: Unicidad secuencial y consumo de exactamente 1 serial por llamada demostrado.
    - TEST-HU-017: Rechazo de configuraciones inválidas en ir.sequence, allocator inactivo sin consumo y salida no numérica.
    - TEST-HU-018: Agotamiento de capacidad (GCP 12 con serial 9999 -> válido, 10000 -> ValidationError).
    - TEST-HU-019: Seguridad RBAC (Manager CRUD completo), multi-compañía y preservación de packages existentes.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.SsccSequence = cls.env["wms.sscc.sequence"]
        cls.IrSequence = cls.env["ir.sequence"]
        cls.Package = cls.env["stock.package"]
        cls.Company = cls.env.company
        cls.Users = cls.env["res.users"]

        # Segunda compañía para pruebas multi-compañía
        cls.company_secondary = cls.env["res.company"].create({
            "name": "Secondary Company SSCC",
        })

        # Secuencia estándar para compañía principal
        cls.raw_seq_main = cls.IrSequence.create({
            "name": "Raw SSCC Counter Main",
            "code": "wms.sscc.raw.main",
            "company_id": cls.Company.id,
            "padding": 0,
            "number_increment": 1,
            "number_next_actual": 1,
            "use_date_range": False,
        })

        # Grupos de seguridad
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_supervisor = cls.env.ref("wms_core.group_wms_supervisor")
        cls.group_manager = cls.env.ref("wms_core.group_wms_manager")
        cls.group_internal = cls.env.ref("base.group_user")

        # Usuarios para pruebas RBAC
        cls.user_operator = cls.Users.create({
            "name": "WMS SSCC Operator",
            "login": "wms_sscc_operator",
            "email": "sscc_operator@test.com",
            "company_id": cls.Company.id,
            "company_ids": [(6, 0, [cls.Company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_operator.id])],
        })
        cls.user_supervisor = cls.Users.create({
            "name": "WMS SSCC Supervisor",
            "login": "wms_sscc_supervisor",
            "email": "sscc_supervisor@test.com",
            "company_id": cls.Company.id,
            "company_ids": [(6, 0, [cls.Company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_supervisor.id])],
        })
        cls.user_manager = cls.Users.create({
            "name": "WMS SSCC Manager",
            "login": "wms_sscc_manager",
            "email": "sscc_manager@test.com",
            "company_id": cls.Company.id,
            "company_ids": [(6, 0, [cls.Company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_manager.id])],
        })
        cls.user_sec_operator = cls.Users.create({
            "name": "WMS SSCC Secondary Operator",
            "login": "wms_sscc_sec_operator",
            "email": "sscc_sec_op@test.com",
            "company_id": cls.company_secondary.id,
            "company_ids": [(6, 0, [cls.company_secondary.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_operator.id])],
        })

    # ------------------------------------------------------------------
    # TEST-HU-011: Existencia del modelo y fronteras de alcance
    # ------------------------------------------------------------------

    def test_hu_011_model_scope_and_package_independence(self):
        """HU-011: wms.sscc.sequence existe con 6 campos exactos; ausente wms.handling.unit y stock.package.sscc."""
        # 1. Modelo en registry
        self.assertIn("wms.sscc.sequence", self.env)

        # 2. Exactamente 6 campos funcionales
        expected_fields = [
            "name",
            "active",
            "company_id",
            "gs1_company_prefix",
            "extension_digit",
            "sequence_id",
        ]
        for f in expected_fields:
            self.assertIn(f, self.SsccSequence._fields, f"El campo '{f}' debe existir en wms.sscc.sequence")

        # 3. Invariante ADR-013: Prohibido modelo paralelo
        self.assertNotIn("wms.handling.unit", self.env)

        # 4. Prohibido campo sscc en stock.package
        self.assertNotIn("sscc", self.Package._fields, "El campo 'sscc' no debe existir en stock.package (se reutiliza name + valid_sscc)")

    # ------------------------------------------------------------------
    # TEST-HU-012: Validación de GCP (4..12 dígitos, leading zeros)
    # ------------------------------------------------------------------

    def test_hu_012_gcp_validation_boundaries_and_formats(self):
        """HU-012: GCP acepta 4 a 12 dígitos con ceros a izquierda; rechaza <4, >12, letras, espacios y caracteres no ASCII."""
        # Válidos: límites 4 y 12 dígitos, y ceros a la izquierda
        valid_gcps = ["1234", "12345", "7601234", "01234567", "001234567890"]
        for idx, gcp in enumerate(valid_gcps):
            seq = self.SsccSequence.create({
                "name": f"SSCC Valid GCP {idx}",
                "gs1_company_prefix": gcp,
                "extension_digit": str(idx % 10),
                "sequence_id": self.raw_seq_main.id,
            })
            self.assertEqual(seq.gs1_company_prefix, gcp)

        # Inválidos: rechazar con ValidationError
        invalid_gcps = [
            "123",            # < 4 dígitos
            "1234567890123",  # > 12 dígitos
            "12345A",         # contiene letra
            "1234 56",        # contiene espacio
            "1234-56",        # contiene guion
            "1234\u0660",     # unicode non-ascii digit
        ]
        for gcp in invalid_gcps:
            with self.assertRaises(ValidationError, msg=f"GCP inválido '{gcp}' no fue rechazado"):
                self.SsccSequence.create({
                    "name": f"SSCC Invalid GCP {gcp}",
                    "gs1_company_prefix": gcp,
                    "extension_digit": "0",
                    "sequence_id": self.raw_seq_main.id,
                })

    # ------------------------------------------------------------------
    # TEST-HU-013: Dígito de extensión y unicidad de namespace
    # ------------------------------------------------------------------

    def test_hu_013_extension_digit_and_namespace_uniqueness(self):
        """HU-013: extension_digit tiene catálogo exacto '0'..'9', sin default; duplicar (company, GCP, extension) falla."""
        field = self.SsccSequence._fields["extension_digit"]
        self.assertEqual(field.type, "selection")
        self.assertTrue(field.required)
        self.assertFalse(field.default)

        # 1. Catálogo exacto de 10 dígitos ("0".."9")
        expected_selection = [(str(i), str(i)) for i in range(10)]
        self.assertEqual(
            field.selection,
            expected_selection,
            "extension_digit debe tener exactamente los 10 dígitos '0' a '9' en su catálogo de selección",
        )

        # 2. Crear secuencia válida
        self.SsccSequence.create({
            "name": "SSCC Namespace Original",
            "gs1_company_prefix": "7601234",
            "extension_digit": "3",
            "sequence_id": self.raw_seq_main.id,
        })

        # 3. Duplicar (company, GCP, extension) en misma compañía -> error
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.SsccSequence.create({
                    "name": "SSCC Namespace Duplicate",
                    "gs1_company_prefix": "7601234",
                    "extension_digit": "3",
                    "sequence_id": self.raw_seq_main.id,
                })

    # ------------------------------------------------------------------
    # TEST-HU-014: Generación y estructura de SSCC válido de 18 dígitos
    # ------------------------------------------------------------------

    def test_hu_014_next_sscc_generation_and_structure(self):
        """HU-014: next_sscc() retorna string de 18 dígitos ASCII con checksum GS1 válido y estructura exacta."""
        seq_allocator = self.SsccSequence.create({
            "name": "SSCC Structure Test",
            "gs1_company_prefix": "7601234",  # 7 dígitos
            "extension_digit": "1",
            "sequence_id": self.raw_seq_main.id,
        })

        sscc = seq_allocator.next_sscc()

        # 1. Longitud y formato
        self.assertIsInstance(sscc, str)
        self.assertEqual(len(sscc), 18)
        self.assertTrue(sscc.isascii())
        self.assertTrue(sscc.isdigit())

        # 2. Validación nativa Odoo
        self.assertTrue(check_barcode_encoding(sscc, "sscc"))

        # 3. Estructura exacta
        self.assertEqual(sscc[0], "1", "El primer dígito debe ser el dígito de extensión")
        self.assertEqual(sscc[1:8], "7601234", "Los dígitos 1..7 deben coincidir con el GCP")
        self.assertEqual(sscc[8:17], "000000001", "Los dígitos 8..16 deben ser el serial con zero-padding de 9 dígitos")
        expected_check = get_barcode_check_digit(sscc[:17] + "0")
        self.assertEqual(int(sscc[17]), expected_check, "El dígito 18 debe ser el check digit módulo-10 exacto")

    # ------------------------------------------------------------------
    # TEST-HU-015: Ancho de serial según longitud de GCP
    # ------------------------------------------------------------------

    def test_hu_015_serial_width_and_zero_padding(self):
        """HU-015: GCP=4 produce serial de 12 dígitos; GCP=12 produce serial de 4 dígitos; preserva zero-padding."""
        # 1. GCP corto (4 dígitos) -> serial length = 16 - 4 = 12 dígitos
        raw_seq_4 = self.IrSequence.create({
            "name": "Counter GCP 4",
            "code": "wms.sscc.counter.gcp4",
            "company_id": self.Company.id,
            "number_increment": 1,
            "number_next_actual": 42,
        })
        allocator_4 = self.SsccSequence.create({
            "name": "SSCC GCP 4",
            "gs1_company_prefix": "1234",
            "extension_digit": "0",
            "sequence_id": raw_seq_4.id,
        })
        sscc_4 = allocator_4.next_sscc()
        self.assertEqual(len(sscc_4), 18)
        self.assertEqual(sscc_4[0], "0")
        self.assertEqual(sscc_4[1:5], "1234")
        self.assertEqual(sscc_4[5:17], "000000000042")  # 12 dígitos de serial con zero-pad
        self.assertTrue(check_barcode_encoding(sscc_4, "sscc"))

        # 2. GCP largo (12 dígitos) -> serial length = 16 - 12 = 4 dígitos
        raw_seq_12 = self.IrSequence.create({
            "name": "Counter GCP 12",
            "code": "wms.sscc.counter.gcp12",
            "company_id": self.Company.id,
            "number_increment": 1,
            "number_next_actual": 7,
        })
        allocator_12 = self.SsccSequence.create({
            "name": "SSCC GCP 12",
            "gs1_company_prefix": "001234567890",
            "extension_digit": "2",
            "sequence_id": raw_seq_12.id,
        })
        sscc_12 = allocator_12.next_sscc()
        self.assertEqual(len(sscc_12), 18)
        self.assertEqual(sscc_12[0], "2")
        self.assertEqual(sscc_12[1:13], "001234567890")
        self.assertEqual(sscc_12[13:17], "0007")  # 4 dígitos de serial con zero-pad
        self.assertTrue(check_barcode_encoding(sscc_12, "sscc"))

    # ------------------------------------------------------------------
    # TEST-HU-016: Unicidad secuencial y consumo de contador
    # ------------------------------------------------------------------

    def test_hu_016_sequential_uniqueness(self):
        """HU-016: Dos llamadas consecutivas generan SSCCs distintos y consumen exactamente 1 serial por llamada."""
        allocator = self.SsccSequence.create({
            "name": "SSCC Uniqueness Test",
            "gs1_company_prefix": "8412345",
            "extension_digit": "0",
            "sequence_id": self.raw_seq_main.id,
        })

        with patch.object(type(allocator.sequence_id), "next_by_id", wraps=allocator.sequence_id.next_by_id) as spy_next:
            sscc_1 = allocator.next_sscc()
            self.assertEqual(spy_next.call_count, 1, "La primera llamada debe consumir exactamente 1 serial")

            sscc_2 = allocator.next_sscc()
            self.assertEqual(spy_next.call_count, 2, "La segunda llamada debe acumular exactamente 2 consumos de serial")

        self.assertNotEqual(sscc_1, sscc_2)
        self.assertTrue(check_barcode_encoding(sscc_1, "sscc"))
        self.assertTrue(check_barcode_encoding(sscc_2, "sscc"))

    # ------------------------------------------------------------------
    # TEST-HU-017: Guard de configuración en runtime y allocator inactivo
    # ------------------------------------------------------------------

    def test_hu_017_runtime_sequence_configuration_guard_and_inactive_allocator(self):
        """HU-017: next_sscc() rechaza prefijos, sufijos, use_date_range, incremento <= 0, allocator inactivo sin consumo y salida no numérica."""
        allocator = self.SsccSequence.create({
            "name": "SSCC Guard Test",
            "gs1_company_prefix": "7601234",
            "extension_digit": "4",
            "sequence_id": self.raw_seq_main.id,
        })

        # 1. Allocator inactivo: ValidationError y NO consume número de secuencia
        with patch.object(type(allocator.sequence_id), "next_by_id", wraps=allocator.sequence_id.next_by_id) as spy_next:
            allocator.write({"active": False})
            with self.assertRaises(ValidationError):
                allocator.next_sscc()
            self.assertEqual(spy_next.call_count, 0, "next_by_id no debe llamarse si el allocator está inactivo")
            allocator.write({"active": True})

        # 2. Sequence con prefijo no vacío
        self.raw_seq_main.write({"prefix": "PRE-"})
        with self.assertRaises(ValidationError):
            allocator.next_sscc()
        self.raw_seq_main.write({"prefix": False})

        # 3. Sequence con sufijo no vacío
        self.raw_seq_main.write({"suffix": "-SUF"})
        with self.assertRaises(ValidationError):
            allocator.next_sscc()
        self.raw_seq_main.write({"suffix": False})

        # 4. Sequence con use_date_range=True
        self.raw_seq_main.write({"use_date_range": True})
        with self.assertRaises(ValidationError):
            allocator.next_sscc()
        self.raw_seq_main.write({"use_date_range": False})

        # 5. Sequence con number_increment <= 0
        allocator_invalid_inc = allocator.new({
            "sequence_id": self.IrSequence.new({"name": "Invalid Inc Mock", "number_increment": 0}),
        })
        with self.assertRaises(ValidationError):
            allocator_invalid_inc._validate_sequence_configuration()

        # 6. Salida no numérica de next_by_id -> ValidationError
        with patch.object(type(allocator.sequence_id), "next_by_id", return_value="ABC12"):
            with self.assertRaises(ValidationError):
                allocator.next_sscc()

    # ------------------------------------------------------------------
    # TEST-HU-018: Agotamiento de capacidad de serial
    # ------------------------------------------------------------------

    def test_hu_018_capacity_exhaustion_validation(self):
        """HU-018: GCP=12 (capacidad 4 dígitos, máx 9999) genera SSCC en 9999 y lanza ValidationError en 10000."""
        raw_seq_capacity = self.IrSequence.create({
            "name": "Counter Capacity Test",
            "code": "wms.sscc.counter.capacity",
            "company_id": self.Company.id,
            "number_increment": 1,
            "number_next_actual": 9999,
        })
        allocator = self.SsccSequence.create({
            "name": "SSCC Capacity Allocator",
            "gs1_company_prefix": "001234567890",  # 12 dígitos -> serial de 4 dígitos
            "extension_digit": "9",
            "sequence_id": raw_seq_capacity.id,
        })

        # 1. Serial 9999 -> Válido
        sscc_9999 = allocator.next_sscc()
        self.assertEqual(sscc_9999[13:17], "9999")
        self.assertTrue(check_barcode_encoding(sscc_9999, "sscc"))

        # 2. Serial 10000 -> Excede capacidad de 4 dígitos -> ValidationError
        with self.assertRaises(ValidationError):
            allocator.next_sscc()

    # ------------------------------------------------------------------
    # TEST-HU-019: Control de acceso RBAC, multi-compañía y no side-effects
    # ------------------------------------------------------------------

    def test_hu_019_rbac_multi_company_and_no_side_effects(self):
        """HU-019: Operator y Supervisor leen y ejecutan next_sscc; Manager CRUD completo; multi-compañía; stock.package intacto."""
        allocator = self.SsccSequence.create({
            "name": "SSCC RBAC Allocator",
            "gs1_company_prefix": "7601234",
            "extension_digit": "5",
            "sequence_id": self.raw_seq_main.id,
        })

        # 1. Operator: Lectura y next_sscc() permitidos; escritura prohibida (AccessError)
        sscc_op = allocator.with_user(self.user_operator).next_sscc()
        self.assertTrue(check_barcode_encoding(sscc_op, "sscc"))
        with self.assertRaises(AccessError):
            allocator.with_user(self.user_operator).write({"gs1_company_prefix": "7609999"})

        # 2. Supervisor: Lectura y next_sscc() permitidos; escritura prohibida (AccessError)
        sscc_sup = allocator.with_user(self.user_supervisor).next_sscc()
        self.assertTrue(check_barcode_encoding(sscc_sup, "sscc"))
        with self.assertRaises(AccessError):
            allocator.with_user(self.user_supervisor).write({"gs1_company_prefix": "7609999"})

        # 3. Manager: CRUD completo (Create, Read, Write, Unlink) y next_sscc()
        # 3a. Create
        seq_mgr = self.SsccSequence.with_user(self.user_manager).create({
            "name": "SSCC Manager Full CRUD",
            "gs1_company_prefix": "9876543",
            "extension_digit": "7",
            "sequence_id": self.raw_seq_main.id,
        })
        self.assertTrue(seq_mgr.id)
        # 3b. Read
        read_val = seq_mgr.with_user(self.user_manager).read(["name", "gs1_company_prefix"])[0]
        self.assertEqual(read_val["name"], "SSCC Manager Full CRUD")
        # 3c. Write
        seq_mgr.with_user(self.user_manager).write({"name": "SSCC Manager Renamed"})
        self.assertEqual(seq_mgr.name, "SSCC Manager Renamed")
        # 3d. next_sscc()
        sscc_mgr = seq_mgr.with_user(self.user_manager).next_sscc()
        self.assertTrue(check_barcode_encoding(sscc_mgr, "sscc"))
        # 3e. Unlink
        seq_mgr.with_user(self.user_manager).unlink()
        self.assertFalse(seq_mgr.exists())

        # 4. Multi-compañía: Usuario de compañía secundaria no puede acceder a secuencia de compañía principal
        with self.assertRaises(AccessError):
            allocator.with_user(self.user_sec_operator).next_sscc()

        # 5. Sin efectos secundarios sobre stock.package ni alteración de packages existentes
        pkg_fixture = self.Package.create({
            "name": "PKG-FIXTURE-HU019",
            "hu_state": "OPEN",
            "hu_class": "PALLET",
        })
        pkg_id_orig = pkg_fixture.id
        pkg_name_orig = pkg_fixture.name
        pkg_state_orig = pkg_fixture.hu_state
        pkg_class_orig = pkg_fixture.hu_class
        pkg_count_before = self.Package.search_count([])

        # Múltiples llamadas a next_sscc()
        allocator.next_sscc()
        allocator.next_sscc()
        allocator.next_sscc()

        pkg_count_after = self.Package.search_count([])
        self.assertEqual(pkg_count_before, pkg_count_after, "next_sscc() no debe crear ni eliminar ningún stock.package")
        pkg_fixture.invalidate_recordset()
        self.assertEqual(pkg_fixture.id, pkg_id_orig, "El ID del paquete fixture debe permanecer inalterado")
        self.assertEqual(pkg_fixture.name, pkg_name_orig, "El name del paquete fixture debe permanecer inalterado")
        self.assertEqual(pkg_fixture.hu_state, pkg_state_orig, "El hu_state del paquete fixture debe permanecer inalterado")
        self.assertEqual(pkg_fixture.hu_class, pkg_class_orig, "El hu_class del paquete fixture debe permanecer inalterado")
