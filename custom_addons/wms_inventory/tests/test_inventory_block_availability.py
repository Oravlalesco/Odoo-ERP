from unittest.mock import patch

from odoo.addons.stock.models.stock_quant import StockQuant
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestInventoryBlockAvailability(TransactionCase):
    """Pruebas unitarias para la guardia de disponibilidad operacional WMS (INV-004).

    Valida:
    - INV-029: API exacta y retorno float; ausencia de modelos y campos nuevos.
    - INV-030: Candidato libre de bloqueos retorna exactamente la disponibilidad nativa strict.
    - INV-031: Bloqueo LOCATION activo fuerza WMS disponible a 0.0 sin alterar stock nativo y ejecuta short-circuit.
    - INV-032: Bloqueos PRODUCT_LOCATION, LOT, PACKAGE y OWNER_LOCATION fuerzan 0.0 en match.
    - INV-033: action_release() restaura inmediatamente la disponibilidad WMS a la cantidad física nativa.
    - INV-034: Múltiples bloqueos solapados: liberar uno no restaura disponibilidad si queda otro activo.
    - INV-035: Frontera strict=True: el stock en ubicación hija no se agrega al candidato de ubicación padre.
    - INV-036: Multi-compañía y RBAC: Operator autorizado funciona; compañía no autorizada, usuario plain
               e incoherencia compañía-ubicación lanzan AccessError.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Block = cls.env["wms.inventory.block"]
        cls.Company = cls.env["res.company"]
        cls.Location = cls.env["stock.location"]
        cls.Product = cls.env["product.product"]
        cls.Lot = cls.env["stock.lot"]
        cls.Package = cls.env["stock.package"]
        cls.Partner = cls.env["res.partner"]
        cls.Quant = cls.env["stock.quant"]
        cls.Users = cls.env["res.users"]

        cls.main_company = cls.env.company

        # Jerarquía de ubicaciones
        # WH/Stock (loc_parent) -> Aisle-01 (loc_child) -> Bin-01 (loc_grandchild)
        cls.loc_root = cls.Location.create({
            "name": "WH-ROOT-AVAIL",
            "usage": "view",
            "company_id": cls.main_company.id,
        })
        cls.loc_parent = cls.Location.create({
            "name": "WH-STOCK-AVAIL",
            "usage": "internal",
            "location_id": cls.loc_root.id,
            "company_id": cls.main_company.id,
        })
        cls.loc_child = cls.Location.create({
            "name": "AISLE-01-AVAIL",
            "usage": "internal",
            "location_id": cls.loc_parent.id,
            "company_id": cls.main_company.id,
        })
        cls.loc_grandchild = cls.Location.create({
            "name": "BIN-01-AVAIL",
            "usage": "internal",
            "location_id": cls.loc_child.id,
            "company_id": cls.main_company.id,
        })

        # Productos
        cls.product_a = cls.Product.create({
            "name": "Product Alpha Availability",
            "type": "consu",
            "is_storable": True,
            "company_id": cls.main_company.id,
        })
        cls.product_b = cls.Product.create({
            "name": "Product Beta Availability",
            "type": "consu",
            "is_storable": True,
            "company_id": cls.main_company.id,
        })
        cls.product_tracked = cls.Product.create({
            "name": "Product Tracked Availability",
            "type": "consu",
            "is_storable": True,
            "tracking": "lot",
            "company_id": cls.main_company.id,
        })

        # Lotes
        cls.lot_a = cls.Lot.create({
            "name": "LOT-AVAIL-A",
            "product_id": cls.product_tracked.id,
            "company_id": cls.main_company.id,
        })
        cls.lot_b = cls.Lot.create({
            "name": "LOT-AVAIL-B",
            "product_id": cls.product_tracked.id,
            "company_id": cls.main_company.id,
        })

        # Jerarquía de paquetes: PALLET-01 -> CASE-01, PALLET-02
        cls.pallet_01 = cls.Package.create({"name": "PALLET-AVAIL-01"})
        cls.case_01 = cls.Package.create({
            "name": "CASE-AVAIL-01",
            "parent_package_id": cls.pallet_01.id,
        })
        cls.pallet_02 = cls.Package.create({"name": "PALLET-AVAIL-02"})

        # Propietarios
        cls.owner_partner = cls.Partner.create({"name": "Owner Partner Avail Alpha"})
        cls.other_partner = cls.Partner.create({"name": "Owner Partner Avail Beta"})

        # Grupos y usuarios
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_supervisor = cls.env.ref("wms_core.group_wms_supervisor")

        cls.user_operator = cls.Users.create({
            "name": "WMS Avail Operator",
            "login": "wms_avail_operator",
            "email": "avail_operator@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_operator.id])],
        })
        cls.user_supervisor = cls.Users.create({
            "name": "WMS Avail Supervisor",
            "login": "wms_avail_supervisor",
            "email": "avail_supervisor@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_supervisor.id])],
        })
        cls.user_plain = cls.Users.create({
            "name": "WMS Avail Plain Internal",
            "login": "wms_avail_plain",
            "email": "avail_plain@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id])],
        })

    # ------------------------------------------------------------------
    # TEST-INV-029: Firma de API, retorno float y verificación de contrato
    # ------------------------------------------------------------------

    def test_inv_29_availability_guard_api_and_return_type(self):
        """INV-029: get_unblocked_available_quantity retorna float y no existen modelos ni campos nuevos."""
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
        actual_functional_fields = set(self.Block._fields.keys()) - odoo_technical_fields
        self.assertEqual(
            actual_functional_fields,
            expected_functional_fields,
            "INV-004 no debe introducir campos adicionales en wms.inventory.block",
        )

        # Retorno tipo float
        qty = self.Block.get_unblocked_available_quantity(
            self.main_company,
            self.product_a,
            self.loc_child,
        )
        self.assertIsInstance(qty, float, "El valor retornado debe ser de tipo float")
        self.assertEqual(qty, 0.0)

        # Validación de parámetros requeridos
        with self.assertRaises(ValueError):
            self.Block.get_unblocked_available_quantity(False, self.product_a, self.loc_child)
        with self.assertRaises(ValueError):
            self.Block.get_unblocked_available_quantity(self.main_company, False, self.loc_child)
        with self.assertRaises(ValueError):
            self.Block.get_unblocked_available_quantity(self.main_company, self.product_a, False)

    # ------------------------------------------------------------------
    # TEST-INV-030: Candidato libre retorna disponibilidad nativa strict
    # ------------------------------------------------------------------

    def test_inv_30_free_candidate_returns_exact_native_strict_quantity(self):
        """INV-030: Un candidato sin bloqueos retorna exactamente la cantidad calculada por stock.quant (strict=True)."""
        # Establecer inventario inicial de 15.0 unidades
        self.Quant._update_available_quantity(
            self.product_a,
            self.loc_child,
            15.0,
        )

        wms_avail = self.Block.get_unblocked_available_quantity(
            self.main_company,
            self.product_a,
            self.loc_child,
        )
        self.assertEqual(wms_avail, 15.0, "La disponibilidad WMS libre debe coincidir con la nativa")
        self.assertIsInstance(wms_avail, float)

    # ------------------------------------------------------------------
    # TEST-INV-031: LOCATION activo fuerza 0.0, mantiene Odoo intacto y hace short-circuit
    # ------------------------------------------------------------------

    def test_inv_31_active_location_block_forces_zero_and_short_circuits(self):
        """INV-031: Bloqueo LOCATION activo retorna 0.0, no altera Odoo nativo y omite consulta a stock.quant."""
        self.Quant._update_available_quantity(
            self.product_a,
            self.loc_child,
            10.0,
        )
        native_before = self.Quant._get_available_quantity(
            self.product_a,
            self.loc_child,
            strict=True,
        )
        self.assertEqual(native_before, 10.0)

        # Crear bloqueo LOCATION en ubicación padre
        self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_parent.id,
            "block_type": "HOLD",
            "reason": "Bloqueo operacional de zona",
        })

        # Verificar short-circuit: _get_available_quantity de stock.quant no debe ser invocado
        with patch.object(
            StockQuant,
            "_get_available_quantity",
            side_effect=AssertionError("No se debe consultar _get_available_quantity cuando el candidato está bloqueado"),
        ):
            wms_avail = self.Block.get_unblocked_available_quantity(
                self.main_company,
                self.product_a,
                self.loc_child,
            )
            self.assertEqual(wms_avail, 0.0, "Candidato bloqueado debe retornar 0.0 inmediatamente")

        # Verificar que la disponibilidad nativa de Odoo permanece intacta
        native_after = self.Quant._get_available_quantity(
            self.product_a,
            self.loc_child,
            strict=True,
        )
        self.assertEqual(native_after, 10.0, "La disponibilidad nativa de Odoo no debe ser modificada por el WMS")

    # ------------------------------------------------------------------
    # TEST-INV-032: Scopes PRODUCT_LOCATION, LOT, PACKAGE, OWNER_LOCATION fuerzan 0.0
    # ------------------------------------------------------------------

    def test_inv_32_all_scope_blocks_force_zero_on_matching(self):
        """INV-032: PRODUCT_LOCATION, LOT, PACKAGE y OWNER_LOCATION fuerzan 0.0 únicamente sobre candidatos que coinciden."""
        # 1. PRODUCT_LOCATION
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0)
        self.Quant._update_available_quantity(self.product_b, self.loc_child, 5.0)
        b_pl = self.Block.create({
            "block_scope": "PRODUCT_LOCATION",
            "product_id": self.product_a.id,
            "location_id": self.loc_parent.id,
            "block_type": "INVESTIGATION",
            "reason": "Investigación SKU A",
        })
        self.assertEqual(self.Block.get_unblocked_available_quantity(self.main_company, self.product_a, self.loc_child), 0.0)
        self.assertEqual(self.Block.get_unblocked_available_quantity(self.main_company, self.product_b, self.loc_child), 5.0)
        b_pl.with_user(self.user_supervisor).action_release()

        # 2. LOT
        self.Quant._update_available_quantity(self.product_tracked, self.loc_child, 10.0, lot_id=self.lot_a)
        self.Quant._update_available_quantity(self.product_tracked, self.loc_child, 5.0, lot_id=self.lot_b)
        b_lot = self.Block.create({
            "block_scope": "LOT",
            "product_id": self.product_tracked.id,
            "lot_id": self.lot_a.id,
            "block_type": "HOLD",
            "reason": "Retención de lote A",
        })
        self.assertEqual(self.Block.get_unblocked_available_quantity(self.main_company, self.product_tracked, self.loc_child, lot_id=self.lot_a), 0.0)
        self.assertEqual(self.Block.get_unblocked_available_quantity(self.main_company, self.product_tracked, self.loc_child, lot_id=self.lot_b), 5.0)
        b_lot.with_user(self.user_supervisor).action_release()

        # 3. PACKAGE
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0, package_id=self.case_01)
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 5.0, package_id=self.pallet_02)
        b_pkg = self.Block.create({
            "block_scope": "PACKAGE",
            "package_id": self.pallet_01.id,
            "block_type": "CUSTOMS",
            "reason": "Aduana Pallet 1",
        })
        # case_01 está contenido en pallet_01 -> bloqueado
        self.assertEqual(self.Block.get_unblocked_available_quantity(self.main_company, self.product_a, self.loc_child, package_id=self.case_01), 0.0)
        # pallet_02 no está contenido -> libre
        self.assertEqual(self.Block.get_unblocked_available_quantity(self.main_company, self.product_a, self.loc_child, package_id=self.pallet_02), 5.0)
        b_pkg.with_user(self.user_supervisor).action_release()

        # 4. OWNER_LOCATION
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0, owner_id=self.owner_partner)
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 5.0, owner_id=self.other_partner)
        b_own = self.Block.create({
            "block_scope": "OWNER_LOCATION",
            "owner_id": self.owner_partner.id,
            "location_id": self.loc_parent.id,
            "block_type": "HOLD",
            "reason": "Retención propietario",
        })
        self.assertEqual(self.Block.get_unblocked_available_quantity(self.main_company, self.product_a, self.loc_child, owner_id=self.owner_partner), 0.0)
        self.assertEqual(self.Block.get_unblocked_available_quantity(self.main_company, self.product_a, self.loc_child, owner_id=self.other_partner), 5.0)
        b_own.with_user(self.user_supervisor).action_release()

    # ------------------------------------------------------------------
    # TEST-INV-033: action_release() restaura disponibilidad inmediatamente
    # ------------------------------------------------------------------

    def test_inv_33_action_release_immediately_restores_wms_availability(self):
        """INV-033: La liberación de un bloqueo restaura inmediatamente la disponibilidad WMS a la cantidad física."""
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 12.0)

        block = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_child.id,
            "block_type": "CYCLE_COUNT",
            "reason": "Bloqueo por inventario cíclico",
        })
        self.assertEqual(self.Block.get_unblocked_available_quantity(self.main_company, self.product_a, self.loc_child), 0.0)

        # Liberación por supervisor
        block.with_user(self.user_supervisor).action_release()
        self.assertTrue(block.released_at)

        # Disponibilidad restaurada de inmediato
        self.assertEqual(
            self.Block.get_unblocked_available_quantity(self.main_company, self.product_a, self.loc_child),
            12.0,
            "La disponibilidad WMS debe restaurarse a 12.0 tras la liberación",
        )

    # ------------------------------------------------------------------
    # TEST-INV-034: Múltiples bloqueos solapados exigen liberación de todos
    # ------------------------------------------------------------------

    def test_inv_34_overlapping_blocks_require_all_released(self):
        """INV-034: Con múltiples bloqueos activos, liberar uno no restaura disponibilidad si queda otro activo."""
        self.Quant._update_available_quantity(self.product_tracked, self.loc_child, 20.0, lot_id=self.lot_a)

        b1 = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_parent.id,
            "block_type": "HOLD",
            "reason": "Bloqueo de zona",
        })
        b2 = self.Block.create({
            "block_scope": "LOT",
            "product_id": self.product_tracked.id,
            "lot_id": self.lot_a.id,
            "block_type": "INVESTIGATION",
            "reason": "Investigación de lote",
        })

        self.assertEqual(
            self.Block.get_unblocked_available_quantity(self.main_company, self.product_tracked, self.loc_child, lot_id=self.lot_a),
            0.0,
        )

        # Liberar b1 -> b2 sigue activo -> 0.0
        b1.with_user(self.user_supervisor).action_release()
        self.assertEqual(
            self.Block.get_unblocked_available_quantity(self.main_company, self.product_tracked, self.loc_child, lot_id=self.lot_a),
            0.0,
            "Debe permanecer en 0.0 mientras b2 siga activo",
        )

        # Liberar b2 -> ya no quedan bloqueos activos -> 20.0
        b2.with_user(self.user_supervisor).action_release()
        self.assertEqual(
            self.Block.get_unblocked_available_quantity(self.main_company, self.product_tracked, self.loc_child, lot_id=self.lot_a),
            20.0,
            "Debe restaurarse a 20.0 cuando todos los bloqueos han sido liberados",
        )

    # ------------------------------------------------------------------
    # TEST-INV-035: Frontera strict=True no agrega stock de hijas en padre
    # ------------------------------------------------------------------

    def test_inv_35_strict_boundary_child_stock_not_aggregated_on_parent(self):
        """INV-035: stock en ubicación hija no se agrega al consultar el candidato padre (strict=True obligatorio)."""
        # Stock de 10 unidades colocado en AISLE-01 (loc_child), nada en WH-STOCK (loc_parent)
        self.Quant._update_available_quantity(
            self.product_a,
            self.loc_child,
            10.0,
        )

        # Disponibilidad nativa de Odoo con strict=False agrega hijos -> 10.0
        native_non_strict = self.Quant._get_available_quantity(
            self.product_a,
            self.loc_parent,
            strict=False,
        )
        self.assertEqual(native_non_strict, 10.0)

        # Disponibilidad nativa de Odoo con strict=True -> 0.0
        native_strict = self.Quant._get_available_quantity(
            self.product_a,
            self.loc_parent,
            strict=True,
        )
        self.assertEqual(native_strict, 0.0)

        # Guardia WMS en el padre debe ser 0.0 (candidato exacto)
        wms_parent_avail = self.Block.get_unblocked_available_quantity(
            self.main_company,
            self.product_a,
            self.loc_parent,
        )
        self.assertEqual(wms_parent_avail, 0.0, "La guardia WMS en la ubicación padre debe ser 0.0 con strict=True")

        # Guardia WMS en la ubicación hija donde reside el stock físico debe ser 10.0
        wms_child_avail = self.Block.get_unblocked_available_quantity(
            self.main_company,
            self.product_a,
            self.loc_child,
        )
        self.assertEqual(wms_child_avail, 10.0, "La guardia WMS en la ubicación hija debe ser 10.0")

    # ------------------------------------------------------------------
    # TEST-INV-036: Control de acceso multi-compañía, RBAC y validación company/location
    # ------------------------------------------------------------------

    def test_inv_36_multi_company_and_rbac_access_control(self):
        """INV-036: Operator funciona sin sudo; compañía no autorizada, usuario plain e incoherencia de compañía lanzan AccessError."""
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0)

        # A. Operator con compañía autorizada -> Funciona normalmente
        avail_op = self.Block.with_user(self.user_operator).get_unblocked_available_quantity(
            self.main_company,
            self.product_a,
            self.loc_child,
        )
        self.assertEqual(avail_op, 10.0)

        # B. Compañía no autorizada en env.companies -> AccessError
        foreign_company = self.Company.create({"name": "Unauthorized Foreign Company Avail"})
        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_operator).get_unblocked_available_quantity(
                foreign_company,
                self.product_a,
                self.loc_child,
            )

        # C. Plain internal user sin permisos ACL -> AccessError
        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_plain).get_unblocked_available_quantity(
                self.main_company,
                self.product_a,
                self.loc_child,
            )

        # D. Incoherencia company_id ↔ location_id:
        # Usuario autorizado para main_company y secondary_company, pero location_id pertenece a main_company
        # mientras el caller consulta con company_id = secondary_company
        secondary_company = self.Company.create({"name": "Secondary Authorized Company"})
        user_multi_company = self.Users.create({
            "name": "WMS Multi Company Operator",
            "login": "wms_multi_company_operator",
            "email": "multi_company_operator@test.com",
            "company_id": self.main_company.id,
            "company_ids": [(6, 0, [self.main_company.id, secondary_company.id])],
            "group_ids": [(6, 0, [self.group_internal.id, cls_group := self.group_operator.id])],
        })

        with self.assertRaises(AccessError):
            self.Block.with_user(user_multi_company).get_unblocked_available_quantity(
                secondary_company,
                self.product_a,
                self.loc_child,  # loc_child.company_id == main_company != secondary_company
            )
