from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class WmsQueue(models.Model):
    _name = 'wms.queue'
    _description = 'Cola de Trabajo WMS'
    _order = 'priority desc, warehouse_id, code, id'
    _check_company_auto = True

    name = fields.Char(
        string='Nombre',
        required=True,
        translate=True
    )
    code = fields.Char(
        string='Código',
        required=True,
        index=True
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén',
        required=True,
        check_company=True,
        ondelete='restrict',
        index=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='warehouse_id.company_id',
        store=True,
        readonly=True,
        index=True
    )
    priority = fields.Integer(
        string='Prioridad',
        default=50,
        required=True,
        help='Prioridad operacional de 0 a 100. Mayor valor indica mayor prioridad.'
    )
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    zone_ids = fields.Many2many(
        'wms.zone',
        'wms_queue_zone_rel',
        'queue_id',
        'zone_id',
        string='Zonas Habilitadas',
        check_company=True
    )
    allowed_resource_ids = fields.Many2many(
        'wms.resource',
        'wms_queue_resource_rel',
        'queue_id',
        'resource_id',
        string='Recursos Asignables',
        check_company=True
    )

    _queue_unique = models.Constraint(
        "UNIQUE(warehouse_id, code)",
        "El código de cola debe ser único por almacén.",
    )

    @api.constrains('code')
    def _check_code(self):
        for record in self:
            if not record.code or not record.code.strip():
                raise ValidationError(_("El código de la cola no puede estar vacío."))
            if len(record.code) > 32:
                raise ValidationError(_("El código de la cola no puede exceder los 32 caracteres."))

    @api.constrains('priority')
    def _check_priority(self):
        for record in self:
            if record.priority < 0 or record.priority > 100:
                raise ValidationError(_("La prioridad debe ser un valor entero entre 0 y 100."))

    @api.constrains('warehouse_id', 'zone_ids')
    def _check_zone_warehouse(self):
        for record in self:
            for zone in record.zone_ids:
                if zone.warehouse_id != record.warehouse_id:
                    raise ValidationError(_(
                        "La zona '%(zone)s' pertenece a un almacén diferente al de la cola.",
                        zone=zone.name
                    ))

    @api.constrains('warehouse_id', 'allowed_resource_ids')
    def _check_resource_warehouse(self):
        for record in self:
            for res in record.allowed_resource_ids:
                if res.warehouse_id != record.warehouse_id:
                    raise ValidationError(_(
                        "El recurso operacional '%(resource)s' pertenece a un almacén diferente al de la cola.",
                        resource=res.resource_id.name
                    ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.pop("company_id", None)
            if "code" in vals and isinstance(vals["code"], str):
                vals["code"] = vals["code"].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        vals.pop("company_id", None)
        if "code" in vals and isinstance(vals["code"], str):
            vals["code"] = vals["code"].strip().upper()
        return super().write(vals)

    def is_dispatchable(self):
        self.ensure_one()
        if not self.active:
            return False
        if not self.zone_ids or not self.allowed_resource_ids:
            return False
        return True
