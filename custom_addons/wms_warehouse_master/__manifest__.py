{
    "name": "WMS Warehouse Master",
    "summary": "Extends Odoo warehouse topology with WMS operational semantics",
    "description": """
WMS Warehouse Master
====================

Extends the native Odoo warehouse topology (stock.warehouse,
stock.location) with operational semantics required by the WMS:
location roles, zones, activity areas, storage types, and
physical capacities.

Odoo remains the authority for base topology. This module adds
WMS-specific attributes without replacing or duplicating native
models.
    """,
    "author": "WMS Project",
    "version": "19.0.1.0.0",
    "category": "Warehouse/WMS",
    "license": "LGPL-3",
    "depends": [
        "wms_core",
        "stock",
    ],
    "data": [
        "security/wms_zone_security.xml",
        "security/ir.model.access.csv",
        "views/stock_location_views.xml",
        "views/wms_zone_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
