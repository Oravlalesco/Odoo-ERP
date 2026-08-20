from odoo import fields, models


class WmsProductLogistics(models.Model):
    """Perfil logístico WMS — companion 1:1 de product.template.

    PLM-002: Identidad core y link one-to-one.

    Cada product.template puede tener como máximo un perfil
    logístico WMS.  El perfil no se crea automáticamente;
    se asigna bajo demanda por un usuario autorizado.

    Campos funcionales:
        product_tmpl_id  → producto Odoo (required, cascade)
        company_id       → derived de product_tmpl_id, puede ser False
        active           → derived de product_tmpl_id

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
    # Constraints
    # ------------------------------------------------------------------

    _unique_product = models.Constraint(
        "UNIQUE(product_tmpl_id)",
        "Sólo puede existir un perfil logístico WMS por producto.",
    )
