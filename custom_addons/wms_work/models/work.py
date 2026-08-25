# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class WmsWork(models.Model):
    """Encabezado de Trabajo Dirigido WMS.

    WORK-002: Representa la unidad de trabajo ejecutable e independiente
    del Warehouse Management System (ADR-002, ADR-003).
    """

    _name = "wms.work"
    _description = "Trabajo Dirigido WMS"
    _rec_name = "reference"
    _order = "priority desc, deadline asc, id"
    _check_company_auto = True

    _reference_unique = models.Constraint(
        "UNIQUE(reference)",
        "La referencia del trabajo WMS debe ser única.",
    )
    _check_priority_range = models.Constraint(
        "CHECK(priority >= 0 AND priority <= 100)",
        "La prioridad debe estar comprendida entre 0 y 100.",
    )
    _state_priority_deadline_idx = models.Index(
        "(state, priority desc, deadline asc, id)"
    )

    reference = fields.Char(
        string="Referencia",
        required=True,
        readonly=True,
        copy=False,
        default="/",
        index=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Almacén",
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
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("ready", "Listo"),
            ("assigned", "Asignado"),
            ("in_progress", "En Progreso"),
            ("completed", "Completado"),
            ("exception", "Excepción"),
            ("reclaimable", "Reclamable"),
            ("reconciliation_required", "Reconciliación Requerida"),
            ("cancelled", "Cancelado"),
        ],
        string="Estado",
        required=True,
        default="draft",
        readonly=True,
        copy=False,
        index=True,
    )
    priority = fields.Integer(
        string="Prioridad",
        required=True,
        default=50,
    )
    deadline = fields.Datetime(
        string="Fecha Límite",
        copy=False,
    )
    line_ids = fields.One2many(
        "wms.work.line",
        "work_id",
        string="Líneas de Trabajo",
    )

    @api.constrains("priority")
    def _check_priority(self):
        for record in self:
            if record.priority < 0 or record.priority > 100:
                raise ValidationError(
                    "La prioridad debe estar comprendida entre 0 y 100."
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("reference") or vals.get("reference") == "/":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code("wms.work") or "/"
                )
        return super().create(vals_list)
