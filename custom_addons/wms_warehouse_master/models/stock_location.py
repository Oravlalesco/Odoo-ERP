from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


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

    Seguridad de mutación (WM-003):
    Sólo wms_core.group_wms_manager, base.group_system o superuser
    pueden crear/escribir wms_location_role. La protección es server-side;
    la UI la refleja pero no la sustituye.
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

    # ------------------------------------------------------------------
    # Constraint ADR-026 (WM-002)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Autorización de mutación del rol WMS (WM-003)
    # ------------------------------------------------------------------

    def _check_wms_role_authorization(self):
        """Verificar que el usuario actual puede modificar wms_location_role.

        Autorizado: superuser, base.group_system, wms_core.group_wms_manager.
        Cualquier otro usuario recibe AccessError.
        """
        if self.env.su:
            return
        user = self.env.user
        if user.has_group("base.group_system"):
            return
        if user.has_group("wms_core.group_wms_manager"):
            return
        raise AccessError(
            _(
                "No tiene permisos para modificar el Rol WMS de la "
                "ubicación. Sólo el Manager WMS o el Administrador "
                "del sistema pueden cambiar esta clasificación."
            )
        )

    @api.model_create_multi
    def create(self, vals_list):
        """Proteger la asignación de rol WMS durante la creación.

        Verifica tanto el valor explícito en vals como el valor
        que default_get() pueda inyectar (ej. default_wms_location_role
        en el contexto).
        """
        needs_default = any(
            "wms_location_role" not in vals for vals in vals_list
        )
        default_role = (
            self.default_get(["wms_location_role"]).get("wms_location_role")
            if needs_default
            else False
        )
        for vals in vals_list:
            role = (
                vals["wms_location_role"]
                if "wms_location_role" in vals
                else default_role
            )
            if role:
                self._check_wms_role_authorization()
                break
        return super().create(vals_list)

    def write(self, vals):
        """Proteger la modificación de rol WMS durante la escritura.

        Sólo se bloquea si wms_location_role está en vals Y su valor
        realmente cambia respecto al actual.  Writes que no tocan
        wms_location_role pasan sin interferencia.
        """
        if "wms_location_role" in vals:
            new_role = vals["wms_location_role"]
            # Verificar si algún registro realmente cambia de rol.
            for location in self:
                if location.wms_location_role != new_role:
                    self._check_wms_role_authorization()
                    break
        return super().write(vals)

