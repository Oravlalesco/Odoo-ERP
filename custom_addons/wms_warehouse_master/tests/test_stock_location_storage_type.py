from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestStockLocationStorageType(TransactionCase):
    """WM-013: Validar relación stock.location ↔ wms.storage.type.

    Cubre: field metadata, invariantes, usage lifecycle, company
    lifecycle, RBAC, context defaults y comparación Many2one.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Location = cls.env["stock.location"]
        cls.StorageType = cls.env["wms.storage.type"]

        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({
            "name": "ST-Loc Company B",
        })

        # Warehouse para Company A
        cls.warehouse_a = cls.env["stock.warehouse"].search([
            ("company_id", "=", cls.company_a.id),
        ], limit=1)

        # Storage types
        cls.st_a = cls.StorageType.create({
            "name": "Pallet Rack",
            "code": "PALLET_RACK",
        })
        cls.st_b = cls.StorageType.with_company(cls.company_b).create({
            "name": "Shelf B",
            "code": "SHELF_B",
            "company_id": cls.company_b.id,
        })

        # Internal location (Company A, with warehouse)
        cls.loc_internal = cls.Location.create({
            "name": "ST Test Internal",
            "usage": "internal",
            "location_id": cls.warehouse_a.lot_stock_id.id,
        })

        # Grupos
        stock_user_group = cls.env.ref("stock.group_stock_user")
        stock_manager_group = cls.env.ref("stock.group_stock_manager")
        wms_operator_group = cls.env.ref("wms_core.group_wms_operator")
        wms_supervisor_group = cls.env.ref("wms_core.group_wms_supervisor")
        wms_manager_group = cls.env.ref("wms_core.group_wms_manager")

        cls.operator_user = cls.env["res.users"].create({
            "name": "STL Operator",
            "login": "test_stl_operator",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [
                (6, 0, [stock_user_group.id, wms_operator_group.id]),
            ],
        })
        cls.supervisor_user = cls.env["res.users"].create({
            "name": "STL Supervisor",
            "login": "test_stl_supervisor",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [
                (6, 0, [stock_user_group.id, wms_supervisor_group.id]),
            ],
        })
        cls.stock_manager_user = cls.env["res.users"].create({
            "name": "STL Stock Manager",
            "login": "test_stl_stock_mgr",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [
                (6, 0, [stock_manager_group.id]),
            ],
        })
        cls.manager_user = cls.env["res.users"].create({
            "name": "STL WMS Manager",
            "login": "test_stl_wms_mgr",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [
                (6, 0, [stock_manager_group.id, wms_manager_group.id]),
            ],
        })
        cls.admin_user = cls.env.ref("base.user_admin")

    # ------------------------------------------------------------------
    # ST-LOC-001: Field metadata
    # ------------------------------------------------------------------

    def test_st_loc_01_field_metadata(self):
        """ST-LOC-001: wms_storage_type_id field metadata exacta."""
        f = self.Location._fields["wms_storage_type_id"]
        self.assertEqual(f.comodel_name, "wms.storage.type")
        self.assertFalse(f.required)
        # default=False means new locations have no ST assigned
        loc = self.Location.create({
            "name": "Default Check",
            "usage": "internal",
            "location_id": self.warehouse_a.lot_stock_id.id,
        })
        self.assertFalse(loc.wms_storage_type_id)
        self.assertEqual(f.ondelete, "restrict")
        self.assertTrue(f.check_company)
        self.assertTrue(f.index)
        self.assertTrue(f.copy)

    # ------------------------------------------------------------------
    # ST-LOC-002: Valid assignment
    # ------------------------------------------------------------------

    def test_st_loc_02_valid_assignment(self):
        """ST-LOC-002: asignación válida internal + same company."""
        self.loc_internal.write({
            "wms_storage_type_id": self.st_a.id,
        })
        self.assertEqual(
            self.loc_internal.wms_storage_type_id, self.st_a,
        )

    # ------------------------------------------------------------------
    # ST-LOC-003: Default is False
    # ------------------------------------------------------------------

    def test_st_loc_03_default_false(self):
        """ST-LOC-003: nueva ubicación sin storage type."""
        loc = self.Location.create({
            "name": "ST Default Test",
            "usage": "internal",
            "location_id": self.warehouse_a.lot_stock_id.id,
        })
        self.assertFalse(loc.wms_storage_type_id)

    # ------------------------------------------------------------------
    # ST-LOC-004: Copy preserves Storage Type
    # ------------------------------------------------------------------

    def test_st_loc_04_copy_preserves(self):
        """ST-LOC-004: copy conserva wms_storage_type_id."""
        self.loc_internal.write({
            "wms_storage_type_id": self.st_a.id,
        })
        copied = self.loc_internal.copy()
        self.assertEqual(copied.wms_storage_type_id, self.st_a)

    # ------------------------------------------------------------------
    # ST-LOC-005: Non-internal + Storage Type → rejected
    # ------------------------------------------------------------------

    def test_st_loc_05_non_internal_rejected(self):
        """ST-LOC-005: usage != internal + Storage Type → ValidationError."""
        with self.assertRaises(ValidationError):
            self.Location.create({
                "name": "Customer ST",
                "usage": "customer",
                "wms_storage_type_id": self.st_a.id,
            })

    # ------------------------------------------------------------------
    # ST-LOC-006: Usage change with Storage Type → blocked
    # ------------------------------------------------------------------

    def test_st_loc_06_usage_change_blocked(self):
        """ST-LOC-006: internal → customer con Storage Type → ValidationError."""
        self.loc_internal.write({
            "wms_storage_type_id": self.st_a.id,
        })
        with self.assertRaises(ValidationError):
            self.loc_internal.write({"usage": "customer"})
        # Rollback check: still internal
        self.assertEqual(self.loc_internal.usage, "internal")

    # ------------------------------------------------------------------
    # ST-LOC-007: Shared location + Storage Type → rejected
    # ------------------------------------------------------------------

    def test_st_loc_07_shared_location_rejected(self):
        """ST-LOC-007: company_id=False + Storage Type → ValidationError."""
        loc = self.Location.create({
            "name": "Shared Loc",
            "usage": "internal",
            "company_id": False,
        })
        with self.assertRaises(ValidationError):
            loc.write({"wms_storage_type_id": self.st_a.id})

    # ------------------------------------------------------------------
    # ST-LOC-008: Company mismatch
    # ------------------------------------------------------------------

    def test_st_loc_08_company_mismatch_rejected(self):
        """ST-LOC-008: Location Company A + ST Company B → rejected."""
        with self.assertRaises(ValidationError):
            self.loc_internal.write({
                "wms_storage_type_id": self.st_b.id,
            })

    # ------------------------------------------------------------------
    # ST-LOC-009: Internal without warehouse → allowed
    # ------------------------------------------------------------------

    def test_st_loc_09_no_warehouse_allowed(self):
        """ST-LOC-009: internal sin warehouse + same company → allowed."""
        loc = self.Location.create({
            "name": "No-WH Internal",
            "usage": "internal",
            "company_id": self.company_a.id,
            "location_id": False,
        })
        # Might not have warehouse_id
        loc.write({"wms_storage_type_id": self.st_a.id})
        self.assertEqual(loc.wms_storage_type_id, self.st_a)

    # ------------------------------------------------------------------
    # ST-LOC-010: Storage Type company change blocked when assigned
    # ------------------------------------------------------------------

    def test_st_loc_10_company_change_blocked_when_used(self):
        """ST-LOC-010: ST company change blocked when locations reference it."""
        st = self.StorageType.create({
            "name": "Lifecycle Test",
            "code": "LIFECYCLE",
        })
        loc = self.Location.create({
            "name": "Lifecycle Loc",
            "usage": "internal",
            "location_id": self.warehouse_a.lot_stock_id.id,
            "wms_storage_type_id": st.id,
        })
        with self.assertRaises(ValidationError):
            st.with_company(self.company_b).write({
                "company_id": self.company_b.id,
            })
        # Also blocked when location is archived
        loc.write({"active": False})
        with self.assertRaises(ValidationError):
            st.with_company(self.company_b).write({
                "company_id": self.company_b.id,
            })
        # Archive ST preserves relation
        st.write({"active": False})
        loc_fresh = self.Location.with_context(
            active_test=False,
        ).browse(loc.id)
        self.assertEqual(loc_fresh.wms_storage_type_id, st)

    # ------------------------------------------------------------------
    # ST-LOC-011: Unused ST company change allowed
    # ------------------------------------------------------------------

    def test_st_loc_11_unused_company_change_allowed(self):
        """ST-LOC-011: ST sin locations → company change permitido."""
        st = self.StorageType.create({
            "name": "Unused",
            "code": "UNUSED_LC",
        })
        st.with_company(self.company_b).write({
            "company_id": self.company_b.id,
        })
        st.invalidate_recordset()
        self.assertEqual(st.company_id, self.company_b)

    # ------------------------------------------------------------------
    # ST-LOC-012: Referenced ST delete restricted
    # ------------------------------------------------------------------

    def test_st_loc_12_delete_restricted(self):
        """ST-LOC-012: unlink ST referenciado → DB restrict."""
        st = self.StorageType.create({
            "name": "Delete Test",
            "code": "DEL_TEST",
        })
        self.Location.create({
            "name": "Del Loc",
            "usage": "internal",
            "location_id": self.warehouse_a.lot_stock_id.id,
            "wms_storage_type_id": st.id,
        })
        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                st.unlink()

    # ------------------------------------------------------------------
    # ST-LOC-013: Operator/Supervisor denied
    # ------------------------------------------------------------------

    def test_st_loc_13_operator_supervisor_denied(self):
        """ST-LOC-013: Operator y Supervisor no pueden assign/clear."""
        for user in (self.operator_user, self.supervisor_user):
            with self.assertRaises(AccessError):
                self.loc_internal.with_user(user).write({
                    "wms_storage_type_id": self.st_a.id,
                })
            # Clear attempt on a location that has ST assigned
            loc = self.Location.create({
                "name": f"RBAC-{user.login}",
                "usage": "internal",
                "location_id": self.warehouse_a.lot_stock_id.id,
                "wms_storage_type_id": self.st_a.id,
            })
            with self.assertRaises(AccessError):
                loc.with_user(user).write({
                    "wms_storage_type_id": False,
                })

    # ------------------------------------------------------------------
    # ST-LOC-014: Stock Manager alone denied
    # ------------------------------------------------------------------

    def test_st_loc_14_stock_manager_alone_denied(self):
        """ST-LOC-014: Stock Manager sin WMS Manager/System → denied."""
        with self.assertRaises(AccessError):
            self.loc_internal.with_user(self.stock_manager_user).write({
                "wms_storage_type_id": self.st_a.id,
            })
        loc = self.Location.create({
            "name": "RBAC-SM",
            "usage": "internal",
            "location_id": self.warehouse_a.lot_stock_id.id,
            "wms_storage_type_id": self.st_a.id,
        })
        with self.assertRaises(AccessError):
            loc.with_user(self.stock_manager_user).write({
                "wms_storage_type_id": False,
            })

    # ------------------------------------------------------------------
    # ST-LOC-015: Manager + System Admin allowed
    # ------------------------------------------------------------------

    def test_st_loc_15_manager_system_allowed(self):
        """ST-LOC-015: Manager y System Admin pueden assign/clear."""
        for user in (self.manager_user, self.admin_user):
            loc = self.Location.create({
                "name": f"RBAC-{user.login}-loc",
                "usage": "internal",
                "location_id": self.warehouse_a.lot_stock_id.id,
            })
            loc.with_user(user).write({
                "wms_storage_type_id": self.st_a.id,
            })
            self.assertEqual(loc.wms_storage_type_id, self.st_a)
            loc.with_user(user).write({
                "wms_storage_type_id": False,
            })
            self.assertFalse(loc.wms_storage_type_id)

    # ------------------------------------------------------------------
    # ST-LOC-016: Security regression
    # ------------------------------------------------------------------

    def test_st_loc_16_security_regression(self):
        """ST-LOC-016: context default + same-value M2O regression."""
        # Context default unauthorized → denied
        with self.assertRaises(AccessError):
            self.Location.with_user(
                self.operator_user,
            ).with_context(
                default_wms_storage_type_id=self.st_a.id,
            ).create({
                "name": "Context Default Hack",
                "usage": "internal",
                "location_id": self.warehouse_a.lot_stock_id.id,
            })

        # Context default Manager → allowed
        loc = self.Location.with_user(
            self.manager_user,
        ).with_context(
            default_wms_storage_type_id=self.st_a.id,
        ).create({
            "name": "Context Default OK",
            "usage": "internal",
            "location_id": self.warehouse_a.lot_stock_id.id,
        })
        self.assertEqual(loc.wms_storage_type_id, self.st_a)

        # Same-value M2O write by unauthorized (stock manager w/o WMS)
        # → no false AccessError since value doesn't change
        loc2 = self.Location.create({
            "name": "Same-Value Write",
            "usage": "internal",
            "location_id": self.warehouse_a.lot_stock_id.id,
            "wms_storage_type_id": self.st_a.id,
        })
        # Stock manager writes same ST value — should NOT trigger WMS error
        loc2.with_user(self.stock_manager_user).write({
            "wms_storage_type_id": self.st_a.id,
        })
        self.assertEqual(loc2.wms_storage_type_id, self.st_a)
