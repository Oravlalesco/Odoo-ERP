from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain


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

    # ------------------------------------------------------------------
    # API DE CONSULTA DE MATCHING DE BLOQUEOS (INV-003)
    # ------------------------------------------------------------------

    @api.model
    def _get_matching_domain(
        self,
        company_id,
        product_id,
        location_id,
        lot_id=False,
        package_id=False,
        owner_id=False,
    ):
        """Construir el Domain ORM determinista para consultar bloqueos operacionales activos.

        :param company_id: Recordset singleton de res.company (requerido).
        :param product_id: Recordset singleton de product.product (requerido).
        :param location_id: Recordset singleton de stock.location (requerido).
        :param lot_id: Recordset singleton de stock.lot o False (opcional).
        :param package_id: Recordset singleton de stock.package o False (opcional).
        :param owner_id: Recordset singleton de res.partner o False (opcional).
        :return: Instancia de odoo.fields.Domain.
        """
        if not company_id or not hasattr(company_id, "_name") or company_id._name != "res.company":
            raise ValueError("company_id debe ser un recordset singleton de res.company.")
        company_id.ensure_one()

        if not product_id or not hasattr(product_id, "_name") or product_id._name != "product.product":
            raise ValueError("product_id debe ser un recordset singleton de product.product.")
        product_id.ensure_one()

        if not location_id or not hasattr(location_id, "_name") or location_id._name != "stock.location":
            raise ValueError("location_id debe ser un recordset singleton de stock.location.")
        location_id.ensure_one()

        if lot_id:
            if not hasattr(lot_id, "_name") or lot_id._name != "stock.lot":
                raise ValueError("lot_id debe ser un recordset singleton de stock.lot o False.")
            lot_id.ensure_one()

        if package_id:
            if not hasattr(package_id, "_name") or package_id._name != "stock.package":
                raise ValueError("package_id debe ser un recordset singleton de stock.package o False.")
            package_id.ensure_one()

        if owner_id:
            if not hasattr(owner_id, "_name") or owner_id._name != "res.partner":
                raise ValueError("owner_id debe ser un recordset singleton de res.partner o False.")
            owner_id.ensure_one()

        if company_id.id not in self.env.companies.ids:
            raise AccessError("No tiene acceso a la compañía especificada.")

        base_domain = Domain([
            ("company_id", "=", company_id.id),
            ("released_at", "=", False),
        ])

        scope_domains = [
            Domain([
                ("block_scope", "=", "LOCATION"),
                ("location_id", "parent_of", location_id.id),
            ]),
            Domain([
                ("block_scope", "=", "PRODUCT_LOCATION"),
                ("product_id", "=", product_id.id),
                ("location_id", "parent_of", location_id.id),
            ]),
        ]

        if lot_id:
            scope_domains.append(
                Domain([
                    ("block_scope", "=", "LOT"),
                    ("product_id", "=", product_id.id),
                    ("lot_id", "=", lot_id.id),
                ])
            )

        if package_id:
            scope_domains.append(
                Domain([
                    ("block_scope", "=", "PACKAGE"),
                    ("package_id", "parent_of", package_id.id),
                ])
            )

        if owner_id:
            scope_domains.append(
                Domain([
                    ("block_scope", "=", "OWNER_LOCATION"),
                    ("owner_id", "=", owner_id.id),
                    ("location_id", "parent_of", location_id.id),
                ])
            )

        return Domain.AND([base_domain, Domain.OR(scope_domains)])

    @api.model
    def get_matching_blocks(
        self,
        company_id,
        product_id,
        location_id,
        lot_id=False,
        package_id=False,
        owner_id=False,
    ):
        """Obtener todos los bloqueos operacionales activos que aplican a un candidato lógico.

        Ejecuta una sola consulta ORM y retorna el recordset completo de bloqueos.
        """
        domain = self._get_matching_domain(
            company_id,
            product_id,
            location_id,
            lot_id=lot_id,
            package_id=package_id,
            owner_id=owner_id,
        )
        return self.search(domain)

    @api.model
    def is_blocked(
        self,
        company_id,
        product_id,
        location_id,
        lot_id=False,
        package_id=False,
        owner_id=False,
    ):
        """Verificar si existe al menos un bloqueo operacional activo para el candidato lógico.

        Ejecuta una búsqueda de existencia limitada (limit=1) para máximo rendimiento.
        """
        domain = self._get_matching_domain(
            company_id,
            product_id,
            location_id,
            lot_id=lot_id,
            package_id=package_id,
            owner_id=owner_id,
        )
        return bool(self.search_count(domain, limit=1))

    # ------------------------------------------------------------------
    # GUARDIA DE DISPONIBILIDAD OPERACIONAL (INV-004)
    # ------------------------------------------------------------------

    @api.model
    def get_unblocked_available_quantity(
        self,
        company_id,
        product_id,
        location_id,
        lot_id=False,
        package_id=False,
        owner_id=False,
    ):
        """Calcular la cantidad disponible utilizable por el WMS para un candidato lógico exacto.

        Aplica la guardia de bloqueos operacionales sobre la disponibilidad nativa de Odoo:
        1. Consulta is_blocked() primero: si existe un bloqueo activo -> retorna 0.0 inmediatamente (short-circuit).
        2. Si no está bloqueado, valida coherencia de compañía entre el candidato y la ubicación.
        3. Consulta la disponibilidad nativa de Odoo con strict=True y allow_negative=False.

        :param company_id: Recordset singleton de res.company (requerido).
        :param product_id: Recordset singleton de product.product (requerido).
        :param location_id: Recordset singleton de stock.location (requerido).
        :param lot_id: Recordset singleton de stock.lot o False (opcional).
        :param package_id: Recordset singleton de stock.package o False (opcional).
        :param owner_id: Recordset singleton de res.partner o False (opcional).
        :return: float con la cantidad disponible utilizable.
        """
        # 1. Guardia de bloqueo operacional (valida parámetros y autorización de compañía)
        if self.is_blocked(
            company_id,
            product_id,
            location_id,
            lot_id=lot_id,
            package_id=package_id,
            owner_id=owner_id,
        ):
            return 0.0

        # 2. Validación de coherencia de compañía con la ubicación (location_id.company_id)
        if location_id.company_id and location_id.company_id != company_id:
            raise AccessError("La ubicación pertenece a una compañía distinta a la especificada.")

        # 3. Consulta de disponibilidad nativa de candidato exacto (strict=True)
        native_qty = self.env["stock.quant"]._get_available_quantity(
            product_id,
            location_id,
            lot_id=lot_id or None,
            package_id=package_id or None,
            owner_id=owner_id or None,
            strict=True,
            allow_negative=False,
        )
        return float(native_qty)


