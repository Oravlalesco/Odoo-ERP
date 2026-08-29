{
    'name': 'WMS Resource Identity Core',
    'version': '19.0.1.0.0',
    'category': 'Warehouse Management',
    'summary': 'WMS Operational Resource Identity Core on Odoo 19 resource.resource (ADR-028)',
    'author': 'Oravlalesco',
    'depends': ['resource', 'stock', 'wms_core', 'wms_warehouse_master'],
    'data': [
        'security/wms_resource_security.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
