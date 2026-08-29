from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError, AccessError
from psycopg2 import IntegrityError
import psycopg2
import os

@tagged('post_install', '-at_install', 'wms', 'wms_resource')
class TestWmsResource(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestWmsResource, cls).setUpClass()
        cls.company_a = cls.env['res.company'].create({'name': 'Company A'})
        cls.company_b = cls.env['res.company'].create({'name': 'Company B'})

        cls.warehouse_a = cls.env['stock.warehouse'].create({
            'name': 'WH A', 'code': 'WHA', 'company_id': cls.company_a.id
        })
        cls.warehouse_b = cls.env['stock.warehouse'].create({
            'name': 'WH B', 'code': 'WHB', 'company_id': cls.company_b.id
        })

        cls.user_op = cls.env['res.users'].create({
            'name': 'Op User A', 'login': 'opuser_a',
            'company_ids': [(6, 0, [cls.company_a.id])],
            'company_id': cls.company_a.id,
            'group_ids': [(6, 0, [cls.env.ref('wms_core.group_wms_operator').id, cls.env.ref('base.group_user').id])]
        })
        cls.user_op_b = cls.env['res.users'].create({
            'name': 'Op User B', 'login': 'opuser_b',
            'company_ids': [(6, 0, [cls.company_b.id])],
            'company_id': cls.company_b.id,
            'group_ids': [(6, 0, [cls.env.ref('wms_core.group_wms_operator').id, cls.env.ref('base.group_user').id])]
        })
        cls.user_sup = cls.env['res.users'].create({
            'name': 'Sup User', 'login': 'supuser',
            'company_ids': [(6, 0, [cls.company_a.id])],
            'company_id': cls.company_a.id,
            'group_ids': [(6, 0, [cls.env.ref('wms_core.group_wms_supervisor').id, cls.env.ref('base.group_user').id])]
        })
        cls.user_mgr = cls.env['res.users'].create({
            'name': 'Mgr User', 'login': 'mgruser',
            'company_ids': [(6, 0, [cls.company_a.id])],
            'company_id': cls.company_a.id,
            'group_ids': [(6, 0, [cls.env.ref('wms_core.group_wms_manager').id, cls.env.ref('base.group_user').id])]
        })
        cls.user_mgr_b = cls.env['res.users'].create({
            'name': 'Mgr User B', 'login': 'mgruser_b',
            'company_ids': [(6, 0, [cls.company_b.id])],
            'company_id': cls.company_b.id,
            'group_ids': [(6, 0, [cls.env.ref('wms_core.group_wms_manager').id, cls.env.ref('base.group_user').id])]
        })
        cls.user_internal = cls.env['res.users'].create({
            'name': 'Internal User', 'login': 'internaluser',
            'company_ids': [(6, 0, [cls.company_a.id])],
            'company_id': cls.company_a.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])]
        })
        cls.user_admin = cls.env['res.users'].create({
            'name': 'Admin User', 'login': 'adminuser',
            'company_ids': [(6, 0, [cls.company_a.id])],
            'company_id': cls.company_a.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_system').id, cls.env.ref('base.group_user').id])]
        })

        cls.resource_human = cls.env['resource.resource'].create({
            'name': 'Human 1',
            'resource_type': 'user',
            'user_id': cls.user_op.id,
            'company_id': cls.company_a.id
        })
        cls.resource_human_b = cls.env['resource.resource'].create({
            'name': 'Human B',
            'resource_type': 'user',
            'user_id': cls.user_op_b.id,
            'company_id': cls.company_b.id
        })
        cls.resource_material = cls.env['resource.resource'].create({
            'name': 'Forklift 1',
            'resource_type': 'material',
            'company_id': cls.company_a.id
        })

    def test_at_res_001_manifest(self):
        import ast
        from odoo.modules.module import get_module_path
        manifest_path = os.path.join(get_module_path('wms_resource'), '__manifest__.py')
        with open(manifest_path, 'r') as f:
            manifest = ast.literal_eval(f.read())
        self.assertEqual(manifest.get('license'), 'LGPL-3')
        self.assertEqual(manifest.get('author'), 'Oravlalesco')
        self.assertIn('resource', manifest.get('depends', []))
        self.assertIn('stock', manifest.get('depends', []))
        self.assertIn('wms_core', manifest.get('depends', []))
        self.assertIn('wms_warehouse_master', manifest.get('depends', []))

    def test_at_res_002_schema_exact_set(self):
        standard_fields = {
            'id', 'display_name', 'create_uid', 'create_date',
            'write_uid', 'write_date'
        }
        model_fields = set(self.env['wms.resource']._fields.keys())
        actual_functional_fields = model_fields - standard_fields
        expected_functional_fields = {'resource_id', 'warehouse_id', 'company_id'}
        self.assertEqual(actual_functional_fields, expected_functional_fields)

    def test_at_res_003_reutilizacion_resource(self):
        res = self.env['wms.resource'].create({
            'resource_id': self.resource_human.id,
            'warehouse_id': self.warehouse_a.id,
        })
        self.assertEqual(res.resource_id.name, 'Human 1')

    def test_at_res_004_human_resource(self):
        res = self.env['wms.resource'].create({
            'resource_id': self.resource_human.id,
            'warehouse_id': self.warehouse_a.id,
        })
        self.assertEqual(res.resource_id.resource_type, 'user')
        self.assertEqual(res.resource_id.user_id, self.user_op)

    def test_at_res_005_material_resource(self):
        res = self.env['wms.resource'].create({
            'resource_id': self.resource_material.id,
            'warehouse_id': self.warehouse_a.id,
        })
        self.assertEqual(res.resource_id.resource_type, 'material')

    def test_at_res_006_strict_uniqueness(self):
        self.env['wms.resource'].create({
            'resource_id': self.resource_human.id,
            'warehouse_id': self.warehouse_a.id,
        })
        self.env.flush_all()
        with self.assertRaises(IntegrityError):
            self.env['wms.resource'].create({
                'resource_id': self.resource_human.id,
                'warehouse_id': self.warehouse_a.id,
            })
            self.env.flush_all()

    def test_at_res_007_company_validation(self):
        resource_b = self.env['resource.resource'].create({
            'name': 'Forklift B',
            'resource_type': 'material',
            'company_id': self.company_b.id
        })
        with self.assertRaises(ValidationError):
            self.env['wms.resource'].create({
                'resource_id': resource_b.id,
                'warehouse_id': self.warehouse_a.id,
            })

        resource_null = self.env['resource.resource'].create({
            'name': 'Forklift Global',
            'resource_type': 'material',
            'company_id': False
        })
        with self.assertRaises(ValidationError):
            self.env['wms.resource'].create({
                'resource_id': resource_null.id,
                'warehouse_id': self.warehouse_a.id,
            })

    def test_at_res_008_user_validation_human(self):
        resource_no_user = self.env['resource.resource'].create({
            'name': 'Human No User',
            'resource_type': 'user',
            'company_id': self.company_a.id
        })
        with self.assertRaises(ValidationError):
            self.env['wms.resource'].create({
                'resource_id': resource_no_user.id,
                'warehouse_id': self.warehouse_a.id,
            })

    def test_at_res_009_rbac_matrix(self):
        res = self.env['wms.resource'].create({
            'resource_id': self.resource_human.id,
            'warehouse_id': self.warehouse_a.id,
        })

        read_fields = ['warehouse_id', 'resource_id', 'company_id']

        # Operator
        op_env = self.env['wms.resource'].with_user(self.user_op)
        op_env.browse(res.id).read(read_fields)
        with self.assertRaises(AccessError):
            op_env.browse(res.id).write({'warehouse_id': self.warehouse_a.id})
        with self.assertRaises(AccessError):
            op_env.create({'resource_id': self.resource_material.id, 'warehouse_id': self.warehouse_a.id})
        with self.assertRaises(AccessError):
            op_env.browse(res.id).unlink()

        # Supervisor
        sup_env = self.env['wms.resource'].with_user(self.user_sup)
        sup_env.browse(res.id).read(read_fields)
        with self.assertRaises(AccessError):
            sup_env.browse(res.id).write({'warehouse_id': self.warehouse_a.id})
        with self.assertRaises(AccessError):
            sup_env.create({'resource_id': self.resource_material.id, 'warehouse_id': self.warehouse_a.id})
        with self.assertRaises(AccessError):
            sup_env.browse(res.id).unlink()

        # Manager
        mgr_env = self.env['wms.resource'].with_user(self.user_mgr)
        mgr_env.browse(res.id).read(read_fields)
        mgr_env.browse(res.id).write({'warehouse_id': self.warehouse_a.id})
        mgr_res = mgr_env.create({'resource_id': self.resource_material.id, 'warehouse_id': self.warehouse_a.id})
        mgr_res.unlink()

        # System Admin
        adm_env = self.env['wms.resource'].with_user(self.user_admin)
        adm_env.browse(res.id).read(read_fields)
        adm_env.browse(res.id).write({'warehouse_id': self.warehouse_a.id})
        resource_admin = self.env['resource.resource'].with_user(self.user_admin).create({
            'name': 'Admin Mat', 'resource_type': 'material', 'company_id': self.company_a.id
        })
        adm_res = adm_env.create({'resource_id': resource_admin.id, 'warehouse_id': self.warehouse_a.id})
        adm_res.unlink()

        # System Admin on resource.resource (unlink=0)
        with self.assertRaises(AccessError):
            self.env['resource.resource'].with_user(self.user_admin).browse(resource_admin.id).unlink()

        # Internal User
        int_env = self.env['wms.resource'].with_user(self.user_internal)
        with self.assertRaises(AccessError):
            int_env.browse(res.id).read(read_fields)
        with self.assertRaises(AccessError):
            int_env.browse(res.id).write({'warehouse_id': self.warehouse_a.id})
        with self.assertRaises(AccessError):
            int_env.create({'resource_id': self.resource_material.id, 'warehouse_id': self.warehouse_a.id})
        with self.assertRaises(AccessError):
            int_env.browse(res.id).unlink()

    def test_at_res_010_isolation(self):
        res_a = self.env['wms.resource'].create({
            'resource_id': self.resource_human.id,
            'warehouse_id': self.warehouse_a.id,
        })
        res_b = self.env['wms.resource'].create({
            'resource_id': self.resource_human_b.id,
            'warehouse_id': self.warehouse_b.id,
        })
        res_mat = self.env['wms.resource'].create({
            'resource_id': self.resource_material.id,
            'warehouse_id': self.warehouse_a.id,
        })

        # Manager A
        mgr_env = self.env['wms.resource'].with_user(self.user_mgr)
        with self.assertRaises(AccessError):
            mgr_env.browse(res_b.id).write({'warehouse_id': self.warehouse_a.id})
        with self.assertRaises(AccessError):
            mgr_env.browse(res_b.id).read(['warehouse_id'])
        self.assertFalse(mgr_env.search([('id', '=', res_b.id)]))

        # Operator A
        op_env = self.env['wms.resource'].with_user(self.user_op)
        with self.assertRaises(AccessError):
            op_env.browse(res_mat.id).read(['warehouse_id'])

        # Supervisor A
        sup_env = self.env['wms.resource'].with_user(self.user_sup)
        sup_env.browse(res_a.id).read(['warehouse_id'])
        sup_env.browse(res_mat.id).read(['warehouse_id'])
        with self.assertRaises(AccessError):
            sup_env.browse(res_b.id).read(['warehouse_id'])

    def test_at_res_011_drift_protection(self):
        res = self.env['wms.resource'].with_context(default_company_id=self.company_b.id).create({
            'resource_id': self.resource_human.id,
            'warehouse_id': self.warehouse_a.id,
            'company_id': self.company_b.id
        })
        self.assertEqual(res.company_id, self.company_a)

        # Context defaults testing
        with self.assertRaises(AccessError):
            self.env['wms.resource'].with_user(self.user_op).with_context(default_resource_id=self.resource_material.id).create({'warehouse_id': self.warehouse_a.id})

        # Drift protection matrix
        resource_mat_user = self.env['resource.resource'].create({
            'name': 'Mat', 'resource_type': 'material', 'user_id': self.user_op.id, 'company_id': self.company_a.id
        })
        self.env['wms.resource'].create({'resource_id': resource_mat_user.id, 'warehouse_id': self.warehouse_a.id})
        with self.assertRaises(ValidationError):
            resource_mat_user.write({'resource_type': 'user', 'user_id': False})

        resource_mat_no_user = self.env['resource.resource'].create({
            'name': 'Mat 2', 'resource_type': 'material', 'company_id': self.company_a.id
        })
        self.env['wms.resource'].create({'resource_id': resource_mat_no_user.id, 'warehouse_id': self.warehouse_a.id})
        with self.assertRaises(ValidationError):
            resource_mat_no_user.write({'resource_type': 'user'})

        resource_mat_no_user.write({'resource_type': 'user', 'user_id': self.user_op.id})

        with self.assertRaises(ValidationError):
            self.resource_human.write({'user_id': False})

        self.resource_human.write({'resource_type': 'material', 'user_id': False})

        resource_no_wms = self.env['resource.resource'].create({
            'name': 'Free', 'resource_type': 'material', 'company_id': self.company_a.id
        })
        resource_no_wms.write({'resource_type': 'user', 'user_id': False}) # Allowed

        # Drift protection across company boundary without record-rule bypass
        user_admin_b = self.env['res.users'].create({
            'name': 'Admin B Drift Test',
            'login': 'admin_b_drift',
            'company_id': self.company_b.id,
            'company_ids': [(6, 0, [self.company_b.id])],
            'group_ids': [(6, 0, [self.env.ref('base.group_system').id])],
        })
        with self.assertRaises(ValidationError):
            resource_mat_user.with_user(user_admin_b).write({'company_id': self.company_b.id})

    def test_at_res_012_zero_side_effects(self):
        q_count = self.env['stock.quant'].search_count([])
        w_count = self.env['wms.work'].search_count([]) if 'wms.work' in self.env else 0
        p_count = self.env['stock.package'].search_count([]) if 'stock.package' in self.env else 0

        res = self.env['wms.resource'].create({
            'resource_id': self.resource_material.id,
            'warehouse_id': self.warehouse_a.id,
        })
        res.write({'warehouse_id': self.warehouse_a.id})
        res.unlink()

        self.assertEqual(q_count, self.env['stock.quant'].search_count([]))
        self.assertEqual(w_count, self.env['wms.work'].search_count([]) if 'wms.work' in self.env else 0)
        self.assertEqual(p_count, self.env['stock.package'].search_count([]) if 'stock.package' in self.env else 0)
