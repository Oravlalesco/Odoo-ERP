from odoo import fields, models


class StockPackage(models.Model):
    """Extensión WMS del modelo nativo stock.package de Odoo 19 (ADR-013).

    HU-002: Incorpora metadata operativa y de ciclo de vida WMS:
        - hu_state: Estado de ciclo de vida WMS (opcional, sin default).
        - hu_class: Clasificación operacional de la unidad de manipulación (opcional, sin default).

    Ambos campos se inicializan en False cuando el paquete no ha sido adoptado
    por un flujo WMS o no tiene clasificación operacional asignada.
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
