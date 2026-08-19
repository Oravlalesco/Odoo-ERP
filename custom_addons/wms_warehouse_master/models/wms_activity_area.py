from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WmsActivityArea(models.Model):
    """Área de actividad WMS — subdivisión funcional de una zona.

    Un área de actividad representa una clasificación lógica dentro
    de una zona WMS para futura distribución de ubicaciones, recursos
    y trabajo según la actividad realizada.

    Jerarquía:
        Warehouse → Zone → Activity Area

    Identidad operacional: zone_id + code.
    Warehouse y company se derivan estructuralmente de la zona.

    Restricciones:
    - code es único por zona (constraint DB).
    - code se normaliza a uppercase + trim en create/write.
    - code no puede quedar vacío después de normalización.
    """

    _name = "wms.activity.area"
    _description = "WMS Activity Area"
    _order = "zone_id, sequence, code, id"
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
            "Identificador técnico/operacional del área de actividad "
            "dentro de la zona. Se normaliza a mayúsculas automáticamente."
        ),
    )
    zone_id = fields.Many2one(
        "wms.zone",
        string="Zona",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Bodega",
        related="zone_id.warehouse_id",
        store=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        related="zone_id.company_id",
        store=True,
        readonly=True,
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

    _unique_zone_code = models.Constraint(
        "UNIQUE(zone_id, code)",
        "El código de área de actividad debe ser único dentro de la zona.",
    )

    @api.constrains("code")
    def _check_code_not_blank(self):
        """Verificar que el código no quede vacío tras normalización."""
        for area in self:
            if not area.code or not area.code.strip():
                raise ValidationError(
                    _(
                        "El código del área de actividad no puede estar "
                        "vacío. Proporcione un identificador válido."
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
