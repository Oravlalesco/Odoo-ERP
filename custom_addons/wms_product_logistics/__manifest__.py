{
    "name": "WMS Product Logistics",
    "summary": "Defines WMS product logistical profiles, packaging hierarchies, and operational attributes",
    "description": """
WMS Product Logistics Master
============================

Dominio del Kernel WMS que define el perfil logístico de cada producto:
- UOM y packagings operacionales (pick, case, pallet)
- Configuración de pallet (Ti-Hi)
- Dimensiones y pesos logísticos
- Clasificaciones operacionales (ABC, velocidad, temperatura, hazmat)
- Control de vida útil y restricciones de HU
- Perfiles de almacenamiento, putaway, asignación y reposición

Este módulo establece la base del dominio definido por ADR-024.
El modelo wms.product.logistics y su relación one-to-one con
product.template están implementados desde PLM-002.
    """,
    "author": "WMS Project",
    "version": "19.0.1.0.0",
    "category": "Warehouse/WMS",
    "license": "LGPL-3",
    "depends": [
        "wms_core",
        "product",
        "stock",
    ],
    "data": [
        "security/wms_product_logistics_security.xml",
        "security/ir.model.access.csv",
        "views/wms_product_logistics_views.xml",
        "views/wms_product_logistics_menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
