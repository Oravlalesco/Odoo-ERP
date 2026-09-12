from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError, AccessError
from psycopg2 import IntegrityError

@tagged('post_install', '-at_install', 'wms', 'wms_queue')
class TestWmsQueue(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestWmsQueue, cls).setUpClass()
        cls.company_a = cls.env['res.company'].create({'name': 'Company A'})
        cls.company_b = cls.env['res.company'].create({'name': 'Company B'})

        cls.warehouse_a = cls.env['stock.warehouse'].create({
            'name': 'WH A', 'code': 'WHA', 'company_id': cls.company_a.id
        })
        cls.warehouse_a2 = cls.env['stock.warehouse'].create({
            'name': 'WH A2', 'code': 'WHA2', 'company_id': cls.company_a.id
        })
        cls.warehouse_b = cls.env['stock.warehouse'].create({
            'name': 'WH B', 'code': 'WHB', 'company_id': cls.company_b.id
        })

        # Zonas
        cls.zone_a1 = cls.env['wms.zone'].create({
            'name': 'Zone A1', 'code': 'ZA1', 'warehouse_id': cls.warehouse_a.id
        })
        cls.zone_a2 = cls.env['wms.zone'].create({
            'name': 'Zone A2', 'code': 'ZA2', 'warehouse_id': cls.warehouse_a.id
        })
        cls.zone_b1 = cls.env['wms.zone'].create({
            'name': 'Zone B1', 'code': 'ZB1', 'warehouse_id': cls.warehouse_b.id
        })

        # Recursos nativos y satélites WMS
        cls.res_native_a1 = cls.env['resource.resource'].create({
            'name': 'Forklift A1', 'resource_type': 'material', 'company_id': cls.company_a.id
        })
        cls.wms_res_a1 = cls.env['wms.resource'].create({
            'resource_id': cls.res_native_a1.id, 'warehouse_id': cls.warehouse_a.id
        })

        cls.res_native_b1 = cls.env['resource.resource'].create({
            'name': 'Forklift B1', 'resource_type': 'material', 'company_id': cls.company_b.id
        })
        cls.wms_res_b1 = cls.env['wms.resource'].create({
            'resource_id': cls.res_native_b1.id, 'warehouse_id': cls.warehouse_b.id
        })

        # Usuarios RBAC
        cls.user_op = cls.env['res.users'].create({
            'name': 'Operator User A', 'login': 'queue_opuser_a',
            'company_ids': [(6, 0, [cls.company_a.id])],
            'company_id': cls.company_a.id,
            'group_ids': [(6, 0, [cls.env.ref('wms_core.group_wms_operator').id, cls.env.ref('base.group_user').id])]
        })
        cls.user_sup = cls.env['res.users'].create({
            'name': 'Supervisor User A', 'login': 'queue_supuser_a',
            'company_ids': [(6, 0, [cls.company_a.id])],
            'company_id': cls.company_a.id,
            'group_ids': [(6, 0, [cls.env.ref('wms_core.group_wms_supervisor').id, cls.env.ref('base.group_user').id])]
        })
        cls.user_mgr = cls.env['res.users'].create({
            'name': 'Manager User A', 'login': 'queue_mgruser_a',
            'company_ids': [(6, 0, [cls.company_a.id])],
            'company_id': cls.company_a.id,
            'group_ids': [(6, 0, [cls.env.ref('wms_core.group_wms_manager').id, cls.env.ref('base.group_user').id])]
        })
        cls.user_mgr_b = cls.env['res.users'].create({
            'name': 'Manager User B', 'login': 'queue_mgruser_b',
            'company_ids': [(6, 0, [cls.company_b.id])],
            'company_id': cls.company_b.id,
            'group_ids': [(6, 0, [cls.env.ref('wms_core.group_wms_manager').id, cls.env.ref('base.group_user').id])]
        })
        cls.user_admin = cls.env['res.users'].create({
            'name': 'Admin User', 'login': 'queue_adminuser',
            'company_ids': [(6, 0, [cls.company_a.id, cls.company_b.id])],
            'company_id': cls.company_a.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_system').id])]
        })

    def test_at_queue_001_manifest_and_dependencies(self):
        """Validar dependencias, información del manifest y localización en español."""
        module = self.env['ir.module.module'].search([('name', '=', 'wms_queue')], limit=1)
        self.assertTrue(module, "El módulo wms_queue debe estar registrado.")
        self.assertEqual(module.shortdesc, 'WMS Núcleo de Colas de Trabajo', "El nombre del módulo debe estar localizado en español.")
        self.assertEqual(module.summary, 'Identidad canónica y compatibilidad de colas de trabajo WMS (QUEUE-001)', "El resumen del módulo debe estar localizado en español.")

        # Descripción del modelo
        self.assertEqual(self.env['wms.queue']._description, 'Cola de Trabajo WMS', "La descripción del modelo debe estar en español.")

        # Nombres de seguridad visibles en español
        rule = self.env.ref('wms_queue.wms_queue_company_rule')
        self.assertEqual(rule.name, 'wms.queue: regla multi-compañía', "El nombre de la regla multi-compañía debe estar en español.")

        self.assertEqual(self.env.ref('wms_queue.access_wms_queue_operator').name, 'wms.queue: operador')
        self.assertEqual(self.env.ref('wms_queue.access_wms_queue_supervisor').name, 'wms.queue: supervisor')
        self.assertEqual(self.env.ref('wms_queue.access_wms_queue_manager').name, 'wms.queue: responsable')
        self.assertEqual(self.env.ref('wms_queue.access_wms_queue_admin').name, 'wms.queue: administrador')

        # Dependencias
        depends = [d.name for d in module.dependencies_id]
        self.assertIn('stock', depends)
        self.assertIn('wms_core', depends)
        self.assertIn('wms_warehouse_master', depends)
        self.assertIn('wms_resource', depends)

    def test_at_queue_002_schema_exact_set(self):
        """Validar Exact Set Equality de 8 campos funcionales y tipos."""
        Queue = self.env['wms.queue']
        functional_fields = {
            'name', 'code', 'warehouse_id', 'company_id',
            'priority', 'active', 'zone_ids', 'allowed_resource_ids'
        }
        model_fields = set(Queue._fields.keys())
        base_odoo_fields = {
            'id', 'display_name', 'create_uid', 'create_date',
            'write_uid', 'write_date'
        }
        self.assertTrue(functional_fields.issubset(model_fields))
        custom_fields = model_fields - base_odoo_fields
        self.assertEqual(custom_fields, functional_fields, "Deben existir exactamente los 8 campos funcionales definidos.")

        # Tipos
        self.assertEqual(Queue._fields['name'].type, 'char')
        self.assertEqual(Queue._fields['code'].type, 'char')
        self.assertEqual(Queue._fields['warehouse_id'].type, 'many2one')
        self.assertEqual(Queue._fields['company_id'].type, 'many2one')
        self.assertEqual(Queue._fields['priority'].type, 'integer')
        self.assertEqual(Queue._fields['active'].type, 'boolean')
        self.assertEqual(Queue._fields['zone_ids'].type, 'many2many')
        self.assertEqual(Queue._fields['allowed_resource_ids'].type, 'many2many')

    def test_at_queue_003_sql_unique_code_per_warehouse(self):
        """Validar restricción UNIQUE(warehouse_id, code) y unicidad por bodega."""
        self.env['wms.queue'].create({
            'name': 'Picking Queue WH A',
            'code': 'PICK_ZONE_A',
            'warehouse_id': self.warehouse_a.id,
        })

        self.env.flush_all()
        # Mismo código en la misma bodega debe fallar
        with self.assertRaises(IntegrityError):
            self.env['wms.queue'].create({
                'name': 'Duplicate Code WH A',
                'code': 'PICK_ZONE_A',
                'warehouse_id': self.warehouse_a.id,
            })
            self.env.flush_all()

        # Mismo código en diferente bodega DEBE permitirse
        queue_a2 = self.env['wms.queue'].create({
            'name': 'Picking Queue WH A2',
            'code': 'PICK_ZONE_A',
            'warehouse_id': self.warehouse_a2.id,
        })
        self.assertTrue(queue_a2.id)

    def test_at_queue_004_code_normalization_and_validation(self):
        """Validar normalización automática strip + upper y rechazo de código vacío o > 32 chars."""
        q = self.env['wms.queue'].create({
            'name': 'Putaway Queue',
            'code': '  put_forklift  ',
            'warehouse_id': self.warehouse_a.id,
        })
        self.assertEqual(q.code, 'PUT_FORKLIFT', "El código debe normalizarse a mayúsculas y sin espacios.")

        # Modificación
        q.write({'code': '  put_pallet_jack  '})
        self.assertEqual(q.code, 'PUT_PALLET_JACK')

        # Vacío
        with self.assertRaises(ValidationError):
            self.env['wms.queue'].create({
                'name': 'Empty Code',
                'code': '   ',
                'warehouse_id': self.warehouse_a.id,
            })

        # Más de 32 chars
        with self.assertRaises(ValidationError):
            self.env['wms.queue'].create({
                'name': 'Too Long Code',
                'code': 'X' * 33,
                'warehouse_id': self.warehouse_a.id,
            })

    def test_at_queue_005_priority_invariants(self):
        """Validar rango de prioridad 0..100 y default 50."""
        q = self.env['wms.queue'].create({
            'name': 'Default Priority Queue',
            'code': 'DEF_PRIO',
            'warehouse_id': self.warehouse_a.id,
        })
        self.assertEqual(q.priority, 50, "El default de prioridad debe ser 50.")

        q.write({'priority': 100})
        self.assertEqual(q.priority, 100)

        q.write({'priority': 0})
        self.assertEqual(q.priority, 0)

        with self.assertRaises(ValidationError):
            q.write({'priority': -1})

        with self.assertRaises(ValidationError):
            q.write({'priority': 101})

    def test_at_queue_006_spatial_zone_invariants(self):
        """Validar que las zonas vinculadas pertenezcan estrictamente al warehouse_id de la cola."""
        q = self.env['wms.queue'].create({
            'name': 'Spatial Queue',
            'code': 'SPATIAL_Q',
            'warehouse_id': self.warehouse_a.id,
            'zone_ids': [(6, 0, [self.zone_a1.id, self.zone_a2.id])]
        })
        self.assertEqual(len(q.zone_ids), 2)

        # Agregar zona de otro almacén debe fallar
        with self.assertRaises(ValidationError):
            q.write({'zone_ids': [(4, self.zone_b1.id)]})

        with self.assertRaises(ValidationError):
            self.env['wms.queue'].create({
                'name': 'Invalid Spatial Queue',
                'code': 'INV_SPATIAL',
                'warehouse_id': self.warehouse_a.id,
                'zone_ids': [(6, 0, [self.zone_b1.id])]
            })

    def test_at_queue_007_resource_invariants(self):
        """Validar que los recursos permitidos pertenezcan estrictamente al warehouse_id de la cola."""
        q = self.env['wms.queue'].create({
            'name': 'Resource Queue',
            'code': 'RES_Q',
            'warehouse_id': self.warehouse_a.id,
            'allowed_resource_ids': [(6, 0, [self.wms_res_a1.id])]
        })
        self.assertEqual(len(q.allowed_resource_ids), 1)

        # Agregar recurso de otro almacén debe fallar
        with self.assertRaises(ValidationError):
            q.write({'allowed_resource_ids': [(4, self.wms_res_b1.id)]})

        with self.assertRaises(ValidationError):
            self.env['wms.queue'].create({
                'name': 'Invalid Res Queue',
                'code': 'INV_RES_Q',
                'warehouse_id': self.warehouse_a.id,
                'allowed_resource_ids': [(6, 0, [self.wms_res_b1.id])]
            })

    def test_at_queue_008_fail_closed_compatibility(self):
        """Validar semántica fail-closed en is_dispatchable()."""
        q = self.env['wms.queue'].create({
            'name': 'Fail Closed Queue',
            'code': 'FAIL_CLOSED',
            'warehouse_id': self.warehouse_a.id,
        })
        # Sin zonas ni recursos -> False
        self.assertFalse(q.is_dispatchable())

        # Solo zonas -> False
        q.write({'zone_ids': [(6, 0, [self.zone_a1.id])]})
        self.assertFalse(q.is_dispatchable())

        # Zonas y recursos -> True
        q.write({'allowed_resource_ids': [(6, 0, [self.wms_res_a1.id])]})
        self.assertTrue(q.is_dispatchable())

        # Archivada -> False
        q.write({'active': False})
        self.assertFalse(q.is_dispatchable())

    def test_at_queue_009_bidirectional_drift_protection(self):
        """Validar protección contra drift bidireccional cubriendo colas activas, archivadas y con usuario restringido."""
        # 1. Cola activa
        q_active = self.env['wms.queue'].create({
            'name': 'Active Drift Queue',
            'code': 'DRIFT_ACT',
            'warehouse_id': self.warehouse_a.id,
            'zone_ids': [(6, 0, [self.zone_a1.id])],
            'allowed_resource_ids': [(6, 0, [self.wms_res_a1.id])]
        })

        # Bloqueo en cola activa
        with self.assertRaises(ValidationError):
            self.zone_a1.write({'warehouse_id': self.warehouse_a2.id})
        with self.assertRaises(ValidationError):
            self.wms_res_a1.write({'warehouse_id': self.warehouse_a2.id})

        # 2. Cola archivada (active=False)
        zone_archived = self.env['wms.zone'].create({
            'name': 'Zone Archived', 'code': 'Z_ARCH', 'warehouse_id': self.warehouse_a.id
        })
        res_native_arch = self.env['resource.resource'].create({
            'name': 'Forklift Arch', 'resource_type': 'material', 'company_id': self.company_a.id
        })
        wms_res_arch = self.env['wms.resource'].create({
            'resource_id': res_native_arch.id, 'warehouse_id': self.warehouse_a.id
        })
        q_archived = self.env['wms.queue'].create({
            'name': 'Archived Drift Queue',
            'code': 'DRIFT_ARCH',
            'active': False,
            'warehouse_id': self.warehouse_a.id,
            'zone_ids': [(6, 0, [zone_archived.id])],
            'allowed_resource_ids': [(6, 0, [wms_res_arch.id])]
        })

        # Bloqueo también en cola archivada (active_test=False)
        with self.assertRaises(ValidationError):
            zone_archived.write({'warehouse_id': self.warehouse_a2.id})
        with self.assertRaises(ValidationError):
            wms_res_arch.write({'warehouse_id': self.warehouse_a2.id})

        # 3. Demostración de sudo(): usuario con permiso de editar zonas/recursos pero con record rule que le oculta la cola
        user_mgr_restricted = self.env['res.users'].create({
            'name': 'Manager Restricted Queue',
            'login': 'mgr_restricted_queue',
            'company_ids': [(6, 0, [self.company_a.id])],
            'company_id': self.company_a.id,
            'group_ids': [(6, 0, [
                self.env.ref('wms_core.group_wms_manager').id,
                self.env.ref('base.group_user').id
            ])]
        })
        # Regla que oculta q_active y q_archived al usuario restricted
        self.env['ir.rule'].create({
            'name': 'Hide Drift Queues',
            'model_id': self.env.ref('wms_queue.model_wms_queue').id,
            'domain_force': "[('code', 'not in', ['DRIFT_ACT', 'DRIFT_ARCH'])]",
            'groups': [(6, 0, [self.env.ref('wms_core.group_wms_manager').id])]
        })
        # Verificar que el usuario no ve la cola en búsqueda normal
        self.assertEqual(self.env['wms.queue'].with_user(user_mgr_restricted).search_count([('id', 'in', [q_active.id, q_archived.id])]), 0)

        # A pesar de no poder leer la cola por record rules, la protección contra drift con sudo() intercepta y bloquea
        # sin fugar información ni nombres de colas ocultas en el mensaje de error.
        with self.assertRaises(ValidationError) as cm_zone:
            self.zone_a1.with_user(user_mgr_restricted).write({'warehouse_id': self.warehouse_a2.id})
        self.assertNotIn('DRIFT_ACT', str(cm_zone.exception))
        self.assertNotIn('Active Drift Queue', str(cm_zone.exception))
        self.assertNotIn('DRIFT_ARCH', str(cm_zone.exception))
        self.assertNotIn('Archived Drift Queue', str(cm_zone.exception))

        with self.assertRaises(ValidationError) as cm_res:
            self.wms_res_a1.with_user(user_mgr_restricted).write({'warehouse_id': self.warehouse_a2.id})
        self.assertNotIn('DRIFT_ACT', str(cm_res.exception))
        self.assertNotIn('Active Drift Queue', str(cm_res.exception))
        self.assertNotIn('DRIFT_ARCH', str(cm_res.exception))
        self.assertNotIn('Archived Drift Queue', str(cm_res.exception))

        # Cola confidencial específica para verificar hermetismo estricto
        zone_secret = self.env['wms.zone'].create({
            'name': 'Zone Secret', 'code': 'Z_SEC', 'warehouse_id': self.warehouse_a.id
        })
        self.env['wms.queue'].create({
            'name': 'COLA SECRETA AUDITORIA',
            'code': 'DRIFT_SECRET',
            'warehouse_id': self.warehouse_a.id,
            'zone_ids': [(6, 0, [zone_secret.id])]
        })
        with self.assertRaises(ValidationError) as cm_sec:
            zone_secret.with_user(user_mgr_restricted).write({'warehouse_id': self.warehouse_a2.id})
        self.assertNotIn('COLA SECRETA AUDITORIA', str(cm_sec.exception))
        self.assertNotIn('DRIFT_SECRET', str(cm_sec.exception))

        # 4. Zona no vinculada (zone_a2) puede cambiar de almacén si no tiene ubicaciones asignadas
        self.zone_a2.write({'warehouse_id': self.warehouse_a2.id})
        self.assertEqual(self.zone_a2.warehouse_id, self.warehouse_a2)

    def test_at_queue_010_multi_company_isolation(self):
        """Validar aislamiento multi-compañía integral: derivación, consultas, CRUD cruzado y M2M cruzado."""
        # 1. Derivación inmutable y resistencia a inyección por contexto
        q_a = self.env['wms.queue'].with_context(default_company_id=self.company_b.id).create({
            'name': 'Queue Company A',
            'code': 'Q_COMP_A',
            'warehouse_id': self.warehouse_a.id,
            'company_id': self.company_b.id
        })
        self.assertEqual(q_a.company_id, self.company_a, "company_id debe derivarse siempre de warehouse_id.company_id.")
        q_a.write({'company_id': self.company_b.id})
        self.assertEqual(q_a.company_id, self.company_a, "company_id no puede ser modificado directamente.")

        # 2. Cola en Company B
        q_b = self.env['wms.queue'].create({
            'name': 'Queue Company B',
            'code': 'Q_COMP_B',
            'warehouse_id': self.warehouse_b.id,
        })

        # 3. Búsqueda y lectura bloqueada para Manager de Company A
        mgr_a_env = self.env['wms.queue'].with_user(self.user_mgr)
        self.assertFalse(mgr_a_env.search([('id', '=', q_b.id)]))
        with self.assertRaises(AccessError):
            mgr_a_env.browse(q_b.id).read(['name'])

        # 4. Creación cruzada bloqueada (Manager A intentando crear cola en almacén de Company B)
        with self.assertRaises(AccessError):
            mgr_a_env.create({
                'name': 'Cross Queue',
                'code': 'CROSS_Q',
                'warehouse_id': self.warehouse_b.id
            })

        # 5. Escritura cruzada bloqueada (Manager A intentando modificar cola de Company B)
        with self.assertRaises(AccessError):
            mgr_a_env.browse(q_b.id).write({'name': 'Hacked Queue B'})

        # 6. Bloqueo de asociaciones M2M cruzadas entre compañías
        with self.assertRaises(ValidationError):
            q_a.write({'zone_ids': [(4, self.zone_b1.id)]})

        with self.assertRaises(ValidationError):
            q_a.write({'allowed_resource_ids': [(4, self.wms_res_b1.id)]})

    def test_at_queue_011_rbac_matrix(self):
        """Validar matriz de seguridad RBAC: Operator Read, Supervisor Read, Manager CRUD, Admin CRUD."""
        q = self.env['wms.queue'].create({
            'name': 'RBAC Queue',
            'code': 'RBAC_Q',
            'warehouse_id': self.warehouse_a.id,
            'zone_ids': [(6, 0, [self.zone_a1.id])],
            'allowed_resource_ids': [(6, 0, [self.wms_res_a1.id])]
        })

        # Operator: Read OK, Write/Create/Unlink FAIL
        op_env = self.env['wms.queue'].with_user(self.user_op)
        op_queue = op_env.browse(q.id)
        self.assertEqual(op_queue.name, 'RBAC Queue')
        with self.assertRaises(AccessError):
            op_queue.write({'name': 'Operator Edited'})
        with self.assertRaises(AccessError):
            op_env.create({'name': 'Op New', 'code': 'OP_NEW', 'warehouse_id': self.warehouse_a.id})
        with self.assertRaises(AccessError):
            op_queue.unlink()

        # Supervisor: Read OK, Write/Create/Unlink FAIL
        sup_env = self.env['wms.queue'].with_user(self.user_sup)
        sup_queue = sup_env.browse(q.id)
        self.assertEqual(sup_queue.name, 'RBAC Queue')
        with self.assertRaises(AccessError):
            sup_queue.write({'name': 'Supervisor Edited'})
        with self.assertRaises(AccessError):
            sup_env.create({'name': 'Sup New', 'code': 'SUP_NEW', 'warehouse_id': self.warehouse_a.id})
        with self.assertRaises(AccessError):
            sup_queue.unlink()

        # Manager: CRUD OK
        mgr_env = self.env['wms.queue'].with_user(self.user_mgr)
        mgr_q = mgr_env.create({
            'name': 'Manager Created', 'code': 'MGR_NEW', 'warehouse_id': self.warehouse_a.id
        })
        self.assertTrue(mgr_q.id)
        mgr_q.write({'name': 'Manager Updated'})
        self.assertEqual(mgr_q.name, 'Manager Updated')
        mgr_q.unlink()

        # Admin: CRUD OK
        admin_env = self.env['wms.queue'].with_user(self.user_admin)
        admin_q = admin_env.create({
            'name': 'Admin Created', 'code': 'ADM_NEW', 'warehouse_id': self.warehouse_a.id
        })
        self.assertTrue(admin_q.id)
        admin_q.write({'name': 'Admin Updated'})
        admin_q.unlink()
