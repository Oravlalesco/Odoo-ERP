from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestWmsStorageType(TransactionCase):
    """WM-011: Validar modelo wms.storage.type.

    Estos tests verifican identidad (company_id + code), normalización,
    constraints, seguridad RBAC, aislamiento multi-company y cambio
    de compañía permitido mientras no hay consumidores downstream.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.StorageType = cls.env["wms.storage.type"]

        # Compañías
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({
            "name": "Test Company B",
        })

        # Grupos
        stock_user_group = cls.env.ref("stock.group_stock_user")
        stock_manager_group = cls.env.ref("stock.group_stock_manager")
        wms_operator_group = cls.env.ref("wms_core.group_wms_operator")
        wms_supervisor_group = cls.env.ref("wms_core.group_wms_supervisor")
        wms_manager_group = cls.env.ref("wms_core.group_wms_manager")

        # Usuarios de prueba — Company A
        cls.operator_user = cls.env["res.users"].create({
            "name": "ST Operator",
            "login": "test_st_operator",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [
                (6, 0, [
                    stock_user_group.id,
                    wms_operator_group.id,
                ]),
            ],
        })
        cls.supervisor_user = cls.env["res.users"].create({
            "name": "ST Supervisor",
            "login": "test_st_supervisor",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [
                (6, 0, [
                    stock_user_group.id,
                    wms_supervisor_group.id,
                ]),
            ],
        })
        cls.manager_user = cls.env["res.users"].create({
            "name": "ST Manager",
            "login": "test_st_manager",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [
                (6, 0, [
                    stock_manager_group.id,
                    wms_manager_group.id,
                ]),
            ],
        })
        cls.admin_user = cls.env.ref("base.user_admin")

        # Reference storage type for reuse
        cls.st_a = cls.StorageType.create({
            "name": "Pallet Rack",
            "code": "PALLET_RACK",
        })

    # ------------------------------------------------------------------
    # TEST-ST-001: Model registration and field metadata
    # ------------------------------------------------------------------

    def test_st_01_model_registered_and_fields(self):
        """TEST-ST-001: modelo registrado con fields esperados."""
        ST = self.env["wms.storage.type"]
        self.assertEqual(ST._name, "wms.storage.type")
        self.assertEqual(ST._description, "WMS Storage Type")
        self.assertEqual(ST._order, "company_id, sequence, code, id")
        self.assertTrue(ST._check_company_auto)

        # name
        name_f = ST._fields["name"]
        self.assertTrue(name_f.required)

        # code
        code_f = ST._fields["code"]
        self.assertTrue(code_f.required)
        self.assertEqual(code_f.size, 32)

        # company_id
        co_f = ST._fields["company_id"]
        self.assertEqual(co_f.comodel_name, "res.company")
        self.assertTrue(co_f.required)
        self.assertEqual(co_f.ondelete, "restrict")
        self.assertTrue(co_f.index)

        # active, sequence
        self.assertIn("active", ST._fields)
        self.assertIn("sequence", ST._fields)

    # ------------------------------------------------------------------
    # TEST-ST-002: Minimal create
    # ------------------------------------------------------------------

    def test_st_02_create_minimal(self):
        """TEST-ST-002: crear con defaults correctos."""
        st = self.StorageType.create({
            "name": "Shelf",
            "code": "SHELF",
        })
        self.assertEqual(st.company_id, self.company_a)
        self.assertTrue(st.active)
        self.assertEqual(st.sequence, 10)

    # ------------------------------------------------------------------
    # TEST-ST-003: Create normalization
    # ------------------------------------------------------------------

    def test_st_03_create_normalization(self):
        """TEST-ST-003: código normalizado en create."""
        st = self.StorageType.create({
            "name": "Pallet Rack 2",
            "code": "  pallet_rack_2  ",
        })
        self.assertEqual(st.code, "PALLET_RACK_2")

    # ------------------------------------------------------------------
    # TEST-ST-004: Write normalization
    # ------------------------------------------------------------------

    def test_st_04_write_normalization(self):
        """TEST-ST-004: código normalizado en write."""
        st = self.StorageType.create({
            "name": "Temp",
            "code": "TEMP",
        })
        st.write({"code": "  shelf  "})
        self.assertEqual(st.code, "SHELF")

    # ------------------------------------------------------------------
    # TEST-ST-005: Blank code rejected
    # ------------------------------------------------------------------

    def test_st_05_blank_code_rejected(self):
        """TEST-ST-005: código vacío/whitespace → ValidationError."""
        with self.assertRaises(ValidationError):
            self.StorageType.create({
                "name": "Blank",
                "code": "   ",
            })

    # ------------------------------------------------------------------
    # TEST-ST-006: Duplicate code same Company
    # ------------------------------------------------------------------

    def test_st_06_duplicate_code_same_company_fails(self):
        """TEST-ST-006: mismo código normalizado en misma company → IntegrityError."""
        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.StorageType.create({
                    "name": "Duplicate",
                    "code": "PALLET_RACK",
                })

    # ------------------------------------------------------------------
    # TEST-ST-007: Same code different Companies
    # ------------------------------------------------------------------

    def test_st_07_same_code_different_companies_ok(self):
        """TEST-ST-007: mismo código en companies diferentes."""
        st_b = self.StorageType.with_company(self.company_b).create({
            "name": "Pallet Rack B",
            "code": "PALLET_RACK",
            "company_id": self.company_b.id,
        })
        self.assertEqual(st_b.code, "PALLET_RACK")
        self.assertEqual(st_b.company_id, self.company_b)
        # Original still exists in company A
        self.assertEqual(self.st_a.company_id, self.company_a)

    # ------------------------------------------------------------------
    # TEST-ST-008: Company change allowed (no consumers)
    # ------------------------------------------------------------------

    def test_st_08_company_change_allowed(self):
        """TEST-ST-008: cambiar company permitido sin consumidores downstream."""
        st = self.StorageType.create({
            "name": "Mobile",
            "code": "MOBILE",
        })
        self.assertEqual(st.company_id, self.company_a)
        st.with_company(self.company_b).write({
            "company_id": self.company_b.id,
        })
        st.invalidate_recordset()
        self.assertEqual(st.company_id, self.company_b)

    # ------------------------------------------------------------------
    # TEST-ST-009: Operator can read
    # ------------------------------------------------------------------

    def test_st_09_operator_can_read(self):
        """TEST-ST-009: Operator puede leer storage types."""
        types = self.StorageType.with_user(self.operator_user).search([
            ("company_id", "=", self.company_a.id),
        ])
        self.assertTrue(len(types) > 0)

    # ------------------------------------------------------------------
    # TEST-ST-010: Operator cannot mutate
    # ------------------------------------------------------------------

    def test_st_10_operator_cannot_mutate(self):
        """TEST-ST-010: Operator no puede create/write/unlink."""
        with self.assertRaises(AccessError):
            self.StorageType.with_user(self.operator_user).create({
                "name": "Hack",
                "code": "HACK",
            })
        with self.assertRaises(AccessError):
            self.st_a.with_user(self.operator_user).write({
                "name": "Hacked",
            })
        with self.assertRaises(AccessError):
            self.st_a.with_user(self.operator_user).unlink()

    # ------------------------------------------------------------------
    # TEST-ST-011: Supervisor read-only
    # ------------------------------------------------------------------

    def test_st_11_supervisor_read_only(self):
        """TEST-ST-011: Supervisor puede leer pero no create/write/unlink."""
        # Can read
        types = self.StorageType.with_user(self.supervisor_user).search([
            ("company_id", "=", self.company_a.id),
        ])
        self.assertTrue(len(types) > 0)
        # Cannot mutate
        with self.assertRaises(AccessError):
            self.StorageType.with_user(self.supervisor_user).create({
                "name": "Hack",
                "code": "HACK_S",
            })
        with self.assertRaises(AccessError):
            self.st_a.with_user(self.supervisor_user).write({
                "name": "Hacked",
            })
        with self.assertRaises(AccessError):
            self.st_a.with_user(self.supervisor_user).unlink()

    # ------------------------------------------------------------------
    # TEST-ST-012: Manager CRUD
    # ------------------------------------------------------------------

    def test_st_12_manager_crud(self):
        """TEST-ST-012: Manager puede CRUD completo."""
        st = self.StorageType.with_user(self.manager_user).create({
            "name": "Manager Type",
            "code": "MGR_TYPE",
        })
        self.assertTrue(st.id)
        st.with_user(self.manager_user).write({"name": "Updated"})
        self.assertEqual(st.name, "Updated")
        st.with_user(self.manager_user).read(["name"])
        st.with_user(self.manager_user).unlink()
        self.assertFalse(st.exists())

    # ------------------------------------------------------------------
    # TEST-ST-013: System Admin CRUD
    # ------------------------------------------------------------------

    def test_st_13_system_admin_crud(self):
        """TEST-ST-013: System Admin puede CRUD completo."""
        st = self.StorageType.with_user(self.admin_user).create({
            "name": "Admin Type",
            "code": "ADM_TYPE",
        })
        self.assertTrue(st.id)
        st.with_user(self.admin_user).write({"name": "Updated"})
        self.assertEqual(st.name, "Updated")
        st.with_user(self.admin_user).read(["name"])
        st.with_user(self.admin_user).unlink()
        self.assertFalse(st.exists())

    # ------------------------------------------------------------------
    # TEST-ST-014: Multi-company isolation
    # ------------------------------------------------------------------

    def test_st_14_multi_company_isolation(self):
        """TEST-ST-014: usuario Company A no ve Storage Type Company B."""
        st_b = self.StorageType.with_company(self.company_b).create({
            "name": "Type B",
            "code": "TYPE_B",
            "company_id": self.company_b.id,
        })

        # User A only — Company A
        user_a = self.env["res.users"].create({
            "name": "ST User A Only",
            "login": "test_st_user_a_only",
            "company_id": self.company_a.id,
            "company_ids": [(6, 0, [self.company_a.id])],
            "group_ids": [
                (6, 0, [
                    self.env.ref("stock.group_stock_manager").id,
                    self.env.ref("wms_core.group_wms_manager").id,
                ]),
            ],
        })
        visible = self.StorageType.with_user(user_a).search([])
        self.assertIn(self.st_a, visible)
        self.assertNotIn(st_b, visible)

        # Direct ID access to st_b → AccessError
        with self.assertRaises(AccessError):
            st_b.with_user(user_a).read(["name"])

        # User A+B — sees both
        user_ab = self.env["res.users"].create({
            "name": "ST User A+B",
            "login": "test_st_user_ab",
            "company_id": self.company_a.id,
            "company_ids": [(6, 0, [
                self.company_a.id, self.company_b.id,
            ])],
            "group_ids": [
                (6, 0, [
                    self.env.ref("stock.group_stock_manager").id,
                    self.env.ref("wms_core.group_wms_manager").id,
                ]),
            ],
        })
        visible_ab = self.StorageType.with_user(user_ab).search([])
        self.assertIn(self.st_a, visible_ab)
        self.assertIn(st_b, visible_ab)
