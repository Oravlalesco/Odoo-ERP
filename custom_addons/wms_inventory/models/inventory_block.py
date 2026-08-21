from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class WmsInventoryBlock(models.Model):
    """Bloqueo operacional de inventario WMS.

    Registro lógico inmutable de bloqueo sobre dimensiones operacionales
    (ubicación, producto/ubicación, lote, paquete, propietario/ubicación).
    No referencia quant_id para desacoplarse del ciclo de vida técnico de stock.quant.
    """

    _name = "wms.inventory.block"
    _description = "Bloqueo operacional de inventario WMS"
    _rec_name = "reason"
    _order = "blocked_at desc, id desc"
    _check_company_auto = True

    # ------------------------------------------------------------------
    # CAMPOS FUNCIONALES (Exactamente 12)
    # ------------------------------------------------------------------

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        ondelete="restrict",
    )
    block_scope = fields.Selection(
        [
            ("LOCATION", "Ubicación"),
            ("PRODUCT_LOCATION", "Producto y Ubicación"),
            ("LOT", "Lote"),
            ("PACKAGE", "Paquete / HU"),
            ("OWNER_LOCATION", "Propietario y Ubicación"),
        ],
        string="Alcance del bloqueo",
        required=True,
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Ubicación",
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lote",
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    package_id = fields.Many2one(
        "stock.package",
        string="Paquete",
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    owner_id = fields.Many2one(
        "res.partner",
        string="Propietario",
        index=True,
        ondelete="restrict",
    )
    block_type = fields.Selection(
        [
            ("CYCLE_COUNT", "Conteo cíclico"),
            ("INVESTIGATION", "Investigación"),
            ("HOLD", "Retención operacional"),
            ("CUSTOMS", "Aduana"),
        ],
        string="Tipo de bloqueo",
        required=True,
        index=True,
    )
    reason = fields.Text(
        string="Motivo",
        required=True,
    )
    blocked_by = fields.Many2one(
        "res.users",
        string="Bloqueado por",
        required=True,
        readonly=True,
        index=True,
        ondelete="restrict",
    )
    blocked_at = fields.Datetime(
        string="Fecha de bloqueo",
        required=True,
        readonly=True,
        index=True,
    )
    released_at = fields.Datetime(
        string="Fecha de liberación",
        readonly=True,
        index=True,
    )

    # ------------------------------------------------------------------
    # DB CONSTRAINTS
    # ------------------------------------------------------------------

    _check_scope_dimensions = models.Constraint(
        """CHECK(
            (block_scope = 'LOCATION' AND location_id IS NOT NULL AND product_id IS NULL AND lot_id IS NULL AND package_id IS NULL AND owner_id IS NULL) OR
            (block_scope = 'PRODUCT_LOCATION' AND product_id IS NOT NULL AND location_id IS NOT NULL AND lot_id IS NULL AND package_id IS NULL AND owner_id IS NULL) OR
            (block_scope = 'LOT' AND product_id IS NOT NULL AND lot_id IS NOT NULL AND location_id IS NULL AND package_id IS NULL AND owner_id IS NULL) OR
            (block_scope = 'PACKAGE' AND package_id IS NOT NULL AND product_id IS NULL AND location_id IS NULL AND lot_id IS NULL AND owner_id IS NULL) OR
            (block_scope = 'OWNER_LOCATION' AND owner_id IS NOT NULL AND location_id IS NOT NULL AND product_id IS NULL AND lot_id IS NULL AND package_id IS NULL)
        )""",
        "Las dimensiones del bloqueo no coinciden con el alcance (block_scope) seleccionado.",
    )

    _check_released_at = models.Constraint(
        "CHECK(released_at IS NULL OR released_at >= blocked_at)",
        "La fecha de liberación debe ser posterior o igual a la fecha de bloqueo.",
    )

    # ------------------------------------------------------------------
    # PYTHON CONSTRAINTS
    # ------------------------------------------------------------------

    @api.constrains("block_scope", "product_id", "lot_id")
    def _check_lot_product_consistency(self):
        for record in self:
            if record.block_scope == "LOT" and record.lot_id and record.product_id:
                if record.lot_id.product_id != record.product_id:
                    raise ValidationError(
                        "El producto del bloqueo debe coincidir con el producto del lote."
                    )

    # ------------------------------------------------------------------
    # LIFECYCLE & IMMUTABILITY METHODS
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        current_uid = self.env.uid
        for vals in vals_list:
            vals["blocked_by"] = current_uid
            vals["blocked_at"] = now
            vals["released_at"] = False
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(
            "Los registros de bloqueo operacional son inmutables y no pueden ser editados directamente."
        )

    def unlink(self):
        raise UserError(
            "Los registros de bloqueo operacional son inmutables y no pueden ser eliminados."
        )

    def action_release(self):
        """Liberar un bloqueo operacional activo.

        Solo permitido para roles Supervisor WMS o System Admin.
        Actualiza released_at mediante la implementación ORM base.
        """
        self.ensure_one()
        if not (
            self.env.user.has_group("wms_core.group_wms_supervisor")
            or self.env.user.has_group("base.group_system")
        ):
            raise AccessError(
                "Solo supervisores o administradores pueden liberar bloqueos operacionales."
            )
        if self.released_at:
            raise UserError("El bloqueo ya ha sido liberado.")
        now = fields.Datetime.now()
        return super().write({"released_at": now})
