from odoo import models, fields


class WmsCanary(models.TransientModel):
    """Canary transient model to verify ORM functionality.

    This model exists solely to prove that:
    1. Custom addons are discovered from /mnt/extra-addons
    2. The ORM can register a new model
    3. Fields are properly created

    This module will be removed after BOOT-GATE.
    """

    _name = "wms.canary"
    _description = "WMS Canary Check"

    name = fields.Char(
        string="Check Name",
        default="canary",
        help="Canary field to verify ORM field creation",
    )
