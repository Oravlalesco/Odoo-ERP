{
    "name": "WMS Inventory Core",
    "summary": "Módulo del dominio de inventario para el Warehouse Management System",
    "description": """
WMS Inventory Core
==================

Módulo del dominio de inventario del Kernel WMS (Fase 5):
- stock.quant como única fuente de verdad del inventario.
- stock.move / stock.move.line reutilizados para intención y detalle físico de movimiento.
- wms_location_role de wms_warehouse_master aportando semántica operativa por ubicación sin extender stock.location.usage.
- Scaffold inicial para futuros bloqueos operacionales, diario de eventos, auditoría e integración outbox.
    """,
    "author": "WMS Project",
    "version": "19.0.1.0.0",
    "category": "Warehouse/WMS",
    "license": "LGPL-3",
    "depends": [
        "wms_core",
        "wms_warehouse_master",
        "stock",
    ],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
