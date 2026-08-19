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

# Fields that constitute WMS configuration on stock.location.
_WMS_CONFIG_FIELDS = {"wms_location_role", "wms_zone_id"}


class StockLocation(models.Model):
    """Extensión de stock.location con semántica operacional WMS.

    ADR-026: wms_location_role identifica la función operacional
    de una ubicación dentro del WMS.  NO reemplaza
    stock.location.usage, que conserva su semántica Odoo completa.

    WM-006: wms_zone_id enlaza la ubicación con una Zone WMS
    del mismo warehouse y compañía.

    Invariantes para wms_zone_id:
    - usage == 'internal'
    - warehouse_id != False
    - zone.warehouse_id == location.warehouse_id
    - company_id != False
    - zone.company_id == location.company_id

    Seguridad de mutación (WM-003 / WM-006):
    Sólo wms_core.group_wms_manager, base.group_system o superuser
    pueden crear/escribir wms_location_role o wms_zone_id.
    La protección es server-side; la UI la refleja pero no la sustituye.
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
    wms_zone_id = fields.Many2one(
        "wms.zone",
        string="WMS Zone",
        default=False,
        ondelete="restrict",
        check_company=True,
        index=True,
        copy=True,
        help=(
            "Zona WMS a la que pertenece esta ubicación. "
            "Debe pertenecer al mismo warehouse y compañía. "
            "Sólo válido en ubicaciones internas con warehouse asignado."
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
    # Constraint WM-006: Zone consistency
    # ------------------------------------------------------------------

    @api.constrains("wms_zone_id", "usage", "warehouse_id", "company_id")
    def _check_wms_zone_consistency(self):
        """Validar las 5 invariantes de la relación location ↔ zone.

        Si wms_zone_id != False:
        1. usage == 'internal'
        2. warehouse_id != False
        3. zone.warehouse_id == location.warehouse_id
        4. company_id != False
        5. zone.company_id == location.company_id
        """
        for loc in self:
            zone = loc.wms_zone_id
            if not zone:
                continue
            if loc.usage != "internal":
                raise ValidationError(
                    _(
                        "La zona WMS sólo puede asignarse a ubicaciones "
                        "internas. '%(location)s' tiene usage='%(usage)s'."
                    )
                    % {"location": loc.display_name, "usage": loc.usage}
                )
            if not loc.warehouse_id:
                raise ValidationError(
                    _(
                        "La ubicación '%(location)s' no pertenece a ningún "
                        "warehouse y no puede tener zona WMS asignada."
                    )
                    % {"location": loc.display_name}
                )
            if zone.warehouse_id != loc.warehouse_id:
                raise ValidationError(
                    _(
                        "La zona '%(zone)s' pertenece al warehouse "
                        "'%(zone_wh)s', pero la ubicación '%(location)s' "
                        "pertenece a '%(loc_wh)s'. Deben coincidir."
                    )
                    % {
                        "zone": zone.display_name,
                        "zone_wh": zone.warehouse_id.display_name,
                        "location": loc.display_name,
                        "loc_wh": loc.warehouse_id.display_name,
                    }
                )
            if not loc.company_id:
                raise ValidationError(
                    _(
                        "La ubicación '%(location)s' es compartida "
                        "(sin compañía) y no puede pertenecer a una "
                        "zona WMS que es company-owned."
                    )
                    % {"location": loc.display_name}
                )
            if zone.company_id != loc.company_id:
                raise ValidationError(
                    _(
                        "La zona '%(zone)s' pertenece a la compañía "
                        "'%(zone_co)s', pero la ubicación '%(location)s' "
                        "pertenece a '%(loc_co)s'. Deben coincidir."
                    )
                    % {
                        "zone": zone.display_name,
                        "zone_co": zone.company_id.display_name,
                        "location": loc.display_name,
                        "loc_co": loc.company_id.display_name,
                    }
                )

    # ------------------------------------------------------------------
    # Autorización de configuración WMS (WM-003 / WM-006)
    # ------------------------------------------------------------------

    def _check_wms_location_configuration_authorization(self):
        """Verificar que el usuario puede modificar configuración WMS.

        Autorizado: superuser, base.group_system, wms_core.group_wms_manager.
        Cualquier otro usuario recibe AccessError.

        Aplica a: wms_location_role, wms_zone_id.
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
                "No tiene permisos para modificar la configuración WMS "
                "de la ubicación (rol o zona). Sólo el Manager WMS o el "
                "Administrador del sistema pueden cambiar esta clasificación."
            )
        )

    # Keep backward-compatible alias for WM-003 tests
    _check_wms_role_authorization = (
        _check_wms_location_configuration_authorization
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Proteger la asignación de configuración WMS durante la creación.

        Verifica tanto el valor explícito en vals como el valor
        que default_get() pueda inyectar (ej. default_wms_location_role
        o default_wms_zone_id en el contexto).
        """
        needs_default = any(
            not _WMS_CONFIG_FIELDS.issubset(vals) for vals in vals_list
        )
        defaults = (
            self.default_get(list(_WMS_CONFIG_FIELDS))
            if needs_default
            else {}
        )
        auth_checked = False
        for vals in vals_list:
            if auth_checked:
                break
            for field in _WMS_CONFIG_FIELDS:
                value = vals.get(field, defaults.get(field))
                if value:
                    self._check_wms_location_configuration_authorization()
                    auth_checked = True
                    break
        return super().create(vals_list)

    def write(self, vals):
        """Proteger la modificación de configuración WMS y validar zone.

        Sólo bloquea si un campo WMS está en vals Y su valor realmente
        cambia. Después de super().write(), revalida zone consistency
        si algún campo relevante fue modificado.
        """
        wms_fields_in_vals = _WMS_CONFIG_FIELDS.intersection(vals)
        if wms_fields_in_vals:
            for location in self:
                for field in wms_fields_in_vals:
                    if location[field] != vals[field]:
                        self._check_wms_location_configuration_authorization()
                        break
                else:
                    continue
                break

        result = super().write(vals)

        # Post-write zone consistency check for fields that may affect
        # the relationship (including location_id which triggers
        # warehouse_id recomputation).
        zone_relevant = {"wms_zone_id", "usage", "location_id", "company_id"}
        if zone_relevant.intersection(vals):
            zoned = self.filtered("wms_zone_id")
            if zoned:
                zoned._check_wms_zone_consistency()

        return result

