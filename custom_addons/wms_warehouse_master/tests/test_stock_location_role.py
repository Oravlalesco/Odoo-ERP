from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


# Los 12 roles WMS aprobados (ADR-026).
EXPECTED_ROLES = [
    "STORAGE",
    "RESERVE_STORAGE",
    "PICK_FACE",
    "RECEIVING",
    "QUALITY_HOLD",
    "QUARANTINE",
    "DAMAGE",
    "STAGING",
    "CONSOLIDATION",
    "PACKING",
    "CROSS_DOCK",
    "DOCK",
]


class TestStockLocationRole(TransactionCase):
    """Verificar el campo wms_location_role en stock.location.

    WM-002: Estos tests demuestran que el campo de rol WMS está
    correctamente definido, tiene default False, aplica la invariante
    usage='internal' y soporta semántica de copia.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Location = cls.env["stock.location"]
        # Usar la ubicación de stock del warehouse por defecto como padre.
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.parent_location = cls.warehouse.lot_stock_id

    def _create_internal(self, name, **kwargs):
        """Helper: crear una ubicación interna bajo el warehouse."""
        vals = {
            "name": name,
            "usage": "internal",
            "location_id": self.parent_location.id,
        }
        vals.update(kwargs)
        return self.Location.create(vals)

    # ------------------------------------------------------------------
    # Existencia del campo y catálogo
    # ------------------------------------------------------------------

    def test_wm_role_01_field_exists(self):
        """TEST-WM-ROLE-001: el campo wms_location_role existe en stock.location."""
        self.assertIn(
            "wms_location_role",
            self.Location._fields,
            "Campo wms_location_role no encontrado en stock.location",
        )

    def test_wm_role_02_catalog_has_12_values(self):
        """TEST-WM-ROLE-002: el catálogo contiene exactamente 12 roles aprobados."""
        field = self.Location._fields["wms_location_role"]
        # selection puede ser lista de tuplas o callable; obtener la lista.
        selection_list = field.selection
        keys = [key for key, _label in selection_list]
        self.assertEqual(len(keys), 12, f"Se esperaban 12 roles, se obtuvieron {len(keys)}")
        for role in EXPECTED_ROLES:
            self.assertIn(role, keys, f"Falta el rol aprobado: {role}")

    # ------------------------------------------------------------------
    # Semántica de default
    # ------------------------------------------------------------------

    def test_wm_role_03_default_is_false(self):
        """TEST-WM-ROLE-003: ubicación interna nueva tiene role=False por defecto."""
        loc = self._create_internal("Test Default Role")
        self.assertFalse(
            loc.wms_location_role,
            "La ubicación nueva debe tener wms_location_role=False",
        )

    # ------------------------------------------------------------------
    # Asignación en ubicaciones internas
    # ------------------------------------------------------------------

    def test_wm_role_04_all_roles_assignable_to_internal(self):
        """TEST-WM-ROLE-004: cada uno de los 12 roles se puede asignar a internal."""
        for role in EXPECTED_ROLES:
            loc = self._create_internal(
                f"Test {role}",
                wms_location_role=role,
            )
            self.assertEqual(loc.wms_location_role, role)

    def test_wm_role_05_assignment_does_not_change_usage(self):
        """TEST-WM-ROLE-005: asignar un rol NO modifica usage."""
        loc = self._create_internal("Test Usage Stable")
        loc.write({"wms_location_role": "PICK_FACE"})
        self.assertEqual(
            loc.usage,
            "internal",
            "El usage debe permanecer 'internal' después de asignar rol",
        )

    # ------------------------------------------------------------------
    # Constraint: el rol requiere usage='internal'
    # ------------------------------------------------------------------

    def test_wm_role_06_supplier_with_role_fails(self):
        """TEST-WM-ROLE-006: ubicación supplier con rol → ValidationError."""
        with self.assertRaises(ValidationError):
            self.Location.create({
                "name": "Bad Supplier",
                "usage": "supplier",
                "location_id": self.parent_location.location_id.id,
                "wms_location_role": "RECEIVING",
            })

    def test_wm_role_07_customer_with_role_fails(self):
        """TEST-WM-ROLE-007: ubicación customer con rol → ValidationError."""
        with self.assertRaises(ValidationError):
            self.Location.create({
                "name": "Bad Customer",
                "usage": "customer",
                "location_id": self.parent_location.location_id.id,
                "wms_location_role": "STAGING",
            })

    def test_wm_role_08_change_usage_with_role_fails(self):
        """TEST-WM-ROLE-008: cambiar internal→customer con rol → ValidationError."""
        loc = self._create_internal(
            "Test Change Usage",
            wms_location_role="STORAGE",
        )
        with self.assertRaises(ValidationError):
            loc.write({"usage": "customer"})

    # ------------------------------------------------------------------
    # Limpieza y copia
    # ------------------------------------------------------------------

    def test_wm_role_09_role_can_be_cleared(self):
        """TEST-WM-ROLE-009: el rol puede limpiarse a False."""
        loc = self._create_internal(
            "Test Clear Role",
            wms_location_role="DOCK",
        )
        loc.write({"wms_location_role": False})
        self.assertFalse(loc.wms_location_role)

    def test_wm_role_10_copy_preserves_role(self):
        """TEST-WM-ROLE-010: copy() conserva wms_location_role."""
        loc = self._create_internal(
            "Test Copy Source",
            wms_location_role="CONSOLIDATION",
        )
        copy = loc.copy()
        self.assertEqual(
            copy.wms_location_role,
            "CONSOLIDATION",
            "copy() debe conservar wms_location_role",
        )
