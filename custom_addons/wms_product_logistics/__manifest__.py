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

Este módulo implementa la especificación ADR-024 (Product Logistics Profile)
mediante un modelo one-to-one con product.template (wms.product.logistics).
    """,
    "author": "WMS Project",
    "version": "19.0.1.0.0",
    "category": "Warehouse/WMS",
    "license": "LGPL-3",
    "depends": [
        "wms_core",
        "product",
    ],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
