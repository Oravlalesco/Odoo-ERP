from odoo import models, _
from odoo.exceptions import ValidationError

class WmsZone(models.Model):
    _inherit = 'wms.zone'

    def write(self, vals):
        if 'warehouse_id' in vals:
            new_wh_id = vals['warehouse_id']
            Queue = self.env['wms.queue'].sudo().with_context(active_test=False)
            for zone in self:
                if zone.warehouse_id.id != new_wh_id:
                    # Comprobar existencia con sudo() y active_test=False sin exponer nombres protegidos
                    has_linked_queues = bool(Queue.search_count([
                        ('zone_ids', 'in', zone.id),
                    ]))
                    if has_linked_queues:
                        raise ValidationError(
                            _("No se puede cambiar el almacén de la zona '%s' porque está asignada a una o más colas de trabajo.")
                            % zone.display_name
                        )
        return super().write(vals)
