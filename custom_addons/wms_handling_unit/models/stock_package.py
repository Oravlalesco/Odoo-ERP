from odoo import fields, models
from odoo.exceptions import ValidationError


class StockPackage(models.Model):
    """Extensión WMS del modelo nativo stock.package de Odoo 19 (ADR-013).

    HU-002: Incorpora metadata operativa y de ciclo de vida WMS:
        - hu_state: Estado de ciclo de vida WMS (opcional, sin default).
        - hu_class: Clasificación operacional de la unidad de manipulación (opcional, sin default).

    HU-003B: Asignación explícita e idempotente de identificadores GS1 SSCC-18:
        - assign_sscc(sscc_sequence_id): Vincula un SSCC generado por wms.sscc.sequence al campo nativo name.
    """

    _inherit = "stock.package"

    hu_state = fields.Selection(
        selection=[
            ("EMPTY", "Vacía"),
            ("OPEN", "Abierta"),
            ("CLOSED", "Cerrada"),
            ("IN_TRANSIT", "En tránsito"),
            ("SHIPPED", "Despachada"),
            ("RETURNED", "Devuelta"),
            ("DISPOSED", "Dada de baja"),
        ],
        string="Estado HU",
        index=True,
        copy=False,
        help="Estado de ciclo de vida WMS cuando el paquete ha sido adoptado por un flujo WMS. "
             "False indica que el ciclo de vida WMS todavía no ha sido inicializado.",
    )

    hu_class = fields.Selection(
        selection=[
            ("PALLET", "Pallet"),
            ("CASE", "Caja"),
            ("TOTE", "Tote"),
            ("CONTAINER", "Contenedor"),
            ("MIXED", "Mixta"),
        ],
        string="Clase HU",
        index=True,
        copy=False,
        help="Clasificación operacional de la unidad de manipulación en el WMS. "
             "False indica que todavía no tiene clasificación asignada.",
    )

    def assign_sscc(self, sscc_sequence_id):
        """Asignar de forma explícita e idempotente un código GS1 SSCC-18 al paquete.

        Reemplaza la referencia genérica 'name' por un SSCC-18 generado por el asignador,
        reutilizando la validación nativa valid_sscc de Odoo 19.

        :param int sscc_sequence_id: ID entero positivo del registro wms.sscc.sequence.
        :return str: Referencia final del paquete (self.name).
        """
        self.ensure_one()
        self.check_access("write")

        # 1. Validar tipo y formato estricto del ID
        if isinstance(sscc_sequence_id, bool) or not isinstance(sscc_sequence_id, int) or sscc_sequence_id <= 0:
            raise ValidationError("El identificador de la secuencia SSCC debe ser un entero positivo.")

        # 2. Idempotencia: si ya tiene SSCC válido, retornar sin modificar ni consumir allocator
        if self.valid_sscc:
            return self.name

        # 3. Resolver y validar existencia del asignador
        allocator = self.env["wms.sscc.sequence"].browse(sscc_sequence_id).exists()
        if not allocator or len(allocator) != 1:
            raise ValidationError("La secuencia SSCC especificada no existe.")

        # 4. Verificar permiso de lectura sobre el asignador
        allocator.check_access("read")

        # 5. Validar que la compañía del paquete esté resuelta
        if not self.company_id:
            raise ValidationError("No se puede asignar un SSCC a un paquete sin compañía resuelta.")

        # 6. Validar coherencia de compañía entre paquete y asignador
        if self.company_id != allocator.company_id:
            raise ValidationError(
                f"La compañía del paquete ({self.company_id.name}) no coincide con la del asignador SSCC ({allocator.company_id.name})."
            )

        # 7. Generar SSCC-18 a través del allocator
        sscc = allocator.next_sscc()

        # 8. Guard de colisión sobre paquetes visibles al llamador
        existing_collision = self.search([
            ("name", "=", sscc),
            ("id", "!=", self.id),
        ], limit=1)
        if existing_collision:
            raise ValidationError(f"Colisión de SSCC: el código '{sscc}' ya está asignado a otro paquete visible.")

        # 9. Asignar el SSCC al name nativo
        self.write({"name": sscc})

        # 10. Validar que el campo nativo valid_sscc haya quedado en True
        if not self.valid_sscc:
            raise ValidationError(f"Error interno: el SSCC asignado '{self.name}' no es válido según el algoritmo GS1.")

        return self.name
