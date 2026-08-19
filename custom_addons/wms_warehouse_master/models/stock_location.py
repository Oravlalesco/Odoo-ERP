from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


# Catálogo aprobado de roles operacionales WMS (ADR-026).
# Ordenado por flujo operacional: entrada → almacenamiento → salida.
WMS_LOCATION_ROLES = [
    ("RECEIVING", "Recepción"),
    ("QUALITY_HOLD", "Retención de calidad"),
    ("QUARANTINE", "Cuarentena"),
    ("DAMAGE", "Mercancía dañada"),
    ("STORAGE", "Almacenamiento"),
    ("RESERVE_STORAGE", "Almacenamiento de reserva"),
    ("PICK_FACE", "Ubicación de picking"),
    ("CONSOLIDATION", "Consolidación"),
    ("PACKING", "Empaque"),
    ("STAGING", "Preparación"),
    ("CROSS_DOCK", "Cross-docking"),
    ("DOCK", "Muelle"),
]


class StockLocation(models.Model):
    """Extensión de stock.location con rol operacional WMS.

    ADR-026: wms_location_role identifica la función operacional
    de una ubicación dentro del WMS.  NO reemplaza
    stock.location.usage, que conserva su semántica Odoo completa.

    Invariante: si wms_location_role tiene valor, usage debe ser 'internal'.
    """

    _inherit = "stock.location"

    wms_location_role = fields.Selection(
        selection=WMS_LOCATION_ROLES,
        string="Rol WMS de la ubicación",
        default=False,
        copy=True,
        help=(
            "Función operacional de esta ubicación dentro del WMS. "
            "No reemplaza stock.location.usage. "
            "Sólo válido en ubicaciones con usage='internal'."
        ),
    )

    @api.constrains("wms_location_role", "usage")
    def _check_wms_role_requires_internal(self):
        """Aplica ADR-026: el rol WMS sólo es válido en ubicaciones internas."""
        for location in self:
            if location.wms_location_role and location.usage != "internal":
                raise ValidationError(
                    _(
                        "El rol WMS sólo puede asignarse a ubicaciones "
                        "con tipo 'Interna'. La ubicación '%(location)s' "
                        "tiene usage='%(usage)s'."
                    )
                    % {
                        "location": location.display_name,
                        "usage": location.usage,
                    }
                )
