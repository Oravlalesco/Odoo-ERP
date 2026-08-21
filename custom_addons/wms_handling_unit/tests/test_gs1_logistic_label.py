from unittest.mock import patch
from reportlab.lib.units import mm

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools.barcode import check_barcode_encoding, createBarcodeDrawing


class TestGs1LogisticLabel(TransactionCase):
    """Pruebas unitarias para la Etiqueta Logística GS1 PDF — SSCC-only (HU-003C1).

    Valida:
    - TEST-HU-028: Existencia y metadata de paperformat A6, action report, QWeb template y AbstractModel; cero campos/tablas nuevas.
    - TEST-HU-029: Eligibility guard: paquete con valid_sscc=False es rechazado atómicamente; 0 llamadas a assign_sscc y next_sscc.
    - TEST-HU-030: Barcode contract y geometría nominal GS1: FNC1 + '00' + SSCC, X-dim 0.495mm, barHeight >= 31.75mm, lquiet/rquiet >= 10X, HRI '(00)'+SSCC.
    - TEST-HU-031: Layout QWeb: formato A6 105x148, data title 'SSCC', HRI y barcode presentes con dimensiones físicas en el template.
    - TEST-HU-032: Multi-package y rechazo atómico: múltiples paquetes válidos generan 1 label por paquete; mixto con inválido rechaza todo.
    - TEST-HU-033: RBAC server-side y seguridad multi-compañía: WMS Operator/Supervisor/Manager pasan; Stock puro y Base puro reciben AccessError.
    - TEST-HU-034: Side-effect free: renderizado no muta package, allocator, sequence, history ni genera attachments.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Package = cls.env["stock.package"]
        cls.PackageType = cls.env["stock.package.type"]
        cls.PackageHistory = cls.env["stock.package.history"]
        cls.Location = cls.env["stock.location"]
        cls.Product = cls.env["product.product"]
        cls.Quant = cls.env["stock.quant"]
        cls.Attachment = cls.env["ir.attachment"]
        cls.IrReport = cls.env["ir.actions.report"]
        cls.IrSequence = cls.env["ir.sequence"]
        cls.SsccSequence = cls.env["wms.sscc.sequence"]
        cls.Company = cls.env.company
        cls.Users = cls.env["res.users"]

        cls.ReportAbstract = cls.env["report.wms_handling_unit.report_gs1_logistic_label"]
        cls.report_action = cls.env.ref("wms_handling_unit.action_report_gs1_logistic_label")
        cls.paperformat = cls.env.ref("wms_handling_unit.paperformat_gs1_logistic_label_a6")

        # Compañía secundaria
        cls.company_secondary = cls.env["res.company"].create({
            "name": "Secondary Co GS1 Label",
        })

        # Ubicaciones
        cls.loc_main = cls.Location.search([
            ("usage", "=", "internal"),
            ("company_id", "in", [cls.Company.id, False]),
        ], limit=1)
        if not cls.loc_main:
            cls.loc_main = cls.Location.create({
                "name": "Main Internal Loc GS1 Label",
                "usage": "internal",
                "company_id": cls.Company.id,
            })

        cls.loc_sec = cls.Location.create({
            "name": "Sec Internal Loc GS1 Label",
            "usage": "internal",
            "company_id": cls.company_secondary.id,
        })

        # Producto
        cls.product = cls.Product.create({
            "name": "GS1 Label Test Product",
            "is_storable": True,
        })

        # Tipo de paquete
        cls.package_type = cls.PackageType.create({
            "name": "Pallet GS1 Label Type",
        })

        # Allocator y secuencia para fixtures de side-effect testing (namespace único)
        cls.raw_seq_main = cls.IrSequence.create({
            "name": "Raw SSCC Seq Label Test",
            "code": "wms.sscc.raw.label.test",
            "company_id": cls.Company.id,
            "number_increment": 1,
            "number_next_actual": 10,
            "use_date_range": False,
        })
        cls.allocator_main = cls.SsccSequence.create({
            "name": "SSCC Allocator Label Test",
            "company_id": cls.Company.id,
            "gs1_company_prefix": "7601234",
            "extension_digit": "0",
            "sequence_id": cls.raw_seq_main.id,
        })

        # Grupos de seguridad
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_supervisor = cls.env.ref("wms_core.group_wms_supervisor")
        cls.group_manager = cls.env.ref("wms_core.group_wms_manager")
        cls.group_stock_user = cls.env.ref("stock.group_stock_user")

        # Usuarios de prueba para matriz RBAC
        # 1. WMS Operator (hereda internal)
        cls.user_wms_operator = cls._create_test_user("u_wms_op_label", [cls.group_operator.id])
        # 2. WMS Supervisor (hereda Operator)
        cls.user_wms_supervisor = cls._create_test_user("u_wms_sup_label", [cls.group_supervisor.id])
        # 3. WMS Manager (hereda Supervisor y Operator)
        cls.user_wms_manager = cls._create_test_user("u_wms_mgr_label", [cls.group_manager.id])
        # 4. Stock User Only (sin rol WMS)
        cls.user_stock_user_only = cls._create_test_user("u_stock_only_label", [cls.group_stock_user.id])
        # 5. Base Internal Only (sin rol Stock ni WMS)
        cls.user_base_internal_only = cls._create_test_user("u_base_internal_label", [])
        # 6. Secondary Company Operator
        cls.user_sec_operator = cls.Users.create({
            "name": "User Sec Operator Label",
            "login": "u_sec_op_label",
            "email": "sec_op_label@test.com",
            "company_id": cls.company_secondary.id,
            "company_ids": [(6, 0, [cls.company_secondary.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_operator.id])],
        })

    @classmethod
    def _create_test_user(cls, login, group_ids):
        all_groups = [cls.group_internal.id] + group_ids
        return cls.Users.create({
            "name": f"User {login}",
            "login": login,
            "email": f"{login}@test.com",
            "company_id": cls.Company.id,
            "company_ids": [(6, 0, [cls.Company.id])],
            "group_ids": [(6, 0, all_groups)],
        })

    def _create_company_bound_sscc_package(self, sscc="176012340000000011", company=None, location=None, hu_state="OPEN", hu_class="PALLET"):
        """Helper para crear un paquete con SSCC válido y quant para resolución de compañía."""
        target_company = company or self.Company
        target_loc = location or self.loc_main
        pkg = self.Package.create({
            "name": sscc,
            "package_type_id": self.package_type.id,
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
        self.assertTrue(pkg.valid_sscc, f"El paquete creado con '{sscc}' debe tener valid_sscc=True")
        self.assertEqual(pkg.company_id, target_company)
        return pkg

    # ------------------------------------------------------------------
    # TEST-HU-028: Existencia de artefactos y ausencia de campos/tablas nuevas
    # ------------------------------------------------------------------

    def test_hu_028_artifacts_existence_and_scope_boundaries(self):
        """HU-028: Paperformat A6, report action, QWeb template y AbstractModel existen; cero campos/tablas persistentes."""
        # 1. Paperformat A6 (105x148 mm)
        self.assertTrue(self.paperformat.exists())
        self.assertEqual(self.paperformat.format, "custom")
        self.assertEqual(self.paperformat.page_width, 105)
        self.assertEqual(self.paperformat.page_height, 148)
        self.assertEqual(self.paperformat.orientation, "Portrait")

        # 2. Report Action
        self.assertTrue(self.report_action.exists())
        self.assertEqual(self.report_action.model, "stock.package")
        self.assertEqual(self.report_action.report_type, "qweb-pdf")
        self.assertEqual(self.report_action.report_name, "wms_handling_unit.report_gs1_logistic_label")
        self.assertEqual(self.report_action.binding_model_id, self.env.ref("stock.model_stock_package"))
        self.assertEqual(self.report_action.paperformat_id, self.paperformat)

        # 3. QWeb Template
        template = self.env.ref("wms_handling_unit.report_gs1_logistic_label")
        self.assertTrue(template.exists())

        # 4. AbstractModel técnico
        self.assertIn("report.wms_handling_unit.report_gs1_logistic_label", self.env)
        self.assertTrue(self.ReportAbstract._abstract, "El modelo técnico de reporte debe ser un AbstractModel")

        # 5. Cero campos nuevos en stock.package y cero tablas creadas
        self.assertNotIn("sscc", self.Package._fields)
        self.assertNotIn("label_state", self.Package._fields)
        self.assertFalse(hasattr(self.ReportAbstract, "_table") and self.ReportAbstract._auto)

    # ------------------------------------------------------------------
    # TEST-HU-029: Eligibility guard (valid_sscc=False es rechazado)
    # ------------------------------------------------------------------

    def test_hu_029_eligibility_guard_rejects_invalid_sscc(self):
        """HU-029: Paquete con valid_sscc=False es rechazado con ValidationError; 0 llamadas a assign_sscc/next_sscc."""
        pkg_generic = self.Package.create({"name": "PACK-GENERIC-99"})
        self.assertFalse(pkg_generic.valid_sscc)

        with patch.object(type(pkg_generic), "assign_sscc", wraps=pkg_generic.assign_sscc) as spy_assign, \
             patch.object(type(self.allocator_main), "next_sscc", wraps=self.allocator_main.next_sscc) as spy_alloc:
            with self.assertRaises(ValidationError):
                self.ReportAbstract.with_user(self.user_wms_operator)._get_report_values([pkg_generic.id])
            self.assertEqual(spy_assign.call_count, 0, "No debe llamarse a assign_sscc al imprimir")
            self.assertEqual(spy_alloc.call_count, 0, "No debe consumirse ningún serial SSCC al fallar la validación")

        # El paquete no sufre mutaciones ni auto-asignación
        self.assertEqual(pkg_generic.name, "PACK-GENERIC-99")
        self.assertFalse(pkg_generic.valid_sscc)

    # ------------------------------------------------------------------
    # TEST-HU-030: Barcode contract y geometría nominal GS1
    # ------------------------------------------------------------------

    def test_hu_030_barcode_contract_fnc1_and_gs1_128_structure(self):
        """HU-030: Barcode codifica FNC1 + '00' + SSCC con geometría GS1 vía helper thread-safe de Odoo."""
        sscc = "176012340000000011"
        self.assertTrue(check_barcode_encoding(sscc, "sscc"))

        # 1. HRI con formato canónico GS1
        hri = self.ReportAbstract._get_sscc_hri(sscc)
        self.assertEqual(hri, f"(00){sscc}")
        self.assertNotIn("(", sscc)
        self.assertNotIn(")", sscc)

        # 2. Generación de PNG válido a través del AbstractModel
        png_bytes = self.ReportAbstract._get_sscc_barcode_png_bytes(sscc)
        self.assertTrue(len(png_bytes) > 0)
        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"), "El renderer debe generar un PNG válido")

        # 3. Geometría física nominal del símbolo GS1-128 mediante odoo.tools.barcode.createBarcodeDrawing
        fnc1_payload = f"\xf100{sscc}"
        drawing_gs1 = createBarcodeDrawing(
            "Code128",
            value=fnc1_payload,
            format="png",
            barWidth=0.495 * mm,
            barHeight=32.0 * mm,
            quiet=1,
            lquiet=6.35 * mm,
            rquiet=6.35 * mm,
        )
        barcode_obj = drawing_gs1.contents[0]

        # Validación de parámetros físicos nominales GS1
        self.assertAlmostEqual(barcode_obj.barWidth / mm, 0.495, places=3, msg="X-dimension debe ser 0.495 mm")
        self.assertGreaterEqual(barcode_obj.barHeight / mm, 31.75, msg="La altura de barras debe ser >= 31.75 mm")
        self.assertAlmostEqual(barcode_obj.barHeight / mm, 32.0, places=1)
        self.assertAlmostEqual(barcode_obj.lquiet / mm, 6.35, places=2, msg="Quiet zone izquierda debe ser 6.35 mm (>= 10X)")
        self.assertAlmostEqual(barcode_obj.rquiet / mm, 6.35, places=2, msg="Quiet zone derecha debe ser 6.35 mm (>= 10X)")

        # Ancho total del símbolo con quiet zones debe caber en el ancho disponible de A6 (97 mm)
        total_width_mm = drawing_gs1.width / mm
        self.assertGreaterEqual(total_width_mm, 87.0, "El ancho del símbolo debe ser >= ~87.12 mm")
        self.assertLessEqual(total_width_mm, 97.0, "El ancho del símbolo debe caber en el ancho imprimible de A6 (97 mm)")

        # 4. Verificación de tokens Code 128 (FNC1 presente en la posición 1)
        encoded_tokens = barcode_obj.encoded
        # Tokens: [START_C (105), FNC1 (102), '00' (0), '17' (17), '60' (60), '12' (12), '34' (34), '00' (0), '00' (0), '00' (0), '00' (0), '11' (11), checksum, STOP (106)]
        self.assertEqual(encoded_tokens[0], 105, "Debe iniciar con START_C (105)")
        self.assertEqual(encoded_tokens[1], 102, "El primer caracter de datos debe ser FNC1 (102 / GS1 flag)")
        self.assertEqual(encoded_tokens[2], 0, "El Application Identifier (00) debe codificarse como '00' (0)")

        # Comparar contra Code128 ordinario (sin FNC1) para asegurar que NO sea Code128 estándar
        drawing_ordinary = createBarcodeDrawing(
            "Code128",
            value=f"00{sscc}",
            format="png",
            barWidth=0.495 * mm,
            barHeight=32.0 * mm,
            quiet=1,
            lquiet=6.35 * mm,
            rquiet=6.35 * mm,
        )
        ordinary_tokens = drawing_ordinary.contents[0].encoded
        self.assertNotEqual(ordinary_tokens[1], 102, "Code128 ordinario sin FNC1 no contiene el token 102 en la posición 1")

    # ------------------------------------------------------------------
    # TEST-HU-031: Layout QWeb y estructura de etiqueta A6
    # ------------------------------------------------------------------

    def test_hu_031_qweb_layout_and_rendered_html_content(self):
        """HU-031: QWeb renderiza etiqueta con título 'SSCC', HRI '(00)<sscc>' y código de barras con dimensiones físicas."""
        sscc = "176012340000000011"
        pkg = self._create_company_bound_sscc_package(sscc=sscc)

        report_values = self.ReportAbstract.with_user(self.user_wms_operator)._get_report_values([pkg.id])
        html = self.env["ir.qweb"]._render("wms_handling_unit.report_gs1_logistic_label", report_values)

        html_str = html if isinstance(html, str) else html.decode("utf-8")
        self.assertIn("SSCC", html_str, "El reporte debe contener el título de dato 'SSCC'")
        self.assertIn(f"(00){sscc}", html_str, "El reporte debe contener el HRI formateado")
        self.assertIn("data:image/png;base64,", html_str, "El reporte debe contener la imagen PNG embebida en base64")
        self.assertIn("class=\"page\"", html_str, "Debe contener el contenedor de página de Odoo")
        self.assertIn("90mm", html_str, "El template debe fijar el ancho físico del barcode en 90mm")
        self.assertIn("32mm", html_str, "El template debe fijar la altura física del barcode en 32mm")

    # ------------------------------------------------------------------
    # TEST-HU-032: Múltiples paquetes y rechazo atómico ante inválidos
    # ------------------------------------------------------------------

    def test_hu_032_multi_package_and_atomic_rejection(self):
        """HU-032: Múltiples paquetes válidos generan 1 label por paquete; recordset mixto con uno inválido rechaza todo."""
        # 1. 2 paquetes válidos
        pkg1 = self._create_company_bound_sscc_package(sscc="176012340000000011")
        pkg2 = self._create_company_bound_sscc_package(sscc="076012340000000052")

        values = self.ReportAbstract.with_user(self.user_wms_operator)._get_report_values([pkg1.id, pkg2.id])
        self.assertEqual(len(values["docs"]), 2)

        html = self.env["ir.qweb"]._render("wms_handling_unit.report_gs1_logistic_label", values)
        html_str = html if isinstance(html, str) else html.decode("utf-8")
        self.assertIn("(00)176012340000000011", html_str)
        self.assertIn("(00)076012340000000052", html_str)

        # 2. Recordset mixto con 1 inválido -> rechazo total atómico
        pkg_invalid = self.Package.create({"name": "INVALID-GENERIC-PACK"})
        with self.assertRaises(ValidationError):
            self.ReportAbstract.with_user(self.user_wms_operator)._get_report_values([pkg1.id, pkg_invalid.id, pkg2.id])

    # ------------------------------------------------------------------
    # TEST-HU-033: RBAC server-side y seguridad multi-compañía
    # ------------------------------------------------------------------

    def test_hu_033_rbac_and_multi_company_security(self):
        """HU-033: Server-side RBAC: Operator, Supervisor y Manager pasan; Stock puro y Base puro reciben AccessError."""
        pkg_main = self._create_company_bound_sscc_package(sscc="176012340000000011", company=self.Company)
        pkg_sec = self._create_company_bound_sscc_package(
            sscc="076012340000000052", company=self.company_secondary, location=self.loc_sec
        )

        # 1. Verificación exacta de group_ids en report_action
        self.assertEqual(
            self.report_action.group_ids,
            self.group_operator,
            "La acción de reporte debe estar vinculada exactamente a group_wms_operator",
        )

        # 2. WMS Operator pasa (renderiza su paquete)
        values_op = self.ReportAbstract.with_user(self.user_wms_operator)._get_report_values([pkg_main.id])
        self.assertEqual(len(values_op["docs"]), 1)

        # 3. WMS Supervisor pasa (hereda Operator)
        values_sup = self.ReportAbstract.with_user(self.user_wms_supervisor)._get_report_values([pkg_main.id])
        self.assertEqual(len(values_sup["docs"]), 1)

        # 4. WMS Manager pasa (hereda Supervisor y Operator)
        values_mgr = self.ReportAbstract.with_user(self.user_wms_manager)._get_report_values([pkg_main.id])
        self.assertEqual(len(values_mgr["docs"]), 1)

        # 5. Stock User puro (sin rol WMS) recibe AccessError server-side
        with self.assertRaises(AccessError):
            self.ReportAbstract.with_user(self.user_stock_user_only)._get_report_values([pkg_main.id])

        # 6. Base Internal User puro (sin rol Stock ni WMS) recibe AccessError server-side
        with self.assertRaises(AccessError):
            self.ReportAbstract.with_user(self.user_base_internal_only)._get_report_values([pkg_main.id])

        # 7. Usuario de compañía secundaria intenta acceder a paquete de compañía principal -> AccessError por record rule
        with self.assertRaises(AccessError):
            self.ReportAbstract.with_user(self.user_sec_operator)._get_report_values([pkg_main.id])

    # ------------------------------------------------------------------
    # TEST-HU-034: Side-effect free (inmutabilidad durante renderizado)
    # ------------------------------------------------------------------

    def test_hu_034_render_is_side_effect_free(self):
        """HU-034: Renderizado no muta package, allocator, sequence, stock.package.history ni genera attachments."""
        sscc = "176012340000000011"
        pkg = self._create_company_bound_sscc_package(sscc=sscc, hu_state="OPEN", hu_class="PALLET")

        # Snapshot previo de paquete, allocator y secuencia
        orig_name = pkg.name
        orig_state = pkg.hu_state
        orig_class = pkg.hu_class
        orig_type = pkg.package_type_id
        orig_loc = pkg.location_id
        orig_comp = pkg.company_id
        orig_quants = pkg.quant_ids
        orig_qty = pkg.quant_ids.quantity

        alloc_id = self.allocator_main.id
        alloc_gcp = self.allocator_main.gs1_company_prefix
        alloc_ext = self.allocator_main.extension_digit
        alloc_active = self.allocator_main.active
        seq_next = self.raw_seq_main.number_next_actual

        pkg_count_before = self.Package.search_count([])
        history_count_before = self.PackageHistory.search_count([])
        attachment_count_before = self.Attachment.search_count([])

        # Renderizado de reporte vía _render_qweb_pdf
        res_bytes, report_type = self.IrReport._render_qweb_pdf(
            "wms_handling_unit.report_gs1_logistic_label", [pkg.id]
        )

        # Verificación de renderizado
        self.assertIn(report_type, ("pdf", "html"))
        self.assertTrue(len(res_bytes) > 0)

        # Invariantes del paquete preservados
        self.assertEqual(pkg.name, orig_name)
        self.assertEqual(pkg.hu_state, orig_state)
        self.assertEqual(pkg.hu_class, orig_class)
        self.assertEqual(pkg.package_type_id, orig_type)
        self.assertEqual(pkg.location_id, orig_loc)
        self.assertEqual(pkg.company_id, orig_comp)
        self.assertEqual(pkg.quant_ids, orig_quants)
        self.assertEqual(pkg.quant_ids.quantity, orig_qty)

        # Invariantes del allocator y secuencia transaccional
        self.assertEqual(self.allocator_main.id, alloc_id)
        self.assertEqual(self.allocator_main.gs1_company_prefix, alloc_gcp)
        self.assertEqual(self.allocator_main.extension_digit, alloc_ext)
        self.assertEqual(self.allocator_main.active, alloc_active)
        self.assertEqual(self.raw_seq_main.number_next_actual, seq_next, "El contador ir.sequence no debe consumirse")

        # Invariantes del sistema: cero registros nuevos
        self.assertEqual(self.Package.search_count([]), pkg_count_before)
        self.assertEqual(self.PackageHistory.search_count([]), history_count_before)
        self.assertEqual(self.Attachment.search_count([]), attachment_count_before)
