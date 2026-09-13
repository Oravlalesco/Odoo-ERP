{
    'name': 'WMS Núcleo de Colas de Trabajo',
    'version': '19.0.1.0.0',
    'category': 'Warehouse Management',
    'summary': 'Identidad canónica y compatibilidad de colas de trabajo WMS (QUEUE-001)',
    'author': 'Oravlalesco',
    'depends': ['stock', 'wms_core', 'wms_warehouse_master', 'wms_resource'],
    'data': [
        'security/wms_queue_security.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
