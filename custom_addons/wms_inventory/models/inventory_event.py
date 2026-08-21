import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

EVENT_TYPES = [
    ("RECEIVE", "Recepción"),
    ("MOVE", "Movimiento"),
    ("RELEASE", "Liberación"),
    ("PUTAWAY", "Ubicación"),
    ("PICK", "Recolección"),
    ("PACK", "Empaque"),
    ("UNPACK", "Desempaque"),
]


class WmsInventoryEvent(models.Model):
    """Diario operacional append-only de eventos de inventario WMS (INV-008).

    Registra transacciones físicas ejecutadas por el WMS.
    Inmutable: no permite creación directa pública, modificación ni borrado.
    La única vía de entrada autorizada es la API privada _append_events().
    """

    _name = "wms.inventory.event"
    _description = "Evento Operacional de Inventario WMS"
    _order = "occurred_at desc, id desc"
    _check_company_auto = True

    # 1. Compañía (explícita, sin default)
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        ondelete="restrict",
        index=True,
    )

    # 2. Fecha/Hora del evento (timestamp server-owned)
    occurred_at = fields.Datetime(
        string="Fecha/Hora del Evento",
        required=True,
        readonly=True,
        index=True,
    )

    # 3. Tipo de Evento
    event_type = fields.Selection(
        EVENT_TYPES,
        string="Tipo de Evento",
        required=True,
        index=True,
    )

    # 4. Producto
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
    )

    # 5. Lote / Serie
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lote/Serie",
        required=False,
        ondelete="restrict",
        check_company=True,
        index=True,
    )

    # 6. Paquete (Handling Unit física = stock.package conforme a ADR-013)
    package_id = fields.Many2one(
        "stock.package",
        string="Paquete / Handling Unit",
        required=False,
        ondelete="restrict",
        check_company=True,
        index=True,
    )

    # 7. Propietario
    owner_id = fields.Many2one(
        "res.partner",
        string="Propietario",
        required=False,
        ondelete="restrict",
        index=True,
    )

    # 8. Ubicación Origen
    source_location_id = fields.Many2one(
        "stock.location",
        string="Ubicación Origen",
        required=False,
        ondelete="restrict",
        check_company=True,
        index=True,
    )

    # 9. Ubicación Destino
    dest_location_id = fields.Many2one(
        "stock.location",
        string="Ubicación Destino",
        required=False,
        ondelete="restrict",
        check_company=True,
        index=True,
    )

    # 10. Cantidad (positiva, expresada en la UoM del producto con precisión 'Product Unit')
    quantity = fields.Float(
        string="Cantidad",
        required=True,
        digits="Product Unit",
    )

    # 11. Operador (server-owned)
    operator_id = fields.Many2one(
        "res.users",
        string="Operador",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
    )

    # 12. Almacén
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Almacén",
        required=False,
        ondelete="restrict",
        check_company=True,
        index=True,
    )

    # 13. ID de Correlación (server-owned UUID4 o tracking ID de batch)
    correlation_id = fields.Char(
        string="ID de Correlación",
        required=True,
        readonly=True,
        index=True,
        copy=False,
    )

    _check_quantity_positive = models.Constraint(
        "CHECK(quantity > 0)",
        "La cantidad del evento de inventario debe ser estrictamente positiva.",
    )

    @api.constrains("quantity")
    def _check_quantity_positive_constrain(self):
        """Invariante: la cantidad del evento de inventario debe ser estrictamente positiva."""
        for record in self:
            if record.quantity <= 0:
                raise ValidationError("La cantidad del evento de inventario debe ser estrictamente positiva.")

    @api.constrains("lot_id", "product_id")
    def _check_lot_product_match(self):
        """Invariante de integridad: el lote asignado debe corresponder al producto del evento."""
        for record in self:
            if record.lot_id and record.lot_id.product_id != record.product_id:
                raise ValidationError(
                    f"El lote '{record.lot_id.name}' no corresponde al producto '{record.product_id.display_name}'."
                )

    # -------------------------------------------------------------------------
    # Inmutabilidad: Prohibición de create directo, write y unlink
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Bloquear la creación directa pública de eventos. Solo permitido vía _append_events()."""
        raise UserError(
            "La creación directa de eventos de inventario no está permitida. Use la API interna _append_events()."
        )

    def write(self, vals):
        """Bloquear toda modificación de eventos. El journal es estrictamente append-only."""
        raise UserError(
            "Los eventos de inventario son inmutables (append-only) y no pueden ser modificados."
        )

    def unlink(self):
        """Bloquear toda eliminación de eventos. El journal es estrictamente append-only."""
        raise UserError(
            "Los eventos de inventario son inmutables (append-only) y no pueden ser eliminados."
        )

    # -------------------------------------------------------------------------
    # API privada de inserción append-only
    # -------------------------------------------------------------------------

    @api.model
    def _append_events(self, vals_list, correlation_id=None):
        """Insertar un batch de eventos de inventario en el journal operacional de forma atómica.

        :param vals_list: list[dict] con valores de 1..N eventos a crear.
        :param correlation_id: str opcional para correlación de transacción. Si no se pasa,
                               se genera un UUID4 único para todo el batch.
        :return: recordset de wms.inventory.event en el mismo orden lógico del batch.
        """
        if not isinstance(vals_list, list) or not vals_list:
            raise UserError("vals_list debe ser una lista no vacía de diccionarios de eventos.")
        for v in vals_list:
            if not isinstance(v, dict):
                raise UserError("Cada elemento de vals_list debe ser un diccionario.")
            if v.get("quantity", 0) <= 0:
                raise ValidationError("La cantidad del evento de inventario debe ser estrictamente positiva.")

        # Generar metadata server-owned común a todo el batch
        now = fields.Datetime.now()
        operator_id = self.env.user.id
        batch_correlation = str(correlation_id) if correlation_id else str(uuid.uuid4())

        prepared_vals = []
        for val in vals_list:
            v = dict(val)
            # Sobrescribir cualquier intento de manipulación de campos server-owned
            v["occurred_at"] = now
            v["operator_id"] = operator_id
            v["correlation_id"] = batch_correlation
            prepared_vals.append(v)

        return super().create(prepared_vals)
