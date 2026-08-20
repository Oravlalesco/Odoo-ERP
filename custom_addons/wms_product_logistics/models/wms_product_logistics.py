from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WmsProductLogistics(models.Model):
    """Perfil logístico WMS — companion 1:1 de product.template.

    PLM-002: Identidad core y link one-to-one.
    PLM-003A: Roles UOM operacionales (pick, case, pallet).

    Cada product.template puede tener como máximo un perfil
    logístico WMS.  El perfil no se crea automáticamente;
    se asigna bajo demanda por un usuario autorizado.

    Campos funcionales (PLM-002):
        product_tmpl_id  → producto Odoo (required, cascade)
        company_id       → derived de product_tmpl_id, puede ser False
        active           → derived de product_tmpl_id

    Campos funcionales (PLM-003A):
        pick_uom_id      → UOM de pick (base o packaging)
        case_uom_id      → UOM de case (sólo packaging)
        pallet_uom_id    → UOM de pallet (sólo packaging)

    Lifecycle:
        - Crear producto no crea perfil
        - Archivar producto → perfil queda active=False
        - Reactivar producto → perfil vuelve a active=True
        - Eliminar producto → perfil eliminado (cascade)
        - Eliminar perfil → producto permanece
    """

    _name = "wms.product.logistics"
    _description = "Perfil logístico WMS de producto"
    _order = "product_tmpl_id, id"
    _rec_name = "product_tmpl_id"

    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Producto",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        related="product_tmpl_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    active = fields.Boolean(
        string="Activo",
        related="product_tmpl_id.active",
        store=True,
        readonly=True,
    )

    # ------------------------------------------------------------------
    # PLM-003A: Operational UOM Roles
    # ------------------------------------------------------------------

    pick_uom_id = fields.Many2one(
        "uom.uom",
        string="UOM de Pick",
        ondelete="restrict",
        help="UOM operacional de pick. "
        "Puede ser la UOM base del producto o un packaging adicional.",
    )
    case_uom_id = fields.Many2one(
        "uom.uom",
        string="UOM de Case",
        ondelete="restrict",
        help="UOM operacional de case. "
        "Debe ser un packaging adicional del producto (uom_ids).",
    )
    pallet_uom_id = fields.Many2one(
        "uom.uom",
        string="UOM de Pallet",
        ondelete="restrict",
        help="UOM operacional de pallet. "
        "Debe ser un packaging adicional del producto (uom_ids).",
    )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    _unique_product = models.Constraint(
        "UNIQUE(product_tmpl_id)",
        "Sólo puede existir un perfil logístico WMS por producto.",
    )

    @api.constrains(
        "product_tmpl_id",
        "pick_uom_id",
        "case_uom_id",
        "pallet_uom_id",
    )
    def _check_operational_uom_roles(self):
        """Validar que las UOM operacionales pertenecen al producto.

        - pick_uom_id: puede ser product.uom_id (base) O product.uom_ids
        - case_uom_id: sólo product.uom_ids (packaging adicional)
        - pallet_uom_id: sólo product.uom_ids (packaging adicional)
        """
        for profile in self:
            product = profile.product_tmpl_id
            base_uom = product.uom_id
            packaging_uoms = product.uom_ids
            all_valid = base_uom | packaging_uoms

            if profile.pick_uom_id and profile.pick_uom_id not in all_valid:
                raise ValidationError(_(
                    "La UOM de pick '%(uom)s' no pertenece al producto "
                    "'%(product)s'. Debe ser la UOM base o un packaging "
                    "adicional.",
                    uom=profile.pick_uom_id.name,
                    product=product.display_name,
                ))

            if profile.case_uom_id:
                if profile.case_uom_id not in packaging_uoms:
                    raise ValidationError(_(
                        "La UOM de case '%(uom)s' no es un packaging "
                        "adicional del producto '%(product)s'.",
                        uom=profile.case_uom_id.name,
                        product=product.display_name,
                    ))

            if profile.pallet_uom_id:
                if profile.pallet_uom_id not in packaging_uoms:
                    raise ValidationError(_(
                        "La UOM de pallet '%(uom)s' no es un packaging "
                        "adicional del producto '%(product)s'.",
                        uom=profile.pallet_uom_id.name,
                        product=product.display_name,
                    ))
