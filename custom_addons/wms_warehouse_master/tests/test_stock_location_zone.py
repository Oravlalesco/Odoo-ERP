from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestStockLocationZone(TransactionCase):
    """WM-006: Validar la relación stock.location ↔ wms.zone.

    Estos tests comprueban las 5 invariantes de la relación,
    lifecycle (hierarchy move, zone warehouse change), seguridad
    de mutación y protección contra context defaults.
    """

    @classmethod
    def setUpClass(cls):
        """Preparar topología multi-warehouse + multi-company.

        Company A:  Warehouse A1 (con Zone A1)
                    Warehouse A2 (con Zone A2)
        Company B:  Warehouse B  (con Zone B)

        Las locations de prueba se crean bajo view_location_id
        del warehouse correspondiente para que Odoo compute
        warehouse_id automáticamente.
        """
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        ResCompany = cls.env["res.company"]
        Warehouse = cls.env["stock.warehouse"]
        Location = cls.env["stock.location"]
        Zone = cls.env["wms.zone"]
        ResUsers = cls.env["res.users"]

        # Companies
        cls.company_a = cls.env.company
        cls.company_b = ResCompany.create({"name": "Company B"})

        # Warehouses — Odoo creates view_location_id automatically
        cls.warehouse_a1 = Warehouse.search(
            [("company_id", "=", cls.company_a.id)], limit=1
        )
        cls.warehouse_a2 = Warehouse.create({
            "name": "Warehouse A2",
            "code": "WHA2",
            "company_id": cls.company_a.id,
        })
        cls.warehouse_b = Warehouse.with_company(cls.company_b).create({
            "name": "Warehouse B",
            "code": "WHB",
            "company_id": cls.company_b.id,
        })

        # Zones
        cls.zone_a1 = Zone.create({
            "name": "Zone A1",
            "code": "ZA1",
            "warehouse_id": cls.warehouse_a1.id,
        })
        cls.zone_a2 = Zone.create({
            "name": "Zone A2",
            "code": "ZA2",
            "warehouse_id": cls.warehouse_a2.id,
        })
        cls.zone_b = Zone.with_company(cls.company_b).create({
            "name": "Zone B",
            "code": "ZB",
            "warehouse_id": cls.warehouse_b.id,
        })

        # Helper: create internal location under a warehouse
        def _make_internal(name, warehouse, company=None):
            company = company or warehouse.company_id
            return Location.with_company(company).create({
                "name": name,
                "usage": "internal",
                "location_id": warehouse.view_location_id.id,
                "company_id": company.id,
            })

        cls._make_internal = staticmethod(
            lambda name, wh, co=None: _make_internal(name, wh, co)
        )

        # Reference internal locations
        cls.loc_a1 = _make_internal("Loc A1", cls.warehouse_a1)
        cls.loc_a2 = _make_internal("Loc A2", cls.warehouse_a2)

        # Users for RBAC tests
        group_stock_manager = cls.env.ref("stock.group_stock_manager")
        group_stock_user = cls.env.ref("stock.group_stock_user")
        group_wms_operator = cls.env.ref("wms_core.group_wms_operator")
        group_wms_manager = cls.env.ref("wms_core.group_wms_manager")

        cls.operator_user = ResUsers.create({
            "name": "Zone Operator",
            "login": "zone_op",
            "group_ids": [
                Command.set([
                    group_stock_manager.id,
                    group_wms_operator.id,
                ]),
            ],
            "company_id": cls.company_a.id,
            "company_ids": [Command.set([cls.company_a.id])],
        })
        cls.manager_user = ResUsers.create({
            "name": "Zone Manager",
            "login": "zone_mgr",
            "group_ids": [
                Command.set([
                    group_stock_manager.id,
                    group_wms_manager.id,
                ]),
            ],
            "company_id": cls.company_a.id,
            "company_ids": [Command.set([cls.company_a.id])],
        })
        # Supervisor: stock_user + wms_supervisor (no stock_manager)
        group_wms_supervisor = cls.env.ref("wms_core.group_wms_supervisor")
        cls.supervisor_user = ResUsers.create({
            "name": "Zone Supervisor",
            "login": "zone_sup",
            "group_ids": [
                Command.set([
                    group_stock_manager.id,
                    group_wms_supervisor.id,
                ]),
            ],
            "company_id": cls.company_a.id,
            "company_ids": [Command.set([cls.company_a.id])],
        })

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-001: Field metadata
    # ------------------------------------------------------------------

    def test_loc_zone_01_field_exists_and_metadata(self):
        """TEST-LOC-ZONE-001: wms_zone_id metadata verificada."""
        field = self.env["stock.location"]._fields["wms_zone_id"]
        self.assertEqual(field.comodel_name, "wms.zone")
        self.assertFalse(field.required)
        self.assertEqual(field.ondelete, "restrict")
        self.assertTrue(field.check_company)
        self.assertTrue(field.index)
        self.assertTrue(field.copy)

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-002: Valid assignment
    # ------------------------------------------------------------------

    def test_loc_zone_02_valid_assignment(self):
        """TEST-LOC-ZONE-002: asignación válida — misma warehouse y company."""
        self.loc_a1.write({"wms_zone_id": self.zone_a1.id})
        self.assertEqual(self.loc_a1.wms_zone_id, self.zone_a1)

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-003: Default is False
    # ------------------------------------------------------------------

    def test_loc_zone_03_default_is_false(self):
        """TEST-LOC-ZONE-003: nueva location sin zone asignada."""
        Location = self.env["stock.location"]
        loc = Location.create({
            "name": "New Internal",
            "usage": "internal",
            "location_id": self.warehouse_a1.view_location_id.id,
            "company_id": self.company_a.id,
        })
        self.assertFalse(loc.wms_zone_id)

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-004: copy preserves zone
    # ------------------------------------------------------------------

    def test_loc_zone_04_copy_preserves_zone(self):
        """TEST-LOC-ZONE-004: copy() conserva wms_zone_id."""
        self.loc_a1.write({"wms_zone_id": self.zone_a1.id})
        copy = self.loc_a1.copy()
        self.assertEqual(copy.wms_zone_id, self.zone_a1)

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-005: non-internal + zone fails
    # ------------------------------------------------------------------

    def test_loc_zone_05_non_internal_with_zone_fails(self):
        """TEST-LOC-ZONE-005: usage != internal + zone → ValidationError."""
        Location = self.env["stock.location"]
        with self.assertRaises(ValidationError):
            Location.create({
                "name": "Customer Loc",
                "usage": "customer",
                "location_id": self.warehouse_a1.view_location_id.id,
                "wms_zone_id": self.zone_a1.id,
                "company_id": self.company_a.id,
            })

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-006: usage change with zone fails
    # ------------------------------------------------------------------

    def test_loc_zone_06_usage_change_with_zone_fails(self):
        """TEST-LOC-ZONE-006: internal→customer con zone → ValidationError."""
        self.loc_a1.write({"wms_zone_id": self.zone_a1.id})
        with self.assertRaises(ValidationError):
            self.loc_a1.write({"usage": "customer"})

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-007: no warehouse + zone fails
    # ------------------------------------------------------------------

    def test_loc_zone_07_no_warehouse_with_zone_fails(self):
        """TEST-LOC-ZONE-007: location sin warehouse + zone → ValidationError.

        Crear una ubicación interna fuera de la jerarquía de un warehouse.
        """
        Location = self.env["stock.location"]
        # Create a standalone view parent outside any warehouse
        standalone_parent = Location.create({
            "name": "Standalone View",
            "usage": "view",
            "company_id": self.company_a.id,
        })
        orphan = Location.create({
            "name": "Orphan Internal",
            "usage": "internal",
            "location_id": standalone_parent.id,
            "company_id": self.company_a.id,
        })
        self.assertFalse(orphan.warehouse_id)
        with self.assertRaises(ValidationError):
            orphan.write({"wms_zone_id": self.zone_a1.id})

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-008: warehouse mismatch fails
    # ------------------------------------------------------------------

    def test_loc_zone_08_warehouse_mismatch_fails(self):
        """TEST-LOC-ZONE-008: location WH-A1 + Zone WH-A2 (same company) → fail."""
        with self.assertRaises(ValidationError):
            self.loc_a1.write({"wms_zone_id": self.zone_a2.id})

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-009: shared location + zone fails
    # ------------------------------------------------------------------

    def test_loc_zone_09_shared_location_with_zone_fails(self):
        """TEST-LOC-ZONE-009: company_id=False + zone → ValidationError.

        Crear una ubicación compartida (sin compañía) e intentar asignarle
        una zona WMS company-owned.
        """
        Location = self.env["stock.location"]
        # Create a standalone view parent with no company
        shared_parent = Location.create({
            "name": "Shared View",
            "usage": "view",
            "company_id": False,
        })
        shared = Location.create({
            "name": "Shared Internal",
            "usage": "internal",
            "location_id": shared_parent.id,
            "company_id": False,
        })
        self.assertFalse(shared.company_id)
        with self.assertRaises(ValidationError):
            shared.write({"wms_zone_id": self.zone_a1.id})

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-010: hierarchy move with zone fails
    # ------------------------------------------------------------------

    def test_loc_zone_10_hierarchy_move_with_zone_fails(self):
        """TEST-LOC-ZONE-010: mover location a otro warehouse con zone → fail."""
        self.loc_a1.write({"wms_zone_id": self.zone_a1.id})
        with self.assertRaises(ValidationError):
            self.loc_a1.write({
                "location_id": self.warehouse_a2.view_location_id.id,
            })
        # After rollback: still in original warehouse with original zone
        self.loc_a1.invalidate_recordset()
        self.assertEqual(self.loc_a1.warehouse_id, self.warehouse_a1)
        self.assertEqual(self.loc_a1.wms_zone_id, self.zone_a1)

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-011: clear zone then move warehouse works
    # ------------------------------------------------------------------

    def test_loc_zone_11_clear_zone_then_move_works(self):
        """TEST-LOC-ZONE-011: desasignar zone → mover → PASS."""
        self.loc_a1.write({"wms_zone_id": self.zone_a1.id})
        self.loc_a1.write({"wms_zone_id": False})
        self.loc_a1.write({
            "location_id": self.warehouse_a2.view_location_id.id,
        })
        self.loc_a1.invalidate_recordset()
        self.assertEqual(self.loc_a1.warehouse_id, self.warehouse_a2)
        self.assertFalse(self.loc_a1.wms_zone_id)

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-012: zone warehouse change blocked when assigned
    # ------------------------------------------------------------------

    def test_loc_zone_12_zone_warehouse_change_blocked(self):
        """TEST-LOC-ZONE-012: cambiar Zone.warehouse con locations → fail.

        Incluye locations archivadas.
        """
        self.loc_a1.write({"wms_zone_id": self.zone_a1.id})
        # Zone archive does NOT break the relationship
        self.zone_a1.write({"active": False})
        self.assertEqual(self.loc_a1.wms_zone_id, self.zone_a1)
        self.assertFalse(self.zone_a1.active)
        self.zone_a1.write({"active": True})
        # Even if location is archived, warehouse change is blocked
        self.loc_a1.write({"active": False})
        with self.assertRaises(ValidationError):
            self.zone_a1.write({"warehouse_id": self.warehouse_a2.id})
        # Cleanup
        self.loc_a1.write({"active": True})

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-013: unused zone warehouse change allowed
    # ------------------------------------------------------------------

    def test_loc_zone_13_unused_zone_warehouse_change_allowed(self):
        """TEST-LOC-ZONE-013: Zone sin locations → warehouse puede cambiar."""
        Zone = self.env["wms.zone"]
        orphan_zone = Zone.create({
            "name": "Orphan Zone",
            "code": "ORPHAN",
            "warehouse_id": self.warehouse_a1.id,
        })
        orphan_zone.write({"warehouse_id": self.warehouse_a2.id})
        self.assertEqual(orphan_zone.warehouse_id, self.warehouse_a2)
        self.assertEqual(orphan_zone.company_id, self.company_a)

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-014: RBAC operator/supervisor blocked
    # ------------------------------------------------------------------

    def test_loc_zone_14_rbac_operator_supervisor_blocked(self):
        """TEST-LOC-ZONE-014: Operator y Supervisor no pueden asignar/limpiar zone."""
        loc = self.loc_a1
        # Operator cannot assign zone
        with self.assertRaises(AccessError):
            loc.with_user(self.operator_user).write({
                "wms_zone_id": self.zone_a1.id,
            })
        # Supervisor cannot assign zone
        with self.assertRaises(AccessError):
            loc.with_user(self.supervisor_user).write({
                "wms_zone_id": self.zone_a1.id,
            })
        # Assign zone as superuser for clear tests
        loc.write({"wms_zone_id": self.zone_a1.id})
        # Operator cannot clear zone
        with self.assertRaises(AccessError):
            loc.with_user(self.operator_user).write({
                "wms_zone_id": False,
            })
        # Supervisor cannot clear zone
        with self.assertRaises(AccessError):
            loc.with_user(self.supervisor_user).write({
                "wms_zone_id": False,
            })
        # Zone still assigned after failed clears
        self.assertEqual(loc.wms_zone_id, self.zone_a1)

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-015: RBAC manager/admin allowed
    # ------------------------------------------------------------------

    def test_loc_zone_15_rbac_manager_admin_allowed(self):
        """TEST-LOC-ZONE-015: Manager y System Admin pueden asignar/limpiar zone."""
        loc = self.loc_a1
        # Manager: assign
        loc.with_user(self.manager_user).write({
            "wms_zone_id": self.zone_a1.id,
        })
        self.assertEqual(loc.wms_zone_id, self.zone_a1)
        # Manager: clear
        loc.with_user(self.manager_user).write({"wms_zone_id": False})
        self.assertFalse(loc.wms_zone_id)
        # System Admin: assign
        admin = self.env.ref("base.user_admin")
        loc.with_user(admin).write({"wms_zone_id": self.zone_a1.id})
        self.assertEqual(loc.wms_zone_id, self.zone_a1)
        # System Admin: clear
        loc.with_user(admin).write({"wms_zone_id": False})
        self.assertFalse(loc.wms_zone_id)

    # ------------------------------------------------------------------
    # TEST-LOC-ZONE-016: context default bypass blocked
    # ------------------------------------------------------------------

    def test_loc_zone_16_context_default_bypass_blocked(self):
        """TEST-LOC-ZONE-016: Operator con default_wms_zone_id → AccessError."""
        Location = self.env["stock.location"]
        # Operator: context default blocked
        with self.assertRaises(AccessError):
            Location.with_user(self.operator_user).with_context(
                default_wms_zone_id=self.zone_a1.id,
            ).create({
                "name": "Context Test",
                "usage": "internal",
                "location_id": self.warehouse_a1.view_location_id.id,
                "company_id": self.company_a.id,
            })
        # Manager: context default allowed
        loc = Location.with_user(self.manager_user).with_context(
            default_wms_zone_id=self.zone_a1.id,
        ).create({
            "name": "Context Test OK",
            "usage": "internal",
            "location_id": self.warehouse_a1.view_location_id.id,
            "company_id": self.company_a.id,
        })
        self.assertEqual(loc.wms_zone_id, self.zone_a1)
