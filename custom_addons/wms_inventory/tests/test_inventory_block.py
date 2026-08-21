from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestInventoryBlock(TransactionCase):
    """Pruebas unitarias para wms.inventory.block (INV-002).

    Valida:
    - Contrato de modelo, campos funcionales y ausencia de campos prohibidos.
    - Scopes, block types y metadata de relaciones.
    - Matriz de validación para cada uno de los 5 scopes (LOCATION, PRODUCT_LOCATION, LOT, PACKAGE, OWNER_LOCATION).
    - Invariante de lote (product_id == lot_id.product_id).
    - Lifecycle metadata server-owned en creación individual y batch.
    - Liberación controlada vía action_release() y DB CHECK released_at >= blocked_at.
    - Restricción de liberación para operadores y rechazo de doble liberación.
    - Inmutabilidad estricta: prohibición de direct write y unlink.
    - Compatibilidad multi-compañía (check_company) y aislamiento por record rules.
    - Matriz RBAC completa para Operator, Supervisor, Manager, System Admin y Plain Internal.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Block = cls.env["wms.inventory.block"]
        cls.Users = cls.env["res.users"]
        cls.Company = cls.env["res.company"]
        cls.Partner = cls.env["res.partner"]
        cls.Location = cls.env["stock.location"]
        cls.Product = cls.env["product.product"]
        cls.Lot = cls.env["stock.lot"]
        cls.Package = cls.env["stock.package"]

        cls.main_company = cls.env.company

        # Ubicación interna
        cls.location_main = cls.Location.create({
            "name": "LOC-INV-01",
            "usage": "internal",
            "company_id": cls.main_company.id,
        })
        cls.location_shared = cls.Location.create({
            "name": "LOC-SHARED-01",
            "usage": "internal",
            "company_id": False,
        })

        # Productos
        cls.product_a = cls.Product.create({
            "name": "Product Alpha",
            "type": "consu",
            "is_storable": True,
            "company_id": cls.main_company.id,
        })
        cls.product_b = cls.Product.create({
            "name": "Product Beta",
            "type": "consu",
            "is_storable": True,
            "company_id": cls.main_company.id,
        })

        # Lotes
        cls.lot_a = cls.Lot.create({
            "name": "LOT-A-001",
            "product_id": cls.product_a.id,
            "company_id": cls.main_company.id,
        })
        cls.lot_b = cls.Lot.create({
            "name": "LOT-B-001",
            "product_id": cls.product_b.id,
            "company_id": cls.main_company.id,
        })

        # Paquete
        cls.package_main = cls.Package.create({
            "name": "PACK-INV-001",
        })

        # Propietario
        cls.owner_partner = cls.Partner.create({
            "name": "Logistics Owner Client",
        })

        # Grupos de seguridad
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_supervisor = cls.env.ref("wms_core.group_wms_supervisor")
        cls.group_manager = cls.env.ref("wms_core.group_wms_manager")
        cls.group_system = cls.env.ref("base.group_system")

        # Usuarios de prueba
        cls.user_operator = cls.Users.create({
            "name": "WMS Test Operator",
            "login": "wms_test_operator_inv",
            "email": "operator_inv@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_operator.id])],
        })
        cls.user_supervisor = cls.Users.create({
            "name": "WMS Test Supervisor",
            "login": "wms_test_supervisor_inv",
            "email": "supervisor_inv@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_supervisor.id])],
        })
        cls.user_manager = cls.Users.create({
            "name": "WMS Test Manager",
            "login": "wms_test_manager_inv",
            "email": "manager_inv@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_manager.id])],
        })
        cls.user_plain = cls.Users.create({
            "name": "WMS Test Plain Internal",
            "login": "wms_test_plain_inv",
            "email": "plain_inv@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id])],
        })
        cls.user_admin = cls.Users.create({
            "name": "WMS Test System Admin",
            "login": "wms_test_admin_inv",
            "email": "admin_inv@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_system.id])],
        })

    # ------------------------------------------------------------------
    # TEST-INV-003: Model contract & 12 functional fields
    # ------------------------------------------------------------------

    def test_inv_03_model_contract_and_field_inventory(self):
        """INV-003: wms.inventory.block registrado con 12 campos funcionales exactos y sin campos prohibidos."""
        self.assertIn("wms.inventory.block", self.env)
        model = self.env["wms.inventory.block"]

        self.assertEqual(model._name, "wms.inventory.block")
        self.assertEqual(model._description, "Bloqueo operacional de inventario WMS")
        self.assertEqual(model._rec_name, "reason")
        self.assertEqual(model._order, "blocked_at desc, id desc")
        self.assertTrue(model._check_company_auto)

        expected_functional_fields = {
            "company_id",
            "block_scope",
            "product_id",
            "location_id",
            "lot_id",
            "package_id",
            "owner_id",
            "block_type",
            "reason",
            "blocked_by",
            "blocked_at",
            "released_at",
        }
        odoo_technical_fields = {
            "id",
            "display_name",
            "create_uid",
            "create_date",
            "write_uid",
            "write_date",
        }
        actual_functional_fields = set(model._fields.keys()) - odoo_technical_fields
        self.assertEqual(
            actual_functional_fields,
            expected_functional_fields,
            "El modelo debe contener exacta y únicamente los 12 campos funcionales declarados",
        )
        for fname in expected_functional_fields:
            self.assertIn(
                fname,
                model._fields,
                f"Campo funcional '{fname}' debe existir en wms.inventory.block",
            )

        forbidden_fields = {
            "quant_id",
            "warehouse_id",
            "active",
            "state",
            "released_by",
            "name",
        }
        for fname in forbidden_fields:
            self.assertNotIn(
                fname,
                model._fields,
                f"Campo prohibido '{fname}' no debe existir en wms.inventory.block",
            )

    # ------------------------------------------------------------------
    # TEST-INV-004: Scopes and block types + relationship metadata
    # ------------------------------------------------------------------

    def test_inv_04_scopes_and_block_types_metadata(self):
        """INV-004: Scopes y block types exactos, ondelete restrict y check_company correcto."""
        model = self.env["wms.inventory.block"]

        scope_keys = {k for k, _ in model._fields["block_scope"].selection}
        self.assertEqual(
            scope_keys,
            {"LOCATION", "PRODUCT_LOCATION", "LOT", "PACKAGE", "OWNER_LOCATION"},
            "Scopes deben ser exactamente LOCATION, PRODUCT_LOCATION, LOT, PACKAGE, OWNER_LOCATION",
        )

        type_keys = {k for k, _ in model._fields["block_type"].selection}
        self.assertEqual(
            type_keys,
            {"CYCLE_COUNT", "INVESTIGATION", "HOLD", "CUSTOMS"},
            "Block types deben ser exactamente CYCLE_COUNT, INVESTIGATION, HOLD, CUSTOMS",
        )

        # ondelete="restrict" en todos los Many2one
        restricted_m2o = [
            "company_id",
            "product_id",
            "location_id",
            "lot_id",
            "package_id",
            "owner_id",
            "blocked_by",
        ]
        for fname in restricted_m2o:
            self.assertEqual(
                model._fields[fname].ondelete,
                "restrict",
                f"Campo '{fname}' debe tener ondelete='restrict'",
            )

        # check_company=True en dimensiones físicas y de producto
        for fname in ["product_id", "location_id", "lot_id", "package_id"]:
            self.assertTrue(
                model._fields[fname].check_company,
                f"Campo '{fname}' debe tener check_company=True",
            )
        self.assertFalse(
            getattr(model._fields["owner_id"], "check_company", False),
            "owner_id no debe tener check_company=True",
        )

        # product_id apunta a product.product
        self.assertEqual(
            model._fields["product_id"].comodel_name,
            "product.product",
            "product_id debe apuntar a product.product",
        )

    # ------------------------------------------------------------------
    # TEST-INV-005: LOCATION scope matrix
    # ------------------------------------------------------------------

    def test_inv_05_location_scope_matrix(self):
        """INV-005: Scope LOCATION exige únicamente location_id."""
        # Válido
        block = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.location_main.id,
            "block_type": "CYCLE_COUNT",
            "reason": "Conteo cíclico de ubicación",
        })
        self.assertTrue(block)

        # Inválido: falta location_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "LOCATION",
                    "block_type": "CYCLE_COUNT",
                    "reason": "Sin ubicación",
                })

        # Inválido: dimensión espuria product_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "LOCATION",
                    "location_id": self.location_main.id,
                    "product_id": self.product_a.id,
                    "block_type": "CYCLE_COUNT",
                    "reason": "Espurio producto",
                })

        # Inválido: dimensión espuria package_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "LOCATION",
                    "location_id": self.location_main.id,
                    "package_id": self.package_main.id,
                    "block_type": "CYCLE_COUNT",
                    "reason": "Espurio paquete",
                })

    # ------------------------------------------------------------------
    # TEST-INV-006: PRODUCT_LOCATION scope matrix
    # ------------------------------------------------------------------

    def test_inv_06_product_location_scope_matrix(self):
        """INV-006: Scope PRODUCT_LOCATION exige exactamente product_id y location_id."""
        # Válido
        block = self.Block.create({
            "block_scope": "PRODUCT_LOCATION",
            "product_id": self.product_a.id,
            "location_id": self.location_main.id,
            "block_type": "INVESTIGATION",
            "reason": "Investigación de SKU en pasillo",
        })
        self.assertTrue(block)

        # Inválido: falta product_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "PRODUCT_LOCATION",
                    "location_id": self.location_main.id,
                    "block_type": "INVESTIGATION",
                    "reason": "Falta producto",
                })

        # Inválido: falta location_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "PRODUCT_LOCATION",
                    "product_id": self.product_a.id,
                    "block_type": "INVESTIGATION",
                    "reason": "Falta ubicación",
                })

        # Inválido: dimensión espuria lot_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "PRODUCT_LOCATION",
                    "product_id": self.product_a.id,
                    "location_id": self.location_main.id,
                    "lot_id": self.lot_a.id,
                    "block_type": "INVESTIGATION",
                    "reason": "Espurio lote",
                })

    # ------------------------------------------------------------------
    # TEST-INV-007: LOT scope matrix & consistency invariant
    # ------------------------------------------------------------------

    def test_inv_07_lot_scope_matrix_and_consistency(self):
        """INV-007: Scope LOT exige product_id y lot_id, y producto debe coincidir con el lote."""
        # Válido
        block = self.Block.create({
            "block_scope": "LOT",
            "product_id": self.product_a.id,
            "lot_id": self.lot_a.id,
            "block_type": "HOLD",
            "reason": "Retención de lote por calidad",
        })
        self.assertTrue(block)

        # Inválido: falta product_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "LOT",
                    "lot_id": self.lot_a.id,
                    "block_type": "HOLD",
                    "reason": "Falta producto",
                })

        # Inválido: falta lot_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "LOT",
                    "product_id": self.product_a.id,
                    "block_type": "HOLD",
                    "reason": "Falta lote",
                })

        # Inválido: dimensión espuria location_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "LOT",
                    "product_id": self.product_a.id,
                    "lot_id": self.lot_a.id,
                    "location_id": self.location_main.id,
                    "block_type": "HOLD",
                    "reason": "Espurio ubicación",
                })

        # Inválido por constraint Python: product_id no coincide con lot_id.product_id
        with self.assertRaises(ValidationError):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "LOT",
                    "product_id": self.product_b.id,
                    "lot_id": self.lot_a.id,  # lot_a es de product_a
                    "block_type": "HOLD",
                    "reason": "Producto inconsistente con lote",
                })

    # ------------------------------------------------------------------
    # TEST-INV-008: PACKAGE scope matrix
    # ------------------------------------------------------------------

    def test_inv_08_package_scope_matrix(self):
        """INV-008: Scope PACKAGE exige únicamente package_id."""
        # Válido
        block = self.Block.create({
            "block_scope": "PACKAGE",
            "package_id": self.package_main.id,
            "block_type": "CUSTOMS",
            "reason": "Retención de contenedor por aduana",
        })
        self.assertTrue(block)

        # Inválido: falta package_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "PACKAGE",
                    "block_type": "CUSTOMS",
                    "reason": "Falta paquete",
                })

        # Inválido: dimensión espuria product_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "PACKAGE",
                    "package_id": self.package_main.id,
                    "product_id": self.product_a.id,
                    "block_type": "CUSTOMS",
                    "reason": "Espurio producto",
                })

    # ------------------------------------------------------------------
    # TEST-INV-009: OWNER_LOCATION scope matrix
    # ------------------------------------------------------------------

    def test_inv_09_owner_location_scope_matrix(self):
        """INV-009: Scope OWNER_LOCATION exige exactamente owner_id y location_id."""
        # Válido
        block = self.Block.create({
            "block_scope": "OWNER_LOCATION",
            "owner_id": self.owner_partner.id,
            "location_id": self.location_main.id,
            "block_type": "HOLD",
            "reason": "Retención de inventario consignado en zona",
        })
        self.assertTrue(block)

        # Inválido: falta owner_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "OWNER_LOCATION",
                    "location_id": self.location_main.id,
                    "block_type": "HOLD",
                    "reason": "Falta propietario",
                })

        # Inválido: falta location_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "OWNER_LOCATION",
                    "owner_id": self.owner_partner.id,
                    "block_type": "HOLD",
                    "reason": "Falta ubicación",
                })

        # Inválido: dimensión espuria package_id
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "OWNER_LOCATION",
                    "owner_id": self.owner_partner.id,
                    "location_id": self.location_main.id,
                    "package_id": self.package_main.id,
                    "block_type": "HOLD",
                    "reason": "Espurio paquete",
                })

    # ------------------------------------------------------------------
    # TEST-INV-010: Lifecycle metadata server-owned in create
    # ------------------------------------------------------------------

    def test_inv_10_lifecycle_metadata_server_owned(self):
        """INV-010: create() sobrescribe blocked_by, blocked_at y released_at incluso en batch."""
        # 1. Creación individual con valores falsificados
        block = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.location_main.id,
            "block_type": "HOLD",
            "reason": "Intento de falsificación de metadata",
            "blocked_by": self.user_operator.id,
            "blocked_at": "2020-01-01 00:00:00",
            "released_at": "2020-01-02 00:00:00",
        })
        self.assertEqual(block.blocked_by, self.env.user, "blocked_by debe ser el usuario actual de env")
        self.assertTrue(block.blocked_at, "blocked_at debe ser establecido por el servidor")
        self.assertFalse(block.released_at, "released_at debe ser False en la creación")

        # 2. Creación batch (@api.model_create_multi)
        blocks = self.Block.create([
            {
                "block_scope": "LOCATION",
                "location_id": self.location_main.id,
                "block_type": "HOLD",
                "reason": "Batch block 1",
                "released_at": "2020-01-01 00:00:00",
            },
            {
                "block_scope": "PACKAGE",
                "package_id": self.package_main.id,
                "block_type": "HOLD",
                "reason": "Batch block 2",
                "blocked_by": self.user_operator.id,
            },
        ])
        self.assertEqual(len(blocks), 2)
        for b in blocks:
            self.assertEqual(b.blocked_by, self.env.user)
            self.assertFalse(b.released_at)

    # ------------------------------------------------------------------
    # TEST-INV-011: Controlled release by supervisor
    # ------------------------------------------------------------------

    def test_inv_11_supervisor_release_and_timestamp_ordering(self):
        """INV-011: Supervisor puede liberar y released_at >= blocked_at."""
        block = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.location_main.id,
            "block_type": "INVESTIGATION",
            "reason": "Bloqueo para liberación",
        })
        self.assertFalse(block.released_at)

        # Liberación por Supervisor
        block.with_user(self.user_supervisor).action_release()
        self.assertTrue(block.released_at, "released_at debe estar establecido tras action_release")
        self.assertGreaterEqual(block.released_at, block.blocked_at, "released_at debe ser >= blocked_at")

    # ------------------------------------------------------------------
    # TEST-INV-012: Operator cannot release & double release rejected
    # ------------------------------------------------------------------

    def test_inv_12_operator_cannot_release_and_double_release_rejected(self):
        """INV-012: Operator no puede liberar (AccessError) y doble release es rechazado (UserError)."""
        block = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.location_main.id,
            "block_type": "HOLD",
            "reason": "Bloqueo para prueba de release",
        })

        # 1. Operator no puede liberar
        with self.assertRaises(AccessError):
            block.with_user(self.user_operator).action_release()

        # 2. Supervisor libera correctamente
        block.with_user(self.user_supervisor).action_release()
        self.assertTrue(block.released_at)

        # 3. Doble liberación rechazada con UserError
        with self.assertRaises(UserError):
            block.with_user(self.user_supervisor).action_release()

    # ------------------------------------------------------------------
    # TEST-INV-013: Immutable records (direct write and unlink prohibited)
    # ------------------------------------------------------------------

    def test_inv_13_immutable_records_direct_write_and_unlink_prohibited(self):
        """INV-013: write() directo y unlink() están terminantemente prohibidos."""
        block = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.location_main.id,
            "block_type": "HOLD",
            "reason": "Bloqueo inmutable",
        })

        # Intento de edición de motivo
        with self.assertRaises(UserError):
            block.write({"reason": "Nuevo motivo"})

        # Intento de edición directa de released_at
        with self.assertRaises(UserError):
            block.write({"released_at": fields.Datetime.now()})

        # Intento de eliminación
        with self.assertRaises(UserError):
            block.unlink()

    # ------------------------------------------------------------------
    # TEST-INV-014: check_company semantics
    # ------------------------------------------------------------------

    def test_inv_14_check_company_semantics(self):
        """INV-014: check_company admite dimensiones de misma compañía o compartidas, y rechaza foráneas."""
        foreign_company = self.Company.create({"name": "Foreign Logistics Co."})

        # Ubicación y producto de compañía foránea
        foreign_loc = self.Location.create({
            "name": "LOC-FOREIGN",
            "usage": "internal",
            "company_id": foreign_company.id,
        })
        foreign_prod = self.Product.create({
            "name": "Product Foreign",
            "type": "consu",
            "is_storable": True,
            "company_id": foreign_company.id,
        })

        # 1. Ubicación compartida (company_id=False) es aceptada
        block_shared = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.location_shared.id,
            "company_id": self.main_company.id,
            "block_type": "HOLD",
            "reason": "Bloqueo en ubicación compartida",
        })
        self.assertTrue(block_shared)

        # 2. Ubicación de compañía foránea es rechazada por check_company
        with self.assertRaises(UserError):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "LOCATION",
                    "location_id": foreign_loc.id,
                    "company_id": self.main_company.id,
                    "block_type": "HOLD",
                    "reason": "Ubicación foránea incompatible",
                })

        # 3. Producto de compañía foránea es rechazado por check_company
        with self.assertRaises(UserError):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "PRODUCT_LOCATION",
                    "product_id": foreign_prod.id,
                    "location_id": self.location_main.id,
                    "company_id": self.main_company.id,
                    "block_type": "HOLD",
                    "reason": "Producto foráneo incompatible",
                })

        # 4. Lote de compañía foránea es rechazado por check_company
        foreign_lot = self.Lot.create({
            "name": "LOT-FOREIGN",
            "product_id": foreign_prod.id,
            "company_id": foreign_company.id,
        })
        with self.assertRaises(UserError):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "LOT",
                    "product_id": foreign_prod.id,
                    "lot_id": foreign_lot.id,
                    "company_id": self.main_company.id,
                    "block_type": "HOLD",
                    "reason": "Lote foráneo incompatible",
                })

        # 5. Paquete con inventario de compañía foránea es rechazado por check_company
        foreign_package = self.Package.create({
            "name": "PACK-FOREIGN",
        })
        self.env["stock.quant"]._update_available_quantity(
            foreign_prod, foreign_loc, 10, package_id=foreign_package
        )
        self.assertEqual(
            foreign_package.company_id,
            foreign_company,
            "El paquete debe heredar company_id de la compañía foránea tras actualizar inventario",
        )
        with self.assertRaises(UserError):
            with self.cr.savepoint():
                self.Block.create({
                    "block_scope": "PACKAGE",
                    "package_id": foreign_package.id,
                    "company_id": self.main_company.id,
                    "block_type": "HOLD",
                    "reason": "Paquete foráneo incompatible",
                })

    # ------------------------------------------------------------------
    # TEST-INV-015: Multi-company record rule isolation
    # ------------------------------------------------------------------

    def test_inv_15_record_rule_multi_company_isolation(self):
        """INV-015: La regla multi-compañía aísla los bloqueos de compañías no autorizadas."""
        other_company = self.Company.create({"name": "Secondary Logistics Branch"})

        # Usuario exclusivo de other_company
        user_branch = self.Users.create({
            "name": "Branch Supervisor",
            "login": "branch_supervisor_inv",
            "email": "branch_supervisor@test.com",
            "company_id": other_company.id,
            "company_ids": [(6, 0, [other_company.id])],
            "group_ids": [(6, 0, [self.group_internal.id, self.group_supervisor.id])],
        })

        # Crear bloqueo en main_company
        block_main = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.location_main.id,
            "company_id": self.main_company.id,
            "block_type": "CYCLE_COUNT",
            "reason": "Bloqueo en compañía principal",
        })

        # user_branch no debe encontrar el bloqueo de main_company
        found_blocks = self.Block.with_user(user_branch).search([("id", "=", block_main.id)])
        self.assertFalse(found_blocks, "Record rule multi-compañía debe ocultar bloqueos de otras compañías")

        # user_branch lectura directa genera AccessError
        with self.assertRaises(AccessError):
            block_main.with_user(user_branch).read(["reason"])

    # ------------------------------------------------------------------
    # TEST-INV-016: Full RBAC matrix
    # ------------------------------------------------------------------

    def test_inv_16_rbac_matrix_effective(self):
        """INV-016: Matriz RBAC efectiva: Operator (R), Supervisor/Manager/Admin (R, C, release), Plain (sin acceso)."""
        # 1. Operator: puede leer, pero no crear ni liberar
        block = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.location_main.id,
            "block_type": "HOLD",
            "reason": "Bloqueo para matriz RBAC",
        })
        read_data = block.with_user(self.user_operator).read(["reason", "block_scope"])
        self.assertTrue(read_data, "Operator debe tener permiso de lectura")

        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_operator).create({
                "block_scope": "LOCATION",
                "location_id": self.location_main.id,
                "block_type": "HOLD",
                "reason": "Operator create no permitido",
            })

        # 2. Supervisor: puede crear y liberar, pero no direct write ni unlink
        sup_block = self.Block.with_user(self.user_supervisor).create({
            "block_scope": "PACKAGE",
            "package_id": self.package_main.id,
            "block_type": "INVESTIGATION",
            "reason": "Supervisor create",
        })
        self.assertTrue(sup_block)
        sup_block.with_user(self.user_supervisor).action_release()
        self.assertTrue(sup_block.released_at)

        with self.assertRaises(UserError):
            sup_block.with_user(self.user_supervisor).write({"reason": "Direct write no permitido"})

        with self.assertRaises(UserError):
            sup_block.with_user(self.user_supervisor).unlink()

        # 3. Manager: puede crear y liberar, pero no direct write ni unlink
        mgr_block = self.Block.with_user(self.user_manager).create({
            "block_scope": "LOCATION",
            "location_id": self.location_main.id,
            "block_type": "CUSTOMS",
            "reason": "Manager create",
        })
        self.assertTrue(mgr_block)
        mgr_block.with_user(self.user_manager).action_release()
        self.assertTrue(mgr_block.released_at)

        with self.assertRaises(UserError):
            mgr_block.with_user(self.user_manager).write({"reason": "Direct write no permitido"})

        with self.assertRaises(UserError):
            mgr_block.with_user(self.user_manager).unlink()

        # 4. System Admin: puede leer, crear y liberar, pero no direct write ni unlink
        admin_block = self.Block.with_user(self.user_admin).create({
            "block_scope": "LOCATION",
            "location_id": self.location_main.id,
            "block_type": "INVESTIGATION",
            "reason": "System Admin create",
        })
        self.assertTrue(admin_block)
        read_admin = admin_block.with_user(self.user_admin).read(["reason", "block_scope"])
        self.assertTrue(read_admin, "System Admin debe tener permiso de lectura")
        admin_block.with_user(self.user_admin).action_release()
        self.assertTrue(admin_block.released_at, "System Admin debe poder liberar el bloqueo")

        with self.assertRaises(UserError):
            admin_block.with_user(self.user_admin).write({"reason": "Direct write no permitido"})

        with self.assertRaises(UserError):
            admin_block.with_user(self.user_admin).unlink()

        # 5. Plain Internal: sin acceso de lectura ni creación
        with self.assertRaises(AccessError):
            block.with_user(self.user_plain).read(["reason"])

        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_plain).create({
                "block_scope": "LOCATION",
                "location_id": self.location_main.id,
                "block_type": "HOLD",
                "reason": "Plain internal no permitido",
            })
