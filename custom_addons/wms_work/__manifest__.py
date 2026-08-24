{
    "name": "WMS Work Engine",
    "summary": "Motor de Trabajo Dirigido y Ejecución WMS",
    "description": """
WMS Work Engine Core
====================
Módulo de Trabajo Dirigido y Ejecución WMS (Fase 7).

Establece la frontera arquitectónica y el ownership del dominio de Work Execution.
Gobierna las unidades de trabajo dirigidas (wms.work, wms.work.line), catálogos,
ciclo de vida, protocolo de lease y comandos transaccionales del WMS.
    """,
    "version": "19.0.1.0.0",
    "category": "Warehouse/WMS",
    "license": "LGPL-3",
    "author": "WMS Project",
    "depends": [
        "wms_core",
        "wms_warehouse_master",
        "wms_inventory",
        "wms_handling_unit",
        "stock",
    ],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
