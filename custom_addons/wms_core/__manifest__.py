{
    "name": "WMS Core",
    "summary": "Foundational infrastructure for WMS modules",
    "description": """
WMS Core
========

Foundational module for the Warehouse Management System.
Provides shared infrastructure upon which all domain-specific
WMS modules depend.

This module does not implement business logic.
Domain functionality lives in specialized modules
(wms_inventory, wms_work, etc.).
    """,
    "author": "WMS Project",
    "version": "19.0.1.0.0",
    "category": "Warehouse/WMS",
    "license": "LGPL-3",
    "depends": ["base"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
