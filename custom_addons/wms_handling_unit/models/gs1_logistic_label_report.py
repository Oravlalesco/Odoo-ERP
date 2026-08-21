import base64

from reportlab.lib.units import mm

from odoo import api, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.barcode import createBarcodeDrawing
from odoo.tools.image import image_data_uri


class ReportGs1LogisticLabel(models.AbstractModel):
    """Modelo técnico para la generación de la etiqueta logística GS1 (SSCC) en PDF (HU-003C1).

    Responsabilidad exclusiva:
    - docids -> stock.package
    - Validar autorización server-side del usuario (group_wms_operator o superior / superuser).
    - Validar permiso de lectura sobre los paquetes bajo las reglas de acceso nativas.
    - Validar que todos los paquetes posean valid_sscc == True (rechazo atómico ante inválidos).
    - Generar el código de barras GS1-128 con geometría conforme a GS1 mediante el wrapper thread-safe de Odoo.
    - Proporcionar HRI con formato '(00)' + SSCC.
    - Cero mutaciones, cero consumo de secuencias, cero creación de registros persistentes.
    """

    _name = "report.wms_handling_unit.report_gs1_logistic_label"
    _description = "Reporte Etiqueta Logistica GS1 SSCC"

    @api.model
    def _get_report_values(self, docids, data=None):
        """Preparar los valores del contexto de renderizado QWeb para la etiqueta logística GS1."""
        # 1. Autorización server-side: exigir rol de Operador WMS (o roles superiores / superuser)
        if not (self.env.is_superuser() or self.env.user.has_group("wms_core.group_wms_operator")):
            raise AccessError("Acceso denegado: se requiere rol de Operador WMS para generar la etiqueta logística GS1.")

        # 2. Resolución y verificación de permisos de lectura sobre stock.package
        docs = self.env["stock.package"].browse(docids)
        docs.check_access("read")

        # 3. Eligibility guard: todos los paquetes deben poseer valid_sscc == True
        for package in docs:
            if not package.valid_sscc:
                raise ValidationError(
                    f"El paquete '{package.display_name}' no posee un identificador SSCC-18 válido para la etiqueta logística GS1."
                )

        return {
            "doc_ids": docids,
            "doc_model": "stock.package",
            "docs": docs,
            "get_barcode_base64": self._get_sscc_barcode_base64,
            "get_hri": self._get_sscc_hri,
        }

    @api.model
    def _get_sscc_hri(self, sscc):
        """Retornar la interpretación legible humana (HRI) con Application Identifier (00).

        Los paréntesis son exclusivamente para representación visual humana y nunca
        forman parte de los datos codificados en el código de barras.
        """
        return f"(00){sscc}"

    @api.model
    def _get_sscc_barcode_png_bytes(self, sscc):
        """Generar los bytes PNG del código de barras GS1-128 con geometría nominal GS1.

        Utiliza el helper thread-safe `odoo.tools.barcode.createBarcodeDrawing` protegido
        con RLock y LRU cache ante concurrencia ReportLab.

        Parámetros físicos nominales GS1:
        - Payload: FNC1 (chr(241)) + AI '00' + 18 dígitos SSCC
        - X-dimension (ancho de módulo): 0.495 mm (target GS1 estándar)
        - Altura mínima de barras: 32.0 mm (cumple >= 31.75 mm requeridos por GS1)
        - Zonas de silencio explícitas (lquiet/rquiet): 6.35 mm (cumple >= 4.95 mm / 10X)
        """
        fnc1_payload = f"\xf100{sscc}"
        drawing = createBarcodeDrawing(
            "Code128",
            value=fnc1_payload,
            format="png",
            barWidth=0.495 * mm,
            barHeight=32.0 * mm,
            quiet=1,
            lquiet=6.35 * mm,
            rquiet=6.35 * mm,
        )
        return drawing.asString("png")

    @api.model
    def _get_sscc_barcode_base64(self, sscc):
        """Generar URI data:image/png;base64 del código de barras GS1-128 para el template QWeb."""
        barcode_png = self._get_sscc_barcode_png_bytes(sscc)
        return image_data_uri(base64.b64encode(barcode_png))
