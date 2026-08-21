{
    "name": "WMS Handling Unit",
    "summary": "Dominio de Unidades de Manipulación (Handling Units) y GS1 para WMS",
    "description": """
WMS Handling Unit Core
======================
Módulo del dominio de Unidades de Manipulación (Handling Units) y GS1 para WMS (Fase 6).

Industrializa y extiende el modelo nativo stock.package de Odoo 19 como fundamento físico
de las Handling Units (ADR-013), prohibiendo la creación de modelos paralelos tipo wms.handling.unit.
    """,
    "version": "19.0.1.0.0",
    "category": "Warehouse/WMS",
    "license": "LGPL-3",
    "author": "WMS Project",
    "depends": [
        "wms_core",
        "wms_warehouse_master",
        "wms_product_logistics",
        "stock",
    ],
    "data": [
        "security/wms_handling_unit_security.xml",
        "security/ir.model.access.csv",
        "report/gs1_logistic_label_report.xml",
        "report/gs1_logistic_label_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
