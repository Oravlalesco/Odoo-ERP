from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestStockLocationAdmin(TransactionCase):
    """Verificar seguridad de mutación y UI del rol WMS en stock.location.

    WM-003: Estos tests demuestran que sólo usuarios autorizados
    (WMS Manager, System Admin, superuser) pueden modificar
    wms_location_role, y que la vista hereda correctamente
    stock.view_location_form.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Location = cls.env["stock.location"]
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.parent_location = cls.warehouse.lot_stock_id

        # Grupos relevantes
        stock_user_group = cls.env.ref("stock.group_stock_user")
        stock_manager_group = cls.env.ref("stock.group_stock_manager")
        wms_operator_group = cls.env.ref("wms_core.group_wms_operator")
        wms_supervisor_group = cls.env.ref("wms_core.group_wms_supervisor")
        wms_manager_group = cls.env.ref("wms_core.group_wms_manager")

        # Todos los usuarios de prueba tienen permisos nativos de stock
        # para aislar la protección WMS de los permisos Odoo.
        cls.operator_user = cls.env["res.users"].create({
            "name": "Test Operator",
            "login": "test_wms_operator",
            "group_ids": [
                (6, 0, [
                    stock_manager_group.id,
                    wms_operator_group.id,
                ]),
            ],
        })
        cls.supervisor_user = cls.env["res.users"].create({
            "name": "Test Supervisor",
            "login": "test_wms_supervisor",
            "group_ids": [
                (6, 0, [
                    stock_manager_group.id,
                    wms_supervisor_group.id,
                ]),
            ],
        })
        cls.manager_user = cls.env["res.users"].create({
            "name": "Test Manager",
            "login": "test_wms_manager",
            "group_ids": [
                (6, 0, [
                    stock_manager_group.id,
                    wms_manager_group.id,
                ]),
            ],
        })
        cls.admin_user = cls.env.ref("base.user_admin")

    def _create_internal_as_admin(self, name, **kwargs):
        """Helper: crear ubicación interna como superuser."""
        vals = {
            "name": name,
            "usage": "internal",
            "location_id": self.parent_location.id,
        }
        vals.update(kwargs)
        return self.Location.create(vals)

    # ------------------------------------------------------------------
    # Vista
    # ------------------------------------------------------------------

    def test_wm_admin_01_view_inherits_location_form(self):
        """TEST-WM-ADMIN-001: la vista WMS hereda stock.view_location_form."""
        view = self.env.ref(
            "wms_warehouse_master.view_location_form_wms_role"
        )
        self.assertTrue(view, "Vista WMS de stock.location no encontrada")
        self.assertEqual(
            view.inherit_id,
            self.env.ref("stock.view_location_form"),
            "La vista debe heredar stock.view_location_form",
        )

    # ------------------------------------------------------------------
    # Autorización de WRITE
    # ------------------------------------------------------------------

    def test_wm_admin_02_operator_cannot_change_role(self):
        """TEST-WM-ADMIN-002: Operator con stock manager NO puede cambiar rol."""
        loc = self._create_internal_as_admin("Test Op Write")
        with self.assertRaises(AccessError):
            loc.with_user(self.operator_user).write({
                "wms_location_role": "STORAGE",
            })

    def test_wm_admin_03_supervisor_cannot_change_role(self):
        """TEST-WM-ADMIN-003: Supervisor con stock manager NO puede cambiar rol."""
        loc = self._create_internal_as_admin("Test Sup Write")
        with self.assertRaises(AccessError):
            loc.with_user(self.supervisor_user).write({
                "wms_location_role": "PICK_FACE",
            })

    def test_wm_admin_04_manager_can_change_role(self):
        """TEST-WM-ADMIN-004: WMS Manager con stock manager puede cambiar rol."""
        loc = self._create_internal_as_admin("Test Mgr Write")
        loc.with_user(self.manager_user).write({
            "wms_location_role": "RECEIVING",
        })
        self.assertEqual(loc.wms_location_role, "RECEIVING")

    def test_wm_admin_05_system_admin_can_change_role(self):
        """TEST-WM-ADMIN-005: System Admin puede cambiar rol."""
        loc = self._create_internal_as_admin("Test Admin Write")
        loc.with_user(self.admin_user).write({
            "wms_location_role": "DOCK",
        })
        self.assertEqual(loc.wms_location_role, "DOCK")

    # ------------------------------------------------------------------
    # No interferencia con writes nativos
    # ------------------------------------------------------------------

    def test_wm_admin_06_operator_can_write_native_field(self):
        """TEST-WM-ADMIN-006: Operator puede modificar campo nativo (name)."""
        loc = self._create_internal_as_admin("Test Op Native")
        loc.with_user(self.operator_user).write({
            "name": "Renamed by Operator",
        })
        self.assertEqual(loc.name, "Renamed by Operator")

    # ------------------------------------------------------------------
    # Autorización de CREATE
    # ------------------------------------------------------------------

    def test_wm_admin_07_operator_cannot_create_with_role(self):
        """TEST-WM-ADMIN-007: Operator NO puede crear location con rol."""
        with self.assertRaises(AccessError):
            self.Location.with_user(self.operator_user).create({
                "name": "Bad Op Create",
                "usage": "internal",
                "location_id": self.parent_location.id,
                "wms_location_role": "STAGING",
            })

    def test_wm_admin_08_manager_can_create_with_role(self):
        """TEST-WM-ADMIN-008: Manager puede crear location con rol."""
        loc = self.Location.with_user(self.manager_user).create({
            "name": "Good Mgr Create",
            "usage": "internal",
            "location_id": self.parent_location.id,
            "wms_location_role": "CONSOLIDATION",
        })
        self.assertEqual(loc.wms_location_role, "CONSOLIDATION")

    # ------------------------------------------------------------------
    # Manager sigue sujeto a ADR-026
    # ------------------------------------------------------------------

    def test_wm_admin_09_manager_cannot_bypass_adr026(self):
        """TEST-WM-ADMIN-009: Manager no puede asignar rol con usage!=internal."""
        with self.assertRaises(ValidationError):
            self.Location.with_user(self.manager_user).create({
                "name": "Bad Mgr ADR026",
                "usage": "customer",
                "location_id": self.parent_location.location_id.id,
                "wms_location_role": "STORAGE",
            })
