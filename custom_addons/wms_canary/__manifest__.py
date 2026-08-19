{
    "name": "WMS Canary",
    "summary": "Canary module to verify addon discovery, installation, ORM and test runner",
    "description": """
        Temporary infrastructure module (BOOT-005).
        Verifies the complete development pipeline:
        - Addon discovery from /mnt/extra-addons
        - Module installation via Odoo 19 CLI
        - Module upgrade idempotency
        - ORM environment availability
        - Test runner discovery and execution

        This module will be removed after BOOT-GATE when wms_core is operational.
    """,
    "author": "WMS Project",
    "version": "19.0.1.0.0",
    "category": "Warehouse/WMS",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
