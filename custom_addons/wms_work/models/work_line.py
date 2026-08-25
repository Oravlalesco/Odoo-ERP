# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class WmsWorkLine(models.Model):
    """Línea de Trabajo Dirigido WMS.

    WORK-002: Representa una instrucción física unitaria dentro de un trabajo
    dirigido WMS (ADR-002, ADR-003).
    WORK-003: Inmutabilidad estructural y concurrencia (solo modificable en DRAFT).
    """

    _name = "wms.work.line"
    _description = "Línea de Trabajo Dirigido WMS"
    _order = "work_id, sequence, id"
    _check_company_auto = True

    _work_sequence_unique = models.Constraint(
        "UNIQUE(work_id, sequence)",
        "La secuencia debe ser única dentro del mismo trabajo.",
    )
    _check_quantity_non_negative = models.Constraint(
        "CHECK(quantity >= 0)",
        "La cantidad no puede ser negativa.",
    )

    work_id = fields.Many2one(
        "wms.work",
        string="Trabajo",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        related="work_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    sequence = fields.Integer(
        string="Secuencia",
        required=True,
        default=10,
    )
    action = fields.Selection(
        [
            ("pick", "Pick"),
            ("put", "Put"),
            ("move", "Move"),
            ("count", "Count"),
            ("replenishment", "Replenishment"),
            ("load", "Load"),
            ("inspect", "Inspect"),
            ("pack", "Pack"),
        ],
        string="Acción",
        required=True,
    )
    source_location_id = fields.Many2one(
        "stock.location",
        string="Ubicación Origen",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    dest_location_id = fields.Many2one(
        "stock.location",
        string="Ubicación Destino",
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unidad de Medida",
        ondelete="restrict",
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lote / Serie",
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    package_id = fields.Many2one(
        "stock.package",
        string="HU Origen",
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    result_package_id = fields.Many2one(
        "stock.package",
        string="HU Destino",
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    owner_id = fields.Many2one(
        "res.partner",
        string="Propietario",
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    quantity = fields.Float(
        string="Cantidad",
        required=True,
        digits="Product Unit of Measure",
        default=0.0,
    )

    @api.model_create_multi
    def create(self, vals_list):
        work_ids = self.env["wms.work"].browse(
            {v["work_id"] for v in vals_list if v.get("work_id")}
        )
        if work_ids:
            work_ids.lock_for_update()
            for work in work_ids:
                if work.state != "draft":
                    raise UserError(
                        "No se pueden agregar líneas a una tarea de trabajo que no esté en estado borrador."
                    )
        for vals in vals_list:
            if vals.get("product_id") and not vals.get("product_uom_id"):
                product = self.env["product.product"].browse(vals["product_id"])
                if product.exists() and product.uom_id:
                    vals["product_uom_id"] = product.uom_id.id
        return super().create(vals_list)

    def write(self, vals):
        work_ids = self.mapped("work_id")
        if vals.get("work_id"):
            work_ids |= self.env["wms.work"].browse(vals["work_id"])
        if work_ids:
            work_ids.lock_for_update()
            for work in work_ids:
                if work.state != "draft":
                    raise UserError(
                        "No se pueden modificar líneas de una tarea de trabajo que no esté en estado borrador."
                    )
        return super().write(vals)

    def unlink(self):
        work_ids = self.mapped("work_id")
        if work_ids:
            work_ids.lock_for_update()
            for work in work_ids:
                if work.state != "draft":
                    raise UserError(
                        "No se pueden eliminar líneas de una tarea de trabajo que no esté en estado borrador."
                    )
        return super().unlink()

    @api.constrains("quantity")
    def _check_quantity(self):
        for record in self:
            if record.quantity < 0:
                raise ValidationError("La cantidad no puede ser negativa.")

    @api.constrains("product_id", "product_uom_id", "lot_id", "quantity")
    def _check_product_dimensions(self):
        for record in self:
            if not record.product_id:
                if record.lot_id:
                    raise ValidationError(
                        "No se puede especificar un lote sin un producto."
                    )
                if record.product_uom_id:
                    raise ValidationError(
                        "No se puede especificar una unidad de medida sin un producto."
                    )
                if record.quantity != 0.0:
                    raise ValidationError(
                        "La cantidad debe ser 0 si no se especifica un producto."
                    )
            else:
                if record.lot_id and record.lot_id.product_id != record.product_id:
                    raise ValidationError(
                        "El lote no corresponde al producto especificado."
                    )
                valid_uoms = record.product_id.uom_id | record.product_id.uom_ids
                if record.product_uom_id and record.product_uom_id not in valid_uoms:
                    raise ValidationError(
                        "La unidad de medida no pertenece a las unidades de medida autorizadas del producto."
                    )
