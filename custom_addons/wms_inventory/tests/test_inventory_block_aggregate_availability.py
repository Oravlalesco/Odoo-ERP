from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestInventoryBlockAggregateAvailability(TransactionCase):
    """Pruebas unitarias para el motor de disponibilidad agregada con bloqueos operacionales (INV-006).

    Valida:
    - INV-046: API exacta, retorno float, validación de recordsets/singletons, cero modelos/campos nuevos.
    - INV-047: Sin bloques: paridad exacta con Odoo strict=False; diferenciación con strict=True de INV-004.
    - INV-048: LOCATION y PRODUCT_LOCATION excluyen sólo los candidatos/subárboles aplicables.
    - INV-049: LOT: producto tracked, bloqueo location-independent y agregación nativa agrupada por lote.
    - INV-050: PACKAGE jerárquico y OWNER_LOCATION afectan correctamente la disponibilidad agregada.
    - INV-051: action_release() restaura inmediatamente la disponibilidad agregada.
    - INV-052: Bloqueos solapados no producen doble descuento; liberar uno no restaura si queda otro activo.
    - INV-053: Gate de negativos y monotonicidad: bloquear un quant negativo jamás incrementa la disponibilidad.
    - INV-054: Company scope y RBAC: raíz compartida con ubicaciones multi-compañía, Operator, Plain Internal,
               compañía no autorizada y raíz incompatible.
    - INV-055: Rendimiento y frontera: 1 _gather, 1 get_blocked_quants, 0 is_blocked, 0 guardia exacto,
               0 _get_available_quantity, sin mutación de quants ni reservas.
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

        # Topología de ubicaciones
        # WH-ROOT-AGG (loc_root)
        #   ├── WH-PARENT-AGG (loc_parent)
        #   │     ├── AISLE-01-AGG (loc_child)
        #   │     └── BIN-01-AGG (loc_grandchild)
        #   └── AISLE-02-AGG (loc_sibling)
        cls.loc_root = cls.Location.create({
            "name": "WH-ROOT-AGG",
            "usage": "internal",
            "company_id": cls.main_company.id,
        })
        cls.loc_parent = cls.Location.create({
            "name": "WH-PARENT-AGG",
            "usage": "internal",
            "location_id": cls.loc_root.id,
            "company_id": cls.main_company.id,
        })
        cls.loc_child = cls.Location.create({
            "name": "AISLE-01-AGG",
            "usage": "internal",
            "location_id": cls.loc_parent.id,
            "company_id": cls.main_company.id,
        })
        cls.loc_grandchild = cls.Location.create({
            "name": "BIN-01-AGG",
            "usage": "internal",
            "location_id": cls.loc_child.id,
            "company_id": cls.main_company.id,
        })
        cls.loc_sibling = cls.Location.create({
            "name": "AISLE-02-AGG",
            "usage": "internal",
            "location_id": cls.loc_root.id,
            "company_id": cls.main_company.id,
        })

        # Productos
        cls.product_a = cls.Product.create({
            "name": "Product Alpha Aggregate",
            "type": "consu",
            "is_storable": True,
            "company_id": cls.main_company.id,
        })
        cls.product_b = cls.Product.create({
            "name": "Product Beta Aggregate",
            "type": "consu",
            "is_storable": True,
            "company_id": cls.main_company.id,
        })
        cls.product_tracked = cls.Product.create({
            "name": "Product Tracked Aggregate",
            "type": "consu",
            "is_storable": True,
            "tracking": "lot",
            "company_id": cls.main_company.id,
        })

        # Lotes
        cls.lot_a = cls.Lot.create({
            "name": "LOT-AGG-A",
            "product_id": cls.product_tracked.id,
            "company_id": cls.main_company.id,
        })
        cls.lot_b = cls.Lot.create({
            "name": "LOT-AGG-B",
            "product_id": cls.product_tracked.id,
            "company_id": cls.main_company.id,
        })

        # Paquetes
        cls.pallet_01 = cls.Package.create({"name": "PALLET-AGG-01"})
        cls.case_01 = cls.Package.create({
            "name": "CASE-AGG-01",
            "parent_package_id": cls.pallet_01.id,
        })
        cls.pallet_02 = cls.Package.create({"name": "PALLET-AGG-02"})

        # Propietarios
        cls.owner_partner = cls.Partner.create({"name": "Owner Partner Aggregate Alpha"})
        cls.other_partner = cls.Partner.create({"name": "Owner Partner Aggregate Beta"})

        # Grupos y usuarios
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_supervisor = cls.env.ref("wms_core.group_wms_supervisor")

        cls.user_operator = cls.Users.create({
            "name": "WMS Aggregate Operator",
            "login": "wms_agg_operator",
            "email": "agg_operator@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_operator.id])],
        })
        cls.user_supervisor = cls.Users.create({
            "name": "WMS Aggregate Supervisor",
            "login": "wms_agg_supervisor",
            "email": "agg_supervisor@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_supervisor.id])],
        })
        cls.user_plain = cls.Users.create({
            "name": "WMS Aggregate Plain Internal",
            "login": "wms_agg_plain",
            "email": "agg_plain@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id])],
        })

    # ------------------------------------------------------------------
    # TEST-INV-046: Contrato de API, tipo de retorno y validación de parámetros
    # ------------------------------------------------------------------

    def test_inv_46_api_signature_and_parameter_validation(self):
        """INV-046: get_aggregate_unblocked_available_quantity retorna float y valida argumentos singleton requeridos."""
        # 1. Verificación de ausencia de modelos o campos nuevos
        self.assertIn("wms.inventory.block", self.env)
        functional_fields = [
            f for f in self.Block._fields
            if not f.startswith("__") and f not in ("id", "display_name", "create_uid", "create_date", "write_uid", "write_date")
        ]
        self.assertEqual(len(functional_fields), 12, "wms.inventory.block debe mantener exactamente 12 campos funcionales")

        # 2. Retorno float
        avail = self.Block.get_aggregate_unblocked_available_quantity(
            self.main_company,
            self.product_a,
            self.loc_root,
        )
        self.assertIsInstance(avail, float)
        self.assertEqual(avail, 0.0)

        # 3. Validaciones de tipos y singletons
        with self.assertRaises(ValueError):
            self.Block.get_aggregate_unblocked_available_quantity(False, self.product_a, self.loc_root)
        with self.assertRaises(ValueError):
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, False, self.loc_root)
        with self.assertRaises(ValueError):
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, False)
        with self.assertRaises(ValueError):
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root, lot_id=self.product_a)
        with self.assertRaises(ValueError):
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root, package_id=self.product_a)
        with self.assertRaises(ValueError):
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root, owner_id=self.product_a)

    # ------------------------------------------------------------------
    # TEST-INV-047: Sin bloques: paridad con Odoo strict=False y distinción con strict=True
    # ------------------------------------------------------------------

    def test_inv_47_native_parity_and_strictness_differentiation(self):
        """INV-047: Sin bloques, paridad exacta con Odoo strict=False y diferenciación con INV-004 strict=True."""
        # Inventario en subárbol: loc_child (10 disp, 2 res), loc_sibling (7 disp, 1 res)
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0)
        self.Quant._update_reserved_quantity(self.product_a, self.loc_child, 2.0)

        self.Quant._update_available_quantity(self.product_a, self.loc_sibling, 7.0)
        self.Quant._update_reserved_quantity(self.product_a, self.loc_sibling, 1.0)

        # 1. INV-006 (strict=False sobre loc_root): agrega subárbol -> (10-2) + (7-1) = 14.0
        agg_avail = self.Block.get_aggregate_unblocked_available_quantity(
            self.main_company,
            self.product_a,
            self.loc_root,
        )
        self.assertEqual(agg_avail, 14.0)

        # 2. INV-004 (strict=True sobre loc_root): candidato exacto en loc_root -> 0.0
        exact_avail = self.Block.get_unblocked_available_quantity(
            self.main_company,
            self.product_a,
            self.loc_root,
        )
        self.assertEqual(exact_avail, 0.0)
        self.assertNotEqual(agg_avail, exact_avail, "INV-006 (strict=False) debe diferir de INV-004 (strict=True) sobre la raíz")

    # ------------------------------------------------------------------
    # TEST-INV-048: Bloqueos LOCATION y PRODUCT_LOCATION en subárbol
    # ------------------------------------------------------------------

    def test_inv_48_location_and_product_location_aggregate_filtering(self):
        """INV-048: LOCATION y PRODUCT_LOCATION excluyen únicamente las cantidades del subárbol/producto aplicables."""
        # loc_child: 10 unidades de product_a, 5 de product_b
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0)
        self.Quant._update_available_quantity(self.product_b, self.loc_child, 5.0)

        # loc_sibling: 8 unidades de product_a, 4 de product_b
        self.Quant._update_available_quantity(self.product_a, self.loc_sibling, 8.0)
        self.Quant._update_available_quantity(self.product_b, self.loc_sibling, 4.0)

        # Baseline: product_a total = 18.0, product_b total = 9.0
        self.assertEqual(self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root), 18.0)
        self.assertEqual(self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_b, self.loc_root), 9.0)

        # 1. Bloqueo LOCATION en loc_parent (afecta a loc_child, excluye 10.0 de product_a y 5.0 de product_b)
        b_loc = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_parent.id,
            "block_type": "HOLD",
            "reason": "Bloqueo de zona parent",
        })
        self.assertEqual(self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root), 8.0)
        self.assertEqual(self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_b, self.loc_root), 4.0)
        b_loc.with_user(self.user_supervisor).action_release()

        # 2. Bloqueo PRODUCT_LOCATION en product_a + loc_sibling (excluye 8.0 de product_a en sibling; product_b intacto)
        b_pl = self.Block.create({
            "block_scope": "PRODUCT_LOCATION",
            "product_id": self.product_a.id,
            "location_id": self.loc_sibling.id,
            "block_type": "INVESTIGATION",
            "reason": "Investigación SKU A en sibling",
        })
        self.assertEqual(self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root), 10.0)
        self.assertEqual(self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_b, self.loc_root), 9.0)
        b_pl.with_user(self.user_supervisor).action_release()

    # ------------------------------------------------------------------
    # TEST-INV-049: Bloqueo LOT y aritmética nativa de productos tracked
    # ------------------------------------------------------------------

    def test_inv_49_lot_block_and_tracked_arithmetic_grouping(self):
        """INV-049: Bloqueo LOT es independiente de ubicación y agrupa correctamente disponibilidad por lote."""
        # LOT-A: 6 en loc_child, 4 en loc_sibling -> total 10.0
        self.Quant._update_available_quantity(self.product_tracked, self.loc_child, 6.0, lot_id=self.lot_a)
        self.Quant._update_available_quantity(self.product_tracked, self.loc_sibling, 4.0, lot_id=self.lot_a)

        # LOT-B: 5 en loc_grandchild -> total 5.0
        self.Quant._update_available_quantity(self.product_tracked, self.loc_grandchild, 5.0, lot_id=self.lot_b)

        # Total sin bloqueos = 15.0
        self.assertEqual(
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_tracked, self.loc_root),
            15.0,
        )

        # Bloqueo LOT en LOT-A
        b_lot = self.Block.create({
            "block_scope": "LOT",
            "product_id": self.product_tracked.id,
            "lot_id": self.lot_a.id,
            "block_type": "HOLD",
            "reason": "Retención lote A",
        })

        # Agregada general excluye todo LOT-A independientemente de su ubicación -> queda 5.0
        self.assertEqual(
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_tracked, self.loc_root),
            5.0,
        )

        # Consulta específica para LOT-A -> 0.0
        self.assertEqual(
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_tracked, self.loc_root, lot_id=self.lot_a),
            0.0,
        )
        # Consulta específica para LOT-B -> 5.0
        self.assertEqual(
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_tracked, self.loc_root, lot_id=self.lot_b),
            5.0,
        )
        b_lot.with_user(self.user_supervisor).action_release()

    # ------------------------------------------------------------------
    # TEST-INV-050: Bloqueos PACKAGE jerárquico y OWNER_LOCATION
    # ------------------------------------------------------------------

    def test_inv_50_package_and_owner_aggregate_filtering(self):
        """INV-050: Bloqueos PACKAGE y OWNER_LOCATION descuentan correctamente en disponibilidad agregada."""
        # 1. PACKAGE: pallet_01 contiene case_01
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0, package_id=self.case_01)
        self.Quant._update_available_quantity(self.product_a, self.loc_sibling, 5.0, package_id=self.pallet_02)

        # Bloqueo en pallet_01 (afecta a case_01)
        b_pkg = self.Block.create({
            "block_scope": "PACKAGE",
            "package_id": self.pallet_01.id,
            "block_type": "CUSTOMS",
            "reason": "Retención pallet 1",
        })
        self.assertEqual(
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root),
            5.0,
        )
        b_pkg.with_user(self.user_supervisor).action_release()

        # 2. OWNER_LOCATION
        self.Quant._update_available_quantity(self.product_b, self.loc_child, 8.0, owner_id=self.owner_partner)
        self.Quant._update_available_quantity(self.product_b, self.loc_sibling, 6.0, owner_id=self.other_partner)

        b_own = self.Block.create({
            "block_scope": "OWNER_LOCATION",
            "owner_id": self.owner_partner.id,
            "location_id": self.loc_parent.id,
            "block_type": "HOLD",
            "reason": "Retención propietario alpha",
        })
        self.assertEqual(
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_b, self.loc_root),
            6.0,
        )
        b_own.with_user(self.user_supervisor).action_release()

    # ------------------------------------------------------------------
    # TEST-INV-051: action_release() restaura disponibilidad agregada
    # ------------------------------------------------------------------

    def test_inv_51_action_release_restores_aggregate_availability(self):
        """INV-051: action_release() restaura de inmediato la disponibilidad agregada a la cantidad nativa."""
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 12.0)
        self.Quant._update_available_quantity(self.product_a, self.loc_sibling, 8.0)

        block = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_child.id,
            "block_type": "CYCLE_COUNT",
            "reason": "Inventario cíclico",
        })
        self.assertEqual(
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root),
            8.0,
        )

        block.with_user(self.user_supervisor).action_release()
        self.assertEqual(
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root),
            20.0,
        )

    # ------------------------------------------------------------------
    # TEST-INV-052: Bloqueos solapados no generan doble descuento
    # ------------------------------------------------------------------

    def test_inv_52_overlapping_blocks_no_double_discount_and_partial_release(self):
        """INV-052: Bloqueos solapados sobre el mismo quant no duplican descuento y liberar uno no restaura si queda otro."""
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0)
        self.Quant._update_available_quantity(self.product_a, self.loc_sibling, 5.0)

        # Bloqueo 1: LOCATION en loc_child
        b1 = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_child.id,
            "block_type": "HOLD",
            "reason": "Bloqueo ubicación",
        })
        # Bloqueo 2: PRODUCT_LOCATION en product_a + loc_child
        b2 = self.Block.create({
            "block_scope": "PRODUCT_LOCATION",
            "product_id": self.product_a.id,
            "location_id": self.loc_child.id,
            "block_type": "INVESTIGATION",
            "reason": "Bloqueo producto-ubicación",
        })

        # Ambos bloqueos cubren el quant de 10.0 en loc_child; la disponibilidad debe ser 5.0 (no -5.0)
        self.assertEqual(
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root),
            5.0,
        )

        # Liberar b1 -> b2 sigue activo -> permanece en 5.0
        b1.with_user(self.user_supervisor).action_release()
        self.assertEqual(
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root),
            5.0,
        )

        # Liberar b2 -> ambos liberados -> 15.0
        b2.with_user(self.user_supervisor).action_release()
        self.assertEqual(
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root),
            15.0,
        )

    # ------------------------------------------------------------------
    # TEST-INV-053: Gate de negativos y monotonicidad (bloquear nunca incrementa disponibilidad)
    # ------------------------------------------------------------------

    def test_inv_53_negative_quant_monotonicity_and_uom_precision(self):
        """INV-053: Bloquear un quant negativo jamás puede incrementar la disponibilidad por encima del baseline nativo."""
        # 1. Untracked: BIN-A = +10, BIN-B = -5 -> Baseline nativo = 5.0
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0)
        self.Quant._update_available_quantity(self.product_a, self.loc_sibling, -5.0)

        native_baseline = self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root)
        self.assertEqual(native_baseline, 5.0)

        # Bloquear BIN-B (el quant negativo de -5).
        # Sin la cota de monotonicidad, la disponibilidad filtrada sería 10.0.
        # Con monotonicidad, result = min(5.0, 10.0) = 5.0.
        b_neg = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_sibling.id,
            "block_type": "HOLD",
            "reason": "Bloqueo en ubicación con negativo",
        })
        avail_after_block = self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_a, self.loc_root)
        self.assertLessEqual(avail_after_block, native_baseline, "Un bloqueo jamás puede incrementar la disponibilidad")
        self.assertEqual(avail_after_block, 5.0)
        self.assertTrue(self.product_a.uom_id.compare(avail_after_block, 0.0) >= 0)
        b_neg.with_user(self.user_supervisor).action_release()

        # 2. Tracked: LOT-A = -4, LOT-B = +7 -> Aritmética nativa suma grupos positivos = 7.0
        self.Quant._update_available_quantity(self.product_tracked, self.loc_child, -4.0, lot_id=self.lot_a)
        self.Quant._update_available_quantity(self.product_tracked, self.loc_sibling, 7.0, lot_id=self.lot_b)

        tracked_native = self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_tracked, self.loc_root)
        self.assertEqual(tracked_native, 7.0)

        # Bloquear LOT-B -> queda LOT-A (-4 -> clamp 0) -> disponibilidad = 0.0
        b_lot_b = self.Block.create({
            "block_scope": "LOT",
            "product_id": self.product_tracked.id,
            "lot_id": self.lot_b.id,
            "block_type": "HOLD",
            "reason": "Bloqueo lote B",
        })
        self.assertEqual(
            self.Block.get_aggregate_unblocked_available_quantity(self.main_company, self.product_tracked, self.loc_root),
            0.0,
        )
        b_lot_b.with_user(self.user_supervisor).action_release()

        # 3. Untracked: precisión sub-rounding de UoM
        # Con rounding = 0.01 y saldo delta sub-rounding, uom.compare valida que no se produzcan cantidades negativas
        # y se mantenga estricta paridad con Odoo sin usar direct SQL.
        uom_cents = self.env["uom.uom"].create({
            "name": "Unit Cents Precision Aggregate",
            "rounding": 0.01,
        })
        product_subround = self.Product.create({
            "name": "Product Subround Aggregate",
            "type": "consu",
            "is_storable": True,
            "uom_id": uom_cents.id,
            "company_id": self.main_company.id,
        })
        self.Quant._update_available_quantity(
            product_subround,
            self.loc_child,
            -0.001,
        )

        subround_avail = self.Block.get_aggregate_unblocked_available_quantity(
            self.main_company,
            product_subround,
            self.loc_root,
        )
        self.assertEqual(subround_avail, 0.0)
        self.assertTrue(product_subround.uom_id.compare(subround_avail, 0.0) >= 0)

    # ------------------------------------------------------------------
    # TEST-INV-054: Scoping de compañía y control de acceso RBAC
    # ------------------------------------------------------------------

    def test_inv_54_company_scoping_and_rbac_access_control(self):
        """INV-054: Raíz compartida respeta allowed_company_ids, quants compartidos y RBAC previene accesos no autorizados."""
        # Crear compañía secundaria y ubicaciones en raíz compartida
        secondary_company = self.Company.create({"name": "Secondary Aggregate Company"})
        loc_shared_root = self.Location.create({
            "name": "WH-SHARED-ROOT-AGG",
            "usage": "internal",
            "company_id": False,  # Ubicación raíz compartida
        })
        loc_shared_child = self.Location.create({
            "name": "LOC-SHARED-CHILD-AGG",
            "usage": "internal",
            "location_id": loc_shared_root.id,
            "company_id": False,  # Ubicación hija compartida
        })
        loc_main = self.Location.create({
            "name": "LOC-MAIN-AGG",
            "usage": "internal",
            "location_id": loc_shared_root.id,
            "company_id": self.main_company.id,
        })
        loc_sec = self.Location.create({
            "name": "LOC-SEC-AGG",
            "usage": "internal",
            "location_id": loc_shared_root.id,
            "company_id": secondary_company.id,
        })

        # Inventario en ambas compañías y en ubicación compartida
        self.Quant._update_available_quantity(self.product_a, loc_main, 10.0)
        self.Quant._update_available_quantity(self.product_a, loc_sec, 20.0)
        self.Quant._update_available_quantity(self.product_a, loc_shared_child, 3.0)

        # Usuario con acceso a ambas compañías
        user_multi = self.Users.create({
            "name": "WMS Multi Aggregate Operator",
            "login": "wms_multi_agg_operator",
            "email": "multi_agg@test.com",
            "company_id": self.main_company.id,
            "company_ids": [(6, 0, [self.main_company.id, secondary_company.id])],
            "group_ids": [(6, 0, [self.group_internal.id, self.group_operator.id])],
        })

        # 1. Consulta con company_id = main_company -> ve 10.0 (loc_main) + 3.0 (compartido) = 13.0 (no ve 20.0 de loc_sec)
        avail_main = self.Block.with_user(user_multi).get_aggregate_unblocked_available_quantity(
            self.main_company,
            self.product_a,
            loc_shared_root,
        )
        self.assertEqual(avail_main, 13.0)

        # 2. Consulta con company_id = secondary_company -> ve 20.0 (loc_sec) + 3.0 (compartido) = 23.0 (no ve 10.0 de loc_main)
        avail_sec = self.Block.with_user(user_multi).get_aggregate_unblocked_available_quantity(
            secondary_company,
            self.product_a,
            loc_shared_root,
        )
        self.assertEqual(avail_sec, 23.0)

        # 3. RBAC: Operator funciona; Plain Internal -> AccessError
        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_plain).get_aggregate_unblocked_available_quantity(
                self.main_company,
                self.product_a,
                self.loc_root,
            )

        # 4. Compañía no autorizada -> AccessError
        unauthorized_company = self.Company.create({"name": "Unauthorized Company Agg"})
        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_operator).get_aggregate_unblocked_available_quantity(
                unauthorized_company,
                self.product_a,
                self.loc_root,
            )

        # 5. Incompatibilidad de ubicación raíz (loc_sec pertenece a secondary_company, consultada bajo main_company)
        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_operator).get_aggregate_unblocked_available_quantity(
                self.main_company,
                self.product_a,
                loc_sec,
            )

    # ------------------------------------------------------------------
    # TEST-INV-055: Performance y frontera de ejecución
    # ------------------------------------------------------------------

    def test_inv_55_performance_and_execution_boundary(self):
        """INV-055: Ejecuta exactamente 1 _gather y 1 get_blocked_quants; 0 is_blocked y 0 _get_available_quantity."""
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0)
        self.Quant._update_available_quantity(self.product_a, self.loc_sibling, 5.0)

        # Parchear helpers para demostrar ausencia de llamadas N+1 o desvíos
        with patch.object(type(self.Block), "is_blocked", side_effect=AssertionError("No se debe invocar is_blocked en agregación")), \
             patch.object(type(self.Block), "get_unblocked_available_quantity", side_effect=AssertionError("No se debe invocar el guardia exacto en agregación")), \
             patch.object(type(self.Quant), "_get_available_quantity", side_effect=AssertionError("No se debe invocar _get_available_quantity en agregación")), \
             patch.object(type(self.Quant), "_gather", wraps=self.Quant._gather) as spy_gather, \
             patch.object(type(self.Block), "get_blocked_quants", wraps=self.Block.get_blocked_quants) as spy_batch:

            avail = self.Block.with_user(self.user_operator).get_aggregate_unblocked_available_quantity(
                self.main_company,
                self.product_a,
                self.loc_root,
            )
            self.assertEqual(avail, 15.0)
            self.assertEqual(spy_gather.call_count, 1, "Debe invocarse _gather exactamente 1 vez")
            self.assertEqual(spy_batch.call_count, 1, "Debe invocarse get_blocked_quants exactamente 1 vez")
