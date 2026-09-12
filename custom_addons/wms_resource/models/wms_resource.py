from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class WmsResource(models.Model):
    _name = 'wms.resource'
    _description = 'WMS Resource Satellite'
    _order = 'warehouse_id, resource_id, id'
    _check_company_auto = True

    resource_id = fields.Many2one(
        'resource.resource',
        required=True,
        check_company=True,
        ondelete='restrict',
        string='Resource'
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        required=True,
        check_company=True,
        ondelete='restrict',
        index=True,
        string='Warehouse'
    )
    company_id = fields.Many2one(
        'res.company',
        related='warehouse_id.company_id',
        store=True,
        readonly=True,
        index=True
    )



    _resource_unique = models.Constraint(
        "UNIQUE(resource_id)",
        "Solo puede existir un perfil WMS por recurso.",
    )

    @api.constrains("resource_id", "warehouse_id")
    def _check_company_resource(self):
        for record in self:
            if not record.resource_id.company_id:
                raise ValidationError("El recurso nativo debe tener una compañía asignada.")
            if record.resource_id.company_id != record.company_id:
                raise ValidationError("La compañía del recurso nativo debe coincidir con la del almacén.")
            if record.resource_id.resource_type == "user" and not record.resource_id.user_id:
                raise ValidationError("El recurso humano debe tener un usuario asignado.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.pop("company_id", None)
        return super().create(vals_list)

class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    def write(self, vals):
        for record in self:
            wms_profile = self.env["wms.resource"].sudo().search([("resource_id", "=", record.id)], limit=1)
            if wms_profile:
                if "company_id" in vals:
                    new_comp_id = vals["company_id"]
                    if not new_comp_id or new_comp_id != wms_profile.company_id.id:
                        raise ValidationError("No se puede modificar la compañía de un recurso nativo asociado a un perfil WMS.")

                target_type = vals["resource_type"] if "resource_type" in vals else record.resource_type
                target_user_id = vals["user_id"] if "user_id" in vals else (record.user_id.id if record.user_id else False)
                if target_type == "user" and not target_user_id:
                    raise ValidationError("Un recurso humano WMS debe tener un usuario asignado.")
        return super(ResourceResource, self).write(vals)
