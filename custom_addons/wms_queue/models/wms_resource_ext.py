from odoo import models, _
from odoo.exceptions import ValidationError

class WmsResource(models.Model):
    _inherit = 'wms.resource'

    def write(self, vals):
        if 'warehouse_id' in vals:
            new_wh_id = vals['warehouse_id']
            Queue = self.env['wms.queue'].sudo().with_context(active_test=False)
            for res in self:
                if res.warehouse_id.id != new_wh_id:
                    # Comprobar existencia con sudo() y active_test=False sin exponer nombres protegidos
                    has_linked_queues = bool(Queue.search_count([
                        ('allowed_resource_ids', 'in', res.id),
                    ]))
                    if has_linked_queues:
                        raise ValidationError(
                            _("No se puede cambiar el almacén del recurso '%s' porque está asignado a una o más colas de trabajo.")
                            % res.display_name
                        )
        return super().write(vals)
