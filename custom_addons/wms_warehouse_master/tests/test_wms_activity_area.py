from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestWmsActivityArea(TransactionCase):
    """WM-008: Validar modelo wms.activity.area.

    Estos tests verifican identidad (zone_id + code), normalización,
    constraints, derivación warehouse/company, seguridad RBAC,
    aislamiento multi-company y protección de Zone ondelete.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Area = cls.env["wms.activity.area"]

        # Compañías
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({
            "name": "Test Company B",
        })

        # Warehouses
        cls.warehouse_a = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company_a.id)], limit=1,
        )
        cls.warehouse_b = cls.env["stock.warehouse"].create({
            "name": "Warehouse B",
            "code": "WHB",
            "company_id": cls.company_b.id,
        })

        # Zones — two in same warehouse A for TEST-AA-007
        cls.zone_a1 = cls.env["wms.zone"].create({
            "name": "Zone A1",
            "code": "ZA1",
            "warehouse_id": cls.warehouse_a.id,
        })
        cls.zone_a2 = cls.env["wms.zone"].create({
            "name": "Zone A2",
            "code": "ZA2",
            "warehouse_id": cls.warehouse_a.id,
        })
        cls.zone_b = cls.env["wms.zone"].with_company(cls.company_b).create({
            "name": "Zone B",
            "code": "ZB",
            "warehouse_id": cls.warehouse_b.id,
        })

        # Grupos
        stock_user_group = cls.env.ref("stock.group_stock_user")
        stock_manager_group = cls.env.ref("stock.group_stock_manager")
        wms_operator_group = cls.env.ref("wms_core.group_wms_operator")
        wms_supervisor_group = cls.env.ref("wms_core.group_wms_supervisor")
        wms_manager_group = cls.env.ref("wms_core.group_wms_manager")

        # Usuarios de prueba — Company A
        cls.operator_user = cls.env["res.users"].create({
            "name": "AA Operator",
            "login": "test_aa_operator",
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
            "name": "AA Supervisor",
            "login": "test_aa_supervisor",
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
            "name": "AA Manager",
            "login": "test_aa_manager",
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

        # Reference area for reuse
        cls.area_a1 = cls.Area.create({
            "name": "Pick Fast",
            "code": "PICK_FAST",
            "zone_id": cls.zone_a1.id,
        })

    # ------------------------------------------------------------------
    # TEST-AA-001: Model registration and field metadata
    # ------------------------------------------------------------------

    def test_aa_01_model_registered_and_fields(self):
        """TEST-AA-001: modelo registrado con fields esperados."""
        Area = self.env["wms.activity.area"]
        self.assertTrue(Area._name == "wms.activity.area")

        # zone_id metadata
        zone_f = Area._fields["zone_id"]
        self.assertEqual(zone_f.comodel_name, "wms.zone")
        self.assertTrue(zone_f.required)
        self.assertEqual(zone_f.ondelete, "restrict")
        self.assertTrue(zone_f.check_company)
        self.assertTrue(zone_f.index)

        # warehouse_id metadata — related, stored, readonly
        wh_f = Area._fields["warehouse_id"]
        self.assertTrue(wh_f.store)
        self.assertTrue(wh_f.readonly)

        # company_id metadata — related, stored, readonly
        co_f = Area._fields["company_id"]
        self.assertTrue(co_f.store)
        self.assertTrue(co_f.readonly)

        # active, sequence exist
        self.assertIn("active", Area._fields)
        self.assertIn("sequence", Area._fields)

        # code metadata
        code_f = Area._fields["code"]
        self.assertTrue(code_f.required)

    # ------------------------------------------------------------------
    # TEST-AA-002: Create minimal
    # ------------------------------------------------------------------

    def test_aa_02_create_minimal(self):
        """TEST-AA-002: crear con defaults correctos y derivación."""
        area = self.Area.create({
            "name": "Receive Dock",
            "code": "RCV",
            "zone_id": self.zone_a1.id,
        })
        self.assertTrue(area.active)
        self.assertEqual(area.sequence, 10)
        self.assertEqual(area.warehouse_id, self.warehouse_a)
        self.assertEqual(area.company_id, self.company_a)

    # ------------------------------------------------------------------
    # TEST-AA-003: Create normalization
    # ------------------------------------------------------------------

    def test_aa_03_create_normalization(self):
        """TEST-AA-003: código normalizado en create."""
        area = self.Area.create({
            "name": "Pick Area",
            "code": "  pick_a  ",
            "zone_id": self.zone_a1.id,
        })
        self.assertEqual(area.code, "PICK_A")

    # ------------------------------------------------------------------
    # TEST-AA-004: Write normalization
    # ------------------------------------------------------------------

    def test_aa_04_write_normalization(self):
        """TEST-AA-004: código normalizado en write."""
        area = self.Area.create({
            "name": "Temp",
            "code": "TEMP",
            "zone_id": self.zone_a1.id,
        })
        area.write({"code": "  updated_code  "})
        self.assertEqual(area.code, "UPDATED_CODE")

    # ------------------------------------------------------------------
    # TEST-AA-005: Blank code rejected
    # ------------------------------------------------------------------

    def test_aa_05_blank_code_rejected(self):
        """TEST-AA-005: código vacío/whitespace → ValidationError."""
        with self.assertRaises(ValidationError):
            self.Area.create({
                "name": "Blank",
                "code": "   ",
                "zone_id": self.zone_a1.id,
            })

    # ------------------------------------------------------------------
    # TEST-AA-006: Duplicate code same zone rejected
    # ------------------------------------------------------------------

    def test_aa_06_duplicate_code_same_zone_fails(self):
        """TEST-AA-006: mismo código normalizado en misma zona → IntegrityError."""
        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.Area.create({
                    "name": "Duplicate",
                    "code": "PICK_FAST",
                    "zone_id": self.zone_a1.id,
                })

    # ------------------------------------------------------------------
    # TEST-AA-007: Same code different zones allowed
    # ------------------------------------------------------------------

    def test_aa_07_same_code_different_zones_ok(self):
        """TEST-AA-007: mismo código en zonas diferentes (mismo warehouse)."""
        area_z2 = self.Area.create({
            "name": "Pick Fast Z2",
            "code": "PICK_FAST",
            "zone_id": self.zone_a2.id,
        })
        self.assertEqual(area_z2.code, "PICK_FAST")
        self.assertEqual(area_z2.zone_id, self.zone_a2)
        # Both zones belong to same warehouse
        self.assertEqual(self.zone_a1.warehouse_id, self.zone_a2.warehouse_id)

    # ------------------------------------------------------------------
    # TEST-AA-008: Zone change updates derived fields
    # ------------------------------------------------------------------

    def test_aa_08_zone_change_updates_derived(self):
        """TEST-AA-008: cambiar zone_id → warehouse/company siguen."""
        area = self.Area.create({
            "name": "Mobile",
            "code": "MOB",
            "zone_id": self.zone_a1.id,
        })
        self.assertEqual(area.warehouse_id, self.warehouse_a)
        self.assertEqual(area.company_id, self.company_a)

        # Change to zone_b (different warehouse, different company)
        area.with_company(self.company_b).write({
            "zone_id": self.zone_b.id,
        })
        area.invalidate_recordset()
        self.assertEqual(area.warehouse_id, self.warehouse_b)
        self.assertEqual(area.company_id, self.company_b)

    # ------------------------------------------------------------------
    # TEST-AA-009: Operator can read
    # ------------------------------------------------------------------

    def test_aa_09_operator_can_read(self):
        """TEST-AA-009: Operator puede leer areas."""
        areas = self.Area.with_user(self.operator_user).search([
            ("zone_id", "=", self.zone_a1.id),
        ])
        self.assertTrue(len(areas) > 0)

    # ------------------------------------------------------------------
    # TEST-AA-010: Operator cannot mutate
    # ------------------------------------------------------------------

    def test_aa_10_operator_cannot_mutate(self):
        """TEST-AA-010: Operator no puede create/write/unlink."""
        with self.assertRaises(AccessError):
            self.Area.with_user(self.operator_user).create({
                "name": "Hack",
                "code": "HACK",
                "zone_id": self.zone_a1.id,
            })
        with self.assertRaises(AccessError):
            self.area_a1.with_user(self.operator_user).write({
                "name": "Hacked",
            })
        with self.assertRaises(AccessError):
            self.area_a1.with_user(self.operator_user).unlink()

    # ------------------------------------------------------------------
    # TEST-AA-011: Supervisor read-only
    # ------------------------------------------------------------------

    def test_aa_11_supervisor_read_only(self):
        """TEST-AA-011: Supervisor puede leer pero no create/write/unlink."""
        # Can read
        areas = self.Area.with_user(self.supervisor_user).search([
            ("zone_id", "=", self.zone_a1.id),
        ])
        self.assertTrue(len(areas) > 0)
        # Cannot mutate
        with self.assertRaises(AccessError):
            self.Area.with_user(self.supervisor_user).create({
                "name": "Hack",
                "code": "HACK_S",
                "zone_id": self.zone_a1.id,
            })
        with self.assertRaises(AccessError):
            self.area_a1.with_user(self.supervisor_user).write({
                "name": "Hacked",
            })
        with self.assertRaises(AccessError):
            self.area_a1.with_user(self.supervisor_user).unlink()

    # ------------------------------------------------------------------
    # TEST-AA-012: Manager CRUD
    # ------------------------------------------------------------------

    def test_aa_12_manager_crud(self):
        """TEST-AA-012: Manager puede CRUD completo."""
        area = self.Area.with_user(self.manager_user).create({
            "name": "Manager Area",
            "code": "MGR",
            "zone_id": self.zone_a1.id,
        })
        self.assertTrue(area.id)
        area.with_user(self.manager_user).write({"name": "Updated"})
        self.assertEqual(area.name, "Updated")
        area.with_user(self.manager_user).read(["name"])
        area.with_user(self.manager_user).unlink()
        self.assertFalse(area.exists())

    # ------------------------------------------------------------------
    # TEST-AA-013: System Admin CRUD
    # ------------------------------------------------------------------

    def test_aa_13_system_admin_crud(self):
        """TEST-AA-013: System Admin puede CRUD completo."""
        area = self.Area.with_user(self.admin_user).create({
            "name": "Admin Area",
            "code": "ADM",
            "zone_id": self.zone_a1.id,
        })
        self.assertTrue(area.id)
        area.with_user(self.admin_user).write({"name": "Updated"})
        self.assertEqual(area.name, "Updated")
        area.with_user(self.admin_user).read(["name"])
        area.with_user(self.admin_user).unlink()
        self.assertFalse(area.exists())

    # ------------------------------------------------------------------
    # TEST-AA-014: Multi-company isolation
    # ------------------------------------------------------------------

    def test_aa_14_multi_company_isolation(self):
        """TEST-AA-014: usuario Company A no ve Area Company B."""
        area_b = self.Area.with_company(self.company_b).create({
            "name": "Area B",
            "code": "AB",
            "zone_id": self.zone_b.id,
        })

        # User A only — Company A
        user_a = self.env["res.users"].create({
            "name": "AA User A Only",
            "login": "test_aa_user_a_only",
            "company_id": self.company_a.id,
            "company_ids": [(6, 0, [self.company_a.id])],
            "group_ids": [
                (6, 0, [
                    self.env.ref("stock.group_stock_manager").id,
                    self.env.ref("wms_core.group_wms_manager").id,
                ]),
            ],
        })
        visible = self.Area.with_user(user_a).search([])
        self.assertIn(self.area_a1, visible)
        self.assertNotIn(area_b, visible)

        # Direct ID access to area_b → AccessError
        with self.assertRaises(AccessError):
            area_b.with_user(user_a).read(["name"])

        # User A+B — sees both
        user_ab = self.env["res.users"].create({
            "name": "AA User A+B",
            "login": "test_aa_user_ab",
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
        visible_ab = self.Area.with_user(user_ab).search([])
        self.assertIn(self.area_a1, visible_ab)
        self.assertIn(area_b, visible_ab)

    # ------------------------------------------------------------------
    # TEST-AA-015: Zone ondelete restrict
    # ------------------------------------------------------------------

    def test_aa_15_zone_ondelete_restrict(self):
        """TEST-AA-015: Zone con Activity Area no puede eliminarse."""
        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.zone_a1.unlink()
