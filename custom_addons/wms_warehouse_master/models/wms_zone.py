from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WmsZone(models.Model):
    """Zona WMS — agrupación lógica dentro de una bodega.

    Una zona representa una clasificación operacional de un área
    del warehouse para futura distribución de ubicaciones, recursos
    y trabajo.

    Identidad operacional: warehouse_id + code.
    La compañía se deriva estructuralmente del warehouse.

    Restricciones:
    - code es único por warehouse (constraint DB).
    - code se normaliza a uppercase + trim en create/write.
    - code no puede quedar vacío después de normalización.
    """

    _name = "wms.zone"
    _description = "WMS Zone"
    _order = "warehouse_id, sequence, code, id"
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
            "Identificador técnico/operacional de la zona dentro "
            "del warehouse. Se normaliza a mayúsculas automáticamente."
        ),
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Bodega",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        related="warehouse_id.company_id",
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

    _unique_warehouse_code = models.Constraint(
        "UNIQUE(warehouse_id, code)",
        "El código de zona debe ser único dentro de la bodega.",
    )

    @api.constrains("code")
    def _check_code_not_blank(self):
        """Verificar que el código no quede vacío tras normalización."""
        for zone in self:
            if not zone.code or not zone.code.strip():
                raise ValidationError(
                    _(
                        "El código de la zona no puede estar vacío. "
                        "Proporcione un identificador válido."
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
        """Normalizar código y proteger cambio de warehouse con locations."""
        if "code" in vals:
            vals["code"] = self._normalize_code(vals["code"])
        if "warehouse_id" in vals:
            self._check_warehouse_change_allowed(vals["warehouse_id"])
        return super().write(vals)

    def _check_warehouse_change_allowed(self, new_warehouse_id):
        """Bloquear cambio de warehouse si hay locations asignadas.

        Incluye locations archivadas (active_test=False) para evitar
        que un archive+change eluda la protección.
        """
        Location = self.env["stock.location"].with_context(active_test=False)
        for zone in self:
            if zone.warehouse_id.id == new_warehouse_id:
                continue
            assigned = Location.search_count([
                ("wms_zone_id", "=", zone.id),
            ], limit=1)
            if assigned:
                raise ValidationError(
                    _(
                        "No se puede cambiar el warehouse de la zona "
                        "'%(zone)s' mientras tenga ubicaciones asignadas. "
                        "Desasigne las ubicaciones primero."
                    )
                    % {"zone": zone.display_name}
                )
