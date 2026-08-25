# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class WmsWork(models.Model):
    """Encabezado de Trabajo Dirigido WMS.

    WORK-002: Representa la unidad de trabajo ejecutable e independiente
    del Warehouse Management System (ADR-002, ADR-003).
    WORK-003: Máquina de estados y lifecycle de preparación (DRAFT -> READY -> CANCELLED).
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
        # Prevalidación atómica de estado en lote antes de consumir secuencias
        for vals in vals_list:
            state = vals.get("state")
            if state and state != "draft":
                raise UserError(
                    "Las tareas de trabajo solo pueden crearse en estado borrador."
                )

        for vals in vals_list:
            if not vals.get("reference") or vals.get("reference") == "/":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code("wms.work") or "/"
                )
        return super().create(vals_list)

    def write(self, vals):
        if "state" in vals and not self.env.context.get("_wms_allow_state_transition"):
            raise UserError(
                "No se puede modificar directamente el estado de una tarea de trabajo. Use las acciones de transición."
            )

        if "reference" in vals:
            for record in self:
                if record.reference and vals["reference"] != record.reference:
                    raise UserError(
                        "No se puede modificar la referencia de una tarea de trabajo."
                    )

        if "warehouse_id" in vals:
            for record in self:
                if (
                    record.state != "draft"
                    and vals["warehouse_id"] != record.warehouse_id.id
                ):
                    raise UserError(
                        "El almacén solo puede modificarse en estado borrador."
                    )

        if "line_ids" in vals:
            for record in self:
                if record.state != "draft":
                    raise UserError(
                        "Las líneas solo pueden modificarse en estado borrador."
                    )

        if "priority" in vals or "deadline" in vals:
            for record in self:
                if record.state in ("cancelled", "completed"):
                    raise UserError(
                        "No se puede modificar la prioridad o fecha límite de una tarea en estado terminal."
                    )

        return super().write(vals)

    def unlink(self):
        for record in self:
            if record.state != "draft":
                raise UserError(
                    "Solo se pueden eliminar tareas de trabajo en estado borrador."
                )
        return super().unlink()

    def action_validate(self):
        """Valida una o más tareas de trabajo en borrador pasando a estado listo."""
        self.check_access("write")
        return self._wms_transition_state("ready")

    def action_cancel(self):
        """Cancela una o más tareas de trabajo en estado listo."""
        self.check_access("write")
        return self._wms_transition_state("cancelled")

    def _wms_transition_state(self, target_state):
        """Primitive privada de transición atómica de estado.

        Bloquea registros mediante FOR UPDATE SKIP LOCKED y prevalida
        el lote completo con semántica all-or-nothing.
        """
        if not self:
            return True

        self.lock_for_update()
        to_transition = self.filtered(lambda r: r.state != target_state)
        if not to_transition:
            return True

        if target_state == "ready":
            for record in to_transition:
                if record.state != "draft":
                    raise UserError(
                        "Solo se pueden validar tareas de trabajo en estado borrador."
                    )
                if not record.line_ids:
                    raise UserError(
                        "No se puede validar una tarea de trabajo sin líneas."
                    )
        elif target_state == "cancelled":
            for record in to_transition:
                if record.state != "ready":
                    raise UserError(
                        "Solo se pueden cancelar tareas de trabajo en estado listo."
                    )
        else:
            raise UserError(
                f"Transición al estado {target_state} no autorizada en este slice."
            )

        to_transition.with_context(_wms_allow_state_transition=True).write(
            {"state": target_state}
        )
        return True
