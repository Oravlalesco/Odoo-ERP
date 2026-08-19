from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestWmsZone(TransactionCase):
    """Verificar modelo wms.zone — primer modelo persistente WMS.

    WM-004: Estos tests validan la identidad de zona (warehouse + code),
    normalización de código, constraints, seguridad RBAC y
    aislamiento multi-company.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Zone = cls.env["wms.zone"]

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

        # Grupos
        stock_user_group = cls.env.ref("stock.group_stock_user")
        stock_manager_group = cls.env.ref("stock.group_stock_manager")
        wms_operator_group = cls.env.ref("wms_core.group_wms_operator")
        wms_supervisor_group = cls.env.ref("wms_core.group_wms_supervisor")
        wms_manager_group = cls.env.ref("wms_core.group_wms_manager")

        # Usuarios de prueba — Company A
        cls.operator_user = cls.env["res.users"].create({
            "name": "Zone Operator",
            "login": "test_zone_operator",
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
            "name": "Zone Supervisor",
            "login": "test_zone_supervisor",
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
            "name": "Zone Manager",
            "login": "test_zone_manager",
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

        # Usuario multi-company (A + B)
        cls.multi_company_user = cls.env["res.users"].create({
            "name": "Zone Multi-Company",
            "login": "test_zone_multi",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id, cls.company_b.id])],
            "group_ids": [
                (6, 0, [
                    stock_manager_group.id,
                    wms_manager_group.id,
                ]),
            ],
        })

    # ------------------------------------------------------------------
    # Existencia del modelo y campos
    # ------------------------------------------------------------------

    def test_zone_01_model_registered(self):
        """TEST-ZONE-001: wms.zone está registrado y contiene los campos esperados."""
        self.assertIn("wms.zone", self.env)
        expected_fields = [
            "name", "code", "warehouse_id", "company_id",
            "active", "sequence",
        ]
        for field_name in expected_fields:
            self.assertIn(
                field_name,
                self.Zone._fields,
                f"Campo '{field_name}' no encontrado en wms.zone",
            )

    # ------------------------------------------------------------------
    # Creación básica
    # ------------------------------------------------------------------

    def test_zone_02_create_minimal(self):
        """TEST-ZONE-002: crear zona mínima con defaults correctos."""
        zone = self.Zone.create({
            "name": "High Rotation",
            "code": "FAST_PICK",
            "warehouse_id": self.warehouse_a.id,
        })
        self.assertTrue(zone.active)
        self.assertEqual(zone.sequence, 10)
        self.assertEqual(zone.company_id, self.warehouse_a.company_id)

    # ------------------------------------------------------------------
    # Normalización de código
    # ------------------------------------------------------------------

    def test_zone_03_code_normalized_on_create(self):
        """TEST-ZONE-003: code se normaliza a uppercase + trim en create."""
        zone = self.Zone.create({
            "name": "Test Normalize",
            "code": "  fast_pick ",
            "warehouse_id": self.warehouse_a.id,
        })
        self.assertEqual(zone.code, "FAST_PICK")

    def test_zone_04_code_normalized_on_write(self):
        """TEST-ZONE-004: normalización también ocurre en write."""
        zone = self.Zone.create({
            "name": "Test Write Norm",
            "code": "ORIGINAL",
            "warehouse_id": self.warehouse_a.id,
        })
        zone.write({"code": "  new_code  "})
        self.assertEqual(zone.code, "NEW_CODE")

    # ------------------------------------------------------------------
    # Constraint: code no puede ser blank
    # ------------------------------------------------------------------

    def test_zone_05_blank_code_rejected(self):
        """TEST-ZONE-005: código vacío/whitespace produce ValidationError."""
        with self.assertRaises(ValidationError):
            self.Zone.create({
                "name": "Bad Zone",
                "code": "   ",
                "warehouse_id": self.warehouse_a.id,
            })

    # ------------------------------------------------------------------
    # Constraint: unicidad warehouse + code
    # ------------------------------------------------------------------

    def test_zone_06_duplicate_code_same_warehouse_fails(self):
        """TEST-ZONE-006: mismo code normalizado en mismo warehouse falla."""
        self.Zone.create({
            "name": "Zone A",
            "code": "FAST_PICK",
            "warehouse_id": self.warehouse_a.id,
        })
        with self.assertRaises(Exception):
            self.Zone.create({
                "name": "Zone B",
                "code": " fast_pick ",
                "warehouse_id": self.warehouse_a.id,
            })

    def test_zone_07_same_code_different_warehouse_ok(self):
        """TEST-ZONE-007: mismo code en warehouses distintos es válido."""
        zone_a = self.Zone.create({
            "name": "Zone WH-A",
            "code": "BULK",
            "warehouse_id": self.warehouse_a.id,
        })
        zone_b = self.Zone.with_company(self.company_b).create({
            "name": "Zone WH-B",
            "code": "BULK",
            "warehouse_id": self.warehouse_b.id,
        })
        self.assertEqual(zone_a.code, "BULK")
        self.assertEqual(zone_b.code, "BULK")
        self.assertNotEqual(zone_a.warehouse_id, zone_b.warehouse_id)

    # ------------------------------------------------------------------
    # Company derivada del warehouse
    # ------------------------------------------------------------------

    def test_zone_08_company_follows_warehouse(self):
        """TEST-ZONE-008: company_id se deriva del warehouse."""
        zone = self.Zone.create({
            "name": "Zone Derive",
            "code": "DERIVE",
            "warehouse_id": self.warehouse_a.id,
        })
        self.assertEqual(zone.company_id, self.company_a)

    # ------------------------------------------------------------------
    # Seguridad RBAC
    # ------------------------------------------------------------------

    def test_zone_09_operator_can_read(self):
        """TEST-ZONE-009: Operator puede leer Zone de compañía permitida."""
        zone = self.Zone.create({
            "name": "Readable",
            "code": "READ_OP",
            "warehouse_id": self.warehouse_a.id,
        })
        zone_read = self.Zone.with_user(self.operator_user).browse(zone.id)
        self.assertEqual(zone_read.name, "Readable")

    def test_zone_10_operator_cannot_mutate(self):
        """TEST-ZONE-010: Operator NO puede create/write/unlink."""
        with self.assertRaises(AccessError):
            self.Zone.with_user(self.operator_user).create({
                "name": "Bad Create",
                "code": "BAD_OP",
                "warehouse_id": self.warehouse_a.id,
            })

    def test_zone_11_supervisor_read_only(self):
        """TEST-ZONE-011: Supervisor puede leer pero NO mutar."""
        zone = self.Zone.create({
            "name": "Sup Read",
            "code": "SUP_READ",
            "warehouse_id": self.warehouse_a.id,
        })
        # Read OK
        zone_read = self.Zone.with_user(self.supervisor_user).browse(zone.id)
        self.assertEqual(zone_read.code, "SUP_READ")
        # Write FAIL
        with self.assertRaises(AccessError):
            zone_read.write({"name": "Modified"})

    def test_zone_12_manager_crud(self):
        """TEST-ZONE-012: Manager puede create/read/write/unlink."""
        zone = self.Zone.with_user(self.manager_user).create({
            "name": "Manager Zone",
            "code": "MGR_ZONE",
            "warehouse_id": self.warehouse_a.id,
        })
        self.assertEqual(zone.code, "MGR_ZONE")
        zone.write({"name": "Updated"})
        self.assertEqual(zone.name, "Updated")
        zone.unlink()

    def test_zone_13_system_admin_crud(self):
        """TEST-ZONE-013: System Admin puede CRUD."""
        zone = self.Zone.with_user(self.admin_user).create({
            "name": "Admin Zone",
            "code": "ADM_ZONE",
            "warehouse_id": self.warehouse_a.id,
        })
        self.assertTrue(zone.exists())
        zone.write({"code": "ADM_UPDATED"})
        self.assertEqual(zone.code, "ADM_UPDATED")
        zone.unlink()

    # ------------------------------------------------------------------
    # Multi-company
    # ------------------------------------------------------------------

    def test_zone_14_multi_company_isolation(self):
        """TEST-ZONE-014: aislamiento multi-company correcto."""
        zone_a = self.Zone.create({
            "name": "Zone Co-A",
            "code": "MC_A",
            "warehouse_id": self.warehouse_a.id,
        })
        zone_b = self.Zone.with_company(self.company_b).create({
            "name": "Zone Co-B",
            "code": "MC_B",
            "warehouse_id": self.warehouse_b.id,
        })

        # Operator sólo Company A → NO ve Zone B
        zones_op = self.Zone.with_user(self.operator_user).search([])
        self.assertIn(zone_a, zones_op)
        self.assertNotIn(zone_b, zones_op)

        # Multi-company user (A+B) → ve ambas
        zones_multi = self.Zone.with_user(self.multi_company_user).search([])
        self.assertIn(zone_a, zones_multi)
        self.assertIn(zone_b, zones_multi)
