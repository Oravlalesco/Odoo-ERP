from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.barcode import check_barcode_encoding, get_barcode_check_digit


class WmsSsccSequence(models.Model):
    """Asignador de identificadores GS1 SSCC-18 para Unidades de Manipulación (HU-003A).

    Configura y consume una secuencia transaccional estándar (ir.sequence) como contador
    monotónico, agregando la composición y validaciones estandarizadas GS1:
        SSCC-18 = Extension Digit (1) + GS1 Company Prefix (4..12) + Serial Ref (12..4) + Check Digit (1)
    """

    _name = "wms.sscc.sequence"
    _description = "Secuencia GS1 SSCC-18 para Unidades de Manipulación"
    _check_company_auto = True
    _order = "company_id, name, id"

    name = fields.Char(
        string="Nombre",
        required=True,
    )
    active = fields.Boolean(
        string="Activo",
        default=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    gs1_company_prefix = fields.Char(
        string="Prefijo de Compañía GS1 (GCP)",
        required=True,
        help="Prefijo de compañía GS1 asignado (GCP). Debe contener entre 4 y 12 dígitos ASCII.",
    )
    extension_digit = fields.Selection(
        selection=[
            ("0", "0"),
            ("1", "1"),
            ("2", "2"),
            ("3", "3"),
            ("4", "4"),
            ("5", "5"),
            ("6", "6"),
            ("7", "7"),
            ("8", "8"),
            ("9", "9"),
        ],
        string="Dígito de Extensión",
        required=True,
        help="Dígito de extensión GS1 (0-9) utilizado para aumentar la capacidad de numeración o categorizar HU.",
    )
    sequence_id = fields.Many2one(
        "ir.sequence",
        string="Secuencia Contador",
        required=True,
        check_company=True,
        ondelete="restrict",
        copy=False,
        help="Secuencia transaccional Odoo utilizada exclusivamente como contador numérico para el serial SSCC.",
    )

    _company_gcp_extension_unique = models.Constraint(
        "UNIQUE(company_id, gs1_company_prefix, extension_digit)",
        "Ya existe un asignador SSCC para esta compañía, prefijo GS1 y dígito de extensión.",
    )

    @api.constrains("gs1_company_prefix")
    def _check_gs1_company_prefix(self):
        """Validar que el GCP contenga únicamente dígitos ASCII y tenga entre 4 y 12 caracteres."""
        for record in self:
            if not record.gs1_company_prefix or not record.gs1_company_prefix.isascii() or not record.gs1_company_prefix.isdigit() or not (4 <= len(record.gs1_company_prefix) <= 12):
                raise ValidationError(
                    "El Prefijo de Compañía GS1 (GCP) debe contener exclusivamente dígitos ASCII (0-9) "
                    "y tener una longitud de entre 4 y 12 caracteres."
                )

    @api.constrains("extension_digit")
    def _check_extension_digit(self):
        """Validar que el dígito de extensión sea un valor válido entre '0' y '9'."""
        for record in self:
            if record.extension_digit not in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]:
                raise ValidationError("El dígito de extensión debe ser un dígito entre '0' y '9'.")

    def _validate_sequence_configuration(self):
        """Validar en tiempo de ejecución la configuración del asignador y del ir.sequence asociado."""
        self.ensure_one()
        if not self.active:
            raise ValidationError("La secuencia SSCC está inactiva y no puede generar identificadores.")
        if not self.gs1_company_prefix or not self.gs1_company_prefix.isascii() or not self.gs1_company_prefix.isdigit() or not (4 <= len(self.gs1_company_prefix) <= 12):
            raise ValidationError(
                "El Prefijo de Compañía GS1 (GCP) configurado no es válido (debe tener entre 4 y 12 dígitos ASCII)."
            )
        if self.extension_digit not in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]:
            raise ValidationError("El dígito de extensión configurado no es válido (debe ser un dígito entre '0' y '9').")
        if not self.sequence_id:
            raise ValidationError("La secuencia SSCC debe tener una secuencia contador (ir.sequence) asignada.")
        if self.sequence_id.prefix:
            raise ValidationError("La secuencia contador no debe tener prefijo configurado para generar SSCC.")
        if self.sequence_id.suffix:
            raise ValidationError("La secuencia contador no debe tener sufijo configurado para generar SSCC.")
        if self.sequence_id.use_date_range:
            raise ValidationError(
                "La secuencia contador no debe utilizar rangos de fechas (use_date_range) para garantizar monotonicidad global del SSCC."
            )
        if self.sequence_id.number_increment <= 0:
            raise ValidationError("El incremento de la secuencia contador debe ser estrictamente mayor a 0.")

    def next_sscc(self):
        """Generar y retornar el siguiente código SSCC-18 válido para la compañía.

        :return: String de exactamente 18 dígitos con checksum GS1 módulo-10 válido.
        """
        self.ensure_one()
        self.check_access("read")
        self._validate_sequence_configuration()

        raw_serial = self.sequence_id.next_by_id()
        if not raw_serial or not str(raw_serial).isascii() or not str(raw_serial).isdigit():
            raise ValidationError("La secuencia contador generó un valor no numérico incompatible con SSCC.")

        raw_serial_str = str(raw_serial)
        serial_length = 16 - len(self.gs1_company_prefix)
        if len(raw_serial_str) > serial_length:
            raise ValidationError(
                f"La secuencia ha superado la capacidad máxima de {serial_length} dígitos "
                f"para el prefijo GS1 '{self.gs1_company_prefix}'."
            )

        serial_reference = raw_serial_str.zfill(serial_length)
        body = f"{self.extension_digit}{self.gs1_company_prefix}{serial_reference}"
        if len(body) != 17:
            raise ValidationError(f"Error interno en longitud de cuerpo SSCC ({len(body)} != 17).")

        check_digit = get_barcode_check_digit(body + "0")
        sscc = f"{body}{check_digit}"

        if not check_barcode_encoding(sscc, "sscc"):
            raise ValidationError(f"El SSCC generado '{sscc}' no superó la validación GS1 SSCC-18.")

        return sscc
