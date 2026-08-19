from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WmsStorageType(models.Model):
    """Tipo de almacenamiento WMS — infraestructura física.

    Un storage type describe la infraestructura física de una
    ubicación de almacenamiento: estantería, rack de pallets,
    piso, cámara fría, etc.

    Semántica:
        stock.location.usage     → semántica estándar Odoo
        wms_location_role        → función operacional (PICK / STORAGE / ...)
        wms.storage.type         → infraestructura física (PALLET_RACK / SHELF / ...)

    Scope:
        Pertenece a una Company.
        Reutilizable entre warehouses de la misma Company.
        No lleva warehouse_id propio.

    Identidad operacional: company_id + code.
    El código se normaliza a uppercase + trim en create/write.

    Restricciones:
    - code es único por company (constraint DB).
    - code no puede quedar vacío después de normalización.
    """

    _name = "wms.storage.type"
    _description = "WMS Storage Type"
    _order = "company_id, sequence, code, id"
    _check_company_auto = True

    name = fields.Char(
        string="Nombre",
        required=True,
    )
    code = fields.Char(
        string="Código",
        required=True,
        size=32,
        help=(
            "Identificador técnico/operacional del tipo de "
            "almacenamiento. Se normaliza a mayúsculas automáticamente."
        ),
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        ondelete="restrict",
        index=True,
    )
    active = fields.Boolean(
        string="Activo",
        default=True,
    )
    sequence = fields.Integer(
        string="Secuencia",
        default=10,
    )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    _unique_company_code = models.Constraint(
        "UNIQUE(company_id, code)",
        "El código de tipo de almacenamiento debe ser único por compañía.",
    )

    @api.constrains("code")
    def _check_code_not_blank(self):
        """Verificar que el código no quede vacío tras normalización."""
        for rec in self:
            if not rec.code or not rec.code.strip():
                raise ValidationError(
                    _(
                        "El código del tipo de almacenamiento no puede "
                        "estar vacío. Proporcione un identificador válido."
                    )
                )

    # ------------------------------------------------------------------
    # Normalización de código
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_code(code):
        """Normalizar código: strip + uppercase."""
        if code:
            return code.strip().upper()
        return code

    @api.model_create_multi
    def create(self, vals_list):
        """Normalizar código durante la creación."""
        for vals in vals_list:
            if "code" in vals:
                vals["code"] = self._normalize_code(vals["code"])
        return super().create(vals_list)

    def write(self, vals):
        """Normalizar código durante la escritura."""
        if "code" in vals:
            vals["code"] = self._normalize_code(vals["code"])
        return super().write(vals)
