import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

ALLOWED_MESSAGE_KEYS = {
    "company_id",
    "event_name",
    "schema_version",
    "payload",
    "message_id",
    "created_at",
    "correlation_id",
    "status",
    "attempt_count",
    "next_attempt_at",
    "published_at",
    "last_error",
}

REQUIRED_INPUT_KEYS = {
    "company_id",
    "event_name",
    "schema_version",
    "payload",
}

OUTBOX_STATUSES = [
    ("PENDING", "Pendiente"),
    ("SENT", "Enviado"),
    ("DEAD", "Muerto"),
]


class WmsOutbox(models.Model):
    """Bandeja de salida transaccional WMS (INV-010A).

    Persiste mensajes de integración outbound en la misma transacción que las
    mutaciones de negocio. Base para entrega at-least-once asíncrona.
    Domain-neutral: sin FKs hacia modelos operacionales específicos.

    Inmutable públicamente: create(), write() y unlink() directos bloqueados.
    Única vía de entrada autorizada: API interna _enqueue_messages().
    """

    _name = "wms.outbox"
    _description = "Bandeja de Salida Transaccional WMS"
    _order = "created_at asc, id asc"
    _check_company_auto = True

    # 1. Compañía (explícita, sin default)
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        ondelete="restrict",
        index=True,
    )

    # 2. ID de Mensaje (UUID4 server-owned, unicidad global de DB)
    message_id = fields.Char(
        string="ID de Mensaje",
        required=True,
        readonly=True,
        index=True,
        copy=False,
    )

    # 3. Fecha/Hora de Creación (timestamp server-owned)
    created_at = fields.Datetime(
        string="Fecha/Hora de Creación",
        required=True,
        readonly=True,
        index=True,
    )

    # 4. Nombre del Evento
    event_name = fields.Char(
        string="Nombre de Evento",
        required=True,
        readonly=True,
        index=True,
    )

    # 5. Versión de Esquema (> 0)
    schema_version = fields.Integer(
        string="Versión de Esquema",
        required=True,
        readonly=True,
    )

    # 6. Payload (JSON)
    payload = fields.Json(
        string="Payload",
        required=True,
        readonly=True,
    )

    # 7. ID de Correlación (UUID4 server-owned o tracking ID de batch)
    correlation_id = fields.Char(
        string="ID de Correlación",
        required=True,
        readonly=True,
        index=True,
        copy=False,
    )

    # 8. Estado del Mensaje (PENDING inicial en INV-010A)
    status = fields.Selection(
        OUTBOX_STATUSES,
        string="Estado",
        required=True,
        readonly=True,
        default="PENDING",
        index=True,
    )

    # 9. Contador de Intentos (>= 0, inicial 0)
    attempt_count = fields.Integer(
        string="Intentos",
        required=True,
        readonly=True,
        default=0,
    )

    # 10. Próximo Intento de Entrega
    next_attempt_at = fields.Datetime(
        string="Próximo Intento",
        required=False,
        readonly=True,
        index=True,
    )

    # 11. Fecha/Hora de Publicación Exitosa
    published_at = fields.Datetime(
        string="Fecha/Hora de Publicación",
        required=False,
        readonly=True,
        index=True,
    )

    # 12. Registro del Último Error
    last_error = fields.Text(
        string="Último Error",
        required=False,
        readonly=True,
    )

    # -------------------------------------------------------------------------
    # DB Constraints (Odoo 19 models.Constraint)
    # -------------------------------------------------------------------------

    _message_id_unique = models.Constraint(
        "UNIQUE(message_id)",
        "El ID del mensaje debe ser único globalmente.",
    )

    _check_schema_version_positive = models.Constraint(
        "CHECK(schema_version > 0)",
        "La versión del esquema debe ser estrictamente positiva.",
    )

    _check_attempt_count_non_negative = models.Constraint(
        "CHECK(attempt_count >= 0)",
        "El contador de intentos debe ser mayor o igual a cero.",
    )

    # -------------------------------------------------------------------------
    # Python Constraints
    # -------------------------------------------------------------------------

    @api.constrains("schema_version")
    def _check_schema_version_constrain(self):
        """Invariante: schema_version debe ser un entero estrictamente positivo."""
        for record in self:
            if isinstance(record.schema_version, bool) or not isinstance(record.schema_version, int) or record.schema_version <= 0:
                raise ValidationError("La versión de esquema debe ser un entero estrictamente positivo.")

    @api.constrains("attempt_count")
    def _check_attempt_count_constrain(self):
        """Invariante: attempt_count debe ser un entero no negativo."""
        for record in self:
            if isinstance(record.attempt_count, bool) or not isinstance(record.attempt_count, int) or record.attempt_count < 0:
                raise ValidationError("El contador de intentos debe ser un entero mayor o igual a cero.")

    # -------------------------------------------------------------------------
    # Inmutabilidad pública: create, write, unlink bloqueados
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Bloquear la creación directa pública de mensajes en el outbox."""
        raise UserError(
            "La creación directa de registros en la bandeja de salida no está permitida. Use la API interna _enqueue_messages()."
        )

    def write(self, vals):
        """Bloquear la modificación directa de mensajes en el outbox."""
        raise UserError(
            "Los registros de la bandeja de salida son inmutables y no pueden ser modificados directamente."
        )

    def unlink(self):
        """Bloquear la eliminación directa de mensajes en el outbox."""
        raise UserError(
            "Los registros de la bandeja de salida no pueden ser eliminados."
        )

    # -------------------------------------------------------------------------
    # API privada de inserción
    # -------------------------------------------------------------------------

    @api.model
    def _enqueue_messages(self, messages, correlation_id=None):
        """Encolar un batch de mensajes en la bandeja de salida transaccional de forma atómica.

        :param messages: list[dict] no vacía con los datos de los mensajes a encolar.
                         Cada elemento debe contener: company_id, event_name, schema_version, payload.
        :param correlation_id: str opcional con al menos un carácter no blanco. Si no se provee (None),
                               se genera un UUID4 común para todo el batch.
        :return: recordset de wms.outbox en el mismo orden lógico del batch.
        """
        if not isinstance(messages, list) or not messages:
            raise UserError("messages debe ser una lista no vacía de diccionarios.")

        # Validar correlation_id del parámetro
        if correlation_id is not None:
            if not isinstance(correlation_id, str) or not correlation_id.strip():
                raise ValidationError("correlation_id debe ser una cadena de texto no vacía.")
            batch_correlation = correlation_id.strip()
        else:
            batch_correlation = str(uuid.uuid4())

        batch_created_at = fields.Datetime.now()
        prepared_vals = []

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise UserError(f"El elemento {i} de messages debe ser un diccionario.")

            # Validar claves desconocidas
            unknown_keys = set(msg.keys()) - ALLOWED_MESSAGE_KEYS
            if unknown_keys:
                raise ValidationError(
                    f"Claves no permitidas en el mensaje {i}: {', '.join(sorted(unknown_keys))}"
                )

            # Validar claves requeridas
            missing_keys = REQUIRED_INPUT_KEYS - set(msg.keys())
            if missing_keys:
                raise ValidationError(
                    f"Faltan claves requeridas en el mensaje {i}: {', '.join(sorted(missing_keys))}"
                )

            company_id = msg["company_id"]
            if not company_id:
                raise ValidationError("company_id es requerido y no puede ser vacío.")
            if hasattr(company_id, "id"):
                company_id_val = company_id.id
            elif isinstance(company_id, int) and not isinstance(company_id, bool) and company_id > 0:
                company_id_val = company_id
            else:
                raise ValidationError("company_id inválido.")

            event_name = msg["event_name"]
            if not isinstance(event_name, str) or not event_name.strip():
                raise ValidationError("event_name debe ser una cadena de texto no vacía.")

            schema_version = msg["schema_version"]
            if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version <= 0:
                raise ValidationError("schema_version debe ser un entero estrictamente positivo.")

            payload = msg["payload"]
            if not isinstance(payload, dict):
                raise ValidationError("payload debe ser un diccionario (JSON object).")

            # Preparar valores sobrescribiendo campos server-owned
            prepared = {
                "company_id": company_id_val,
                "event_name": event_name.strip(),
                "schema_version": schema_version,
                "payload": payload,
                "message_id": str(uuid.uuid4()),
                "created_at": batch_created_at,
                "correlation_id": batch_correlation,
                "status": "PENDING",
                "attempt_count": 0,
                "next_attempt_at": False,
                "published_at": False,
                "last_error": False,
            }
            prepared_vals.append(prepared)

        return super().create(prepared_vals)
