from odoo.tests.common import TransactionCase


class TestWmsSecurity(TransactionCase):
    """Verify WMS security taxonomy: category, privileges, and groups.

    CORE-002: These tests prove that the foundational WMS RBAC
    hierarchy is correctly installed and linked.
    """

    def test_sec_01_category_exists(self):
        """TEST-SEC-001: module_category_wms exists."""
        category = self.env.ref("wms_core.module_category_wms")
        self.assertTrue(category, "WMS category not found")
        self.assertEqual(category.name, "WMS")

    def test_sec_02_privilege_operations_exists(self):
        """TEST-SEC-002: privilege_wms_operations exists and belongs to WMS category."""
        privilege = self.env.ref("wms_core.privilege_wms_operations")
        self.assertTrue(privilege, "WMS Operations privilege not found")
        self.assertEqual(
            privilege.category_id,
            self.env.ref("wms_core.module_category_wms"),
            "Operations privilege should belong to WMS category",
        )

    def test_sec_03_privilege_configuration_exists(self):
        """TEST-SEC-003: privilege_wms_configuration exists and belongs to WMS category."""
        privilege = self.env.ref("wms_core.privilege_wms_configuration")
        self.assertTrue(privilege, "WMS Configuration privilege not found")
        self.assertEqual(
            privilege.category_id,
            self.env.ref("wms_core.module_category_wms"),
            "Configuration privilege should belong to WMS category",
        )

    def test_sec_04_operator_uses_operations_privilege(self):
        """TEST-SEC-004: group_wms_operator uses privilege_wms_operations."""
        group = self.env.ref("wms_core.group_wms_operator")
        self.assertTrue(group, "Operator group not found")
        self.assertEqual(
            group.privilege_id,
            self.env.ref("wms_core.privilege_wms_operations"),
            "Operator should use Operations privilege",
        )

    def test_sec_05_supervisor_uses_operations_privilege(self):
        """TEST-SEC-005: group_wms_supervisor uses privilege_wms_operations."""
        group = self.env.ref("wms_core.group_wms_supervisor")
        self.assertTrue(group, "Supervisor group not found")
        self.assertEqual(
            group.privilege_id,
            self.env.ref("wms_core.privilege_wms_operations"),
            "Supervisor should use Operations privilege",
        )

    def test_sec_06_supervisor_implies_operator(self):
        """TEST-SEC-006: Supervisor implies Operator."""
        supervisor = self.env.ref("wms_core.group_wms_supervisor")
        operator = self.env.ref("wms_core.group_wms_operator")
        self.assertIn(
            operator,
            supervisor.implied_ids,
            "Supervisor should imply Operator",
        )

    def test_sec_07_manager_uses_configuration_privilege(self):
        """TEST-SEC-007: group_wms_manager uses privilege_wms_configuration."""
        group = self.env.ref("wms_core.group_wms_manager")
        self.assertTrue(group, "Manager group not found")
        self.assertEqual(
            group.privilege_id,
            self.env.ref("wms_core.privilege_wms_configuration"),
            "Manager should use Configuration privilege",
        )

    def test_sec_08_manager_implies_supervisor(self):
        """TEST-SEC-008: Manager implies Supervisor."""
        manager = self.env.ref("wms_core.group_wms_manager")
        supervisor = self.env.ref("wms_core.group_wms_supervisor")
        self.assertIn(
            supervisor,
            manager.implied_ids,
            "Manager should imply Supervisor",
        )
