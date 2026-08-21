from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.tests.common import TransactionCase


class TestInventoryBlockMatching(TransactionCase):
    """Pruebas unitarias para la API de consulta de coincidencia de bloqueos operacionales (INV-003).

    Valida:
    - INV-017: Firma y tipos de retorno exactos (_get_matching_domain, get_matching_blocks, is_blocked).
    - INV-018: Scope LOCATION con semántica jerárquica (self + descendants).
    - INV-019: Scope PRODUCT_LOCATION con jerarquía de ubicación y producto exacto.
    - INV-020: Scope LOT independiente de ubicación para el mismo producto y lote.
    - INV-021: Scope PACKAGE con semántica jerárquica de contenedores.
    - INV-022: Scope OWNER_LOCATION con propietario exacto y jerarquía de ubicación.
    - INV-023: Bloque liberado deja de hacer match inmediatamente.
    - INV-024: Múltiples bloques solapados retornan todos sin priorización arbitraria.
    - INV-025: Múltiples bloques con la misma dimensión coexisten y se liberan independientemente.
    - INV-026: Candidatos sin dimensiones opcionales no generan matches espurios.
    - INV-027: Multi-company y RBAC: compañía no autorizada lanza AccessError; funciona para Operator sin sudo.
    - INV-028: Boundary: el matcher no altera la disponibilidad nativa de Odoo (_get_available_quantity).
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
        cls.Users = cls.env["res.users"]

        cls.main_company = cls.env.company

        # Jerarquía de ubicaciones
        # WH/Stock (loc_parent) -> Aisle-01 (loc_child) -> Bin-01 (loc_grandchild)
        # WH/Stock (loc_parent) -> Aisle-02 (loc_sibling)
        cls.loc_root = cls.Location.create({
            "name": "WH-ROOT",
            "usage": "view",
            "company_id": cls.main_company.id,
        })
        cls.loc_parent = cls.Location.create({
            "name": "WH-STOCK",
            "usage": "internal",
            "location_id": cls.loc_root.id,
            "company_id": cls.main_company.id,
        })
        cls.loc_child = cls.Location.create({
            "name": "AISLE-01",
            "usage": "internal",
            "location_id": cls.loc_parent.id,
            "company_id": cls.main_company.id,
        })
        cls.loc_grandchild = cls.Location.create({
            "name": "BIN-01",
            "usage": "internal",
            "location_id": cls.loc_child.id,
            "company_id": cls.main_company.id,
        })
        cls.loc_sibling = cls.Location.create({
            "name": "AISLE-02",
            "usage": "internal",
            "location_id": cls.loc_parent.id,
            "company_id": cls.main_company.id,
        })

        # Productos
        cls.product_a = cls.Product.create({
            "name": "Product Alpha Matcher",
            "type": "consu",
            "is_storable": True,
            "company_id": cls.main_company.id,
        })
        cls.product_b = cls.Product.create({
            "name": "Product Beta Matcher",
            "type": "consu",
            "is_storable": True,
            "company_id": cls.main_company.id,
        })

        # Lotes
        cls.lot_a = cls.Lot.create({
            "name": "LOT-MATCH-A",
            "product_id": cls.product_a.id,
            "company_id": cls.main_company.id,
        })
        cls.lot_b = cls.Lot.create({
            "name": "LOT-MATCH-B",
            "product_id": cls.product_a.id,
            "company_id": cls.main_company.id,
        })

        # Jerarquía de paquetes: PALLET-01 -> CASE-01 -> PACK-01, PALLET-02
        cls.pallet_01 = cls.Package.create({"name": "PALLET-MATCH-01"})
        cls.case_01 = cls.Package.create({
            "name": "CASE-MATCH-01",
            "parent_package_id": cls.pallet_01.id,
        })
        cls.pack_01 = cls.Package.create({
            "name": "PACK-MATCH-01",
            "parent_package_id": cls.case_01.id,
        })
        cls.pallet_02 = cls.Package.create({"name": "PALLET-MATCH-02"})

        # Propietarios
        cls.owner_partner = cls.Partner.create({"name": "Owner Partner Alpha"})
        cls.other_partner = cls.Partner.create({"name": "Owner Partner Beta"})

        # Grupos y usuarios
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_supervisor = cls.env.ref("wms_core.group_wms_supervisor")

        cls.user_operator = cls.Users.create({
            "name": "WMS Matcher Operator",
            "login": "wms_matcher_operator",
            "email": "matcher_operator@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_operator.id])],
        })
        cls.user_supervisor = cls.Users.create({
            "name": "WMS Matcher Supervisor",
            "login": "wms_matcher_supervisor",
            "email": "matcher_supervisor@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_supervisor.id])],
        })
        cls.user_plain = cls.Users.create({
            "name": "WMS Matcher Plain Internal",
            "login": "wms_matcher_plain",
            "email": "matcher_plain@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id])],
        })

    # ------------------------------------------------------------------
    # TEST-INV-017: Firmas de API, tipos de retorno y validaciones
    # ------------------------------------------------------------------

    def test_inv_17_matching_api_signatures_and_types(self):
        """INV-017: _get_matching_domain retorna Domain, get_matching_blocks retorna recordset, is_blocked retorna bool."""
        domain = self.Block._get_matching_domain(
            self.main_company,
            self.product_a,
            self.loc_child,
        )
        self.assertIsInstance(domain, Domain, "Debe retornar una instancia de odoo.fields.Domain")

        blocks = self.Block.get_matching_blocks(
            self.main_company,
            self.product_a,
            self.loc_child,
        )
        self.assertEqual(blocks._name, "wms.inventory.block")

        blocked = self.Block.is_blocked(
            self.main_company,
            self.product_a,
            self.loc_child,
        )
        self.assertIsInstance(blocked, bool)
        self.assertFalse(blocked)

        # Validación de parámetros requeridos
        with self.assertRaises(ValueError):
            self.Block._get_matching_domain(False, self.product_a, self.loc_child)
        with self.assertRaises(ValueError):
            self.Block._get_matching_domain(self.main_company, False, self.loc_child)
        with self.assertRaises(ValueError):
            self.Block._get_matching_domain(self.main_company, self.product_a, False)

    # ------------------------------------------------------------------
    # TEST-INV-018: Matching jerárquico de LOCATION
    # ------------------------------------------------------------------

    def test_inv_18_location_hierarchy_matching(self):
        """INV-018: Bloqueo LOCATION en padre afecta a descendientes; bloqueo en hijo no afecta a ancestro."""
        # 1. Bloqueo en WH/Stock (loc_parent)
        block_parent = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_parent.id,
            "block_type": "HOLD",
            "reason": "Bloqueo general de zona de stock",
        })

        # Mismo registro (loc_parent) -> Coincidencia
        self.assertTrue(self.Block.is_blocked(self.main_company, self.product_a, self.loc_parent))
        # Hijo (loc_child) -> Coincidencia
        self.assertTrue(self.Block.is_blocked(self.main_company, self.product_a, self.loc_child))
        # Nieto (loc_grandchild) -> Coincidencia
        self.assertTrue(self.Block.is_blocked(self.main_company, self.product_a, self.loc_grandchild))
        # Hermano (loc_sibling) -> Coincidencia (porque loc_sibling es hijo de loc_parent)
        self.assertTrue(self.Block.is_blocked(self.main_company, self.product_a, self.loc_sibling))
        # Raíz (loc_root, ancestro de loc_parent) -> Sin coincidencia
        self.assertFalse(self.Block.is_blocked(self.main_company, self.product_a, self.loc_root))

        block_parent.with_user(self.user_supervisor).action_release()

        # 2. Bloqueo en Aisle-01 (loc_child)
        self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_child.id,
            "block_type": "CYCLE_COUNT",
            "reason": "Conteo cíclico de pasillo 1",
        })

        # Nieto (loc_grandchild) -> Coincidencia
        self.assertTrue(self.Block.is_blocked(self.main_company, self.product_a, self.loc_grandchild))
        # Padre (loc_parent) -> Sin coincidencia (el ancestro no queda bloqueado)
        self.assertFalse(self.Block.is_blocked(self.main_company, self.product_a, self.loc_parent))
        # Hermano (loc_sibling) -> Sin coincidencia
        self.assertFalse(self.Block.is_blocked(self.main_company, self.product_a, self.loc_sibling))

    # ------------------------------------------------------------------
    # TEST-INV-019: Matching jerárquico de PRODUCT_LOCATION
    # ------------------------------------------------------------------

    def test_inv_19_product_location_hierarchy_matching(self):
        """INV-019: Bloqueo PRODUCT_LOCATION exige producto exacto y aplica al subtree de ubicación."""
        self.Block.create({
            "block_scope": "PRODUCT_LOCATION",
            "product_id": self.product_a.id,
            "location_id": self.loc_parent.id,
            "block_type": "INVESTIGATION",
            "reason": "Investigación de Product Alpha en bodega",
        })

        # Product Alpha en hijo (loc_child) -> Coincidencia
        self.assertTrue(self.Block.is_blocked(self.main_company, self.product_a, self.loc_child))
        # Product Alpha en nieto (loc_grandchild) -> Coincidencia
        self.assertTrue(self.Block.is_blocked(self.main_company, self.product_a, self.loc_grandchild))
        # Product Beta en hijo (loc_child) -> Sin coincidencia (producto diferente)
        self.assertFalse(self.Block.is_blocked(self.main_company, self.product_b, self.loc_child))
        # Product Alpha en raíz (loc_root) -> Sin coincidencia (fuera del subárbol)
        self.assertFalse(self.Block.is_blocked(self.main_company, self.product_a, self.loc_root))

    # ------------------------------------------------------------------
    # TEST-INV-020: Matching de LOT independiente de ubicación
    # ------------------------------------------------------------------

    def test_inv_20_lot_matching_location_independent(self):
        """INV-020: Bloqueo LOT aplica al mismo producto y lote independientemente de la ubicación."""
        self.Block.create({
            "block_scope": "LOT",
            "product_id": self.product_a.id,
            "lot_id": self.lot_a.id,
            "block_type": "HOLD",
            "reason": "Bloqueo de lote por control de calidad",
        })

        # Product Alpha + Lot A en loc_child -> Coincidencia
        self.assertTrue(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, lot_id=self.lot_a)
        )
        # Product Alpha + Lot A en loc_sibling -> Coincidencia (ubicación indiferente)
        self.assertTrue(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_sibling, lot_id=self.lot_a)
        )
        # Product Alpha + Lot B en loc_child -> Sin coincidencia (lote diferente)
        self.assertFalse(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, lot_id=self.lot_b)
        )
        # Product Alpha sin lote -> Sin coincidencia
        self.assertFalse(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, lot_id=False)
        )

    # ------------------------------------------------------------------
    # TEST-INV-021: Matching jerárquico de PACKAGE
    # ------------------------------------------------------------------

    def test_inv_21_package_hierarchy_matching(self):
        """INV-021: Bloqueo PACKAGE en contenedor padre aplica a paquetes contenidos (descendientes)."""
        # 1. Bloqueo en PALLET-01
        block_pallet = self.Block.create({
            "block_scope": "PACKAGE",
            "package_id": self.pallet_01.id,
            "block_type": "CUSTOMS",
            "reason": "Retención de pallet por aduana",
        })

        # Mismo paquete (pallet_01) -> Coincidencia
        self.assertTrue(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, package_id=self.pallet_01)
        )
        # Paquete hijo (case_01) -> Coincidencia
        self.assertTrue(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, package_id=self.case_01)
        )
        # Paquete nieto (pack_01) -> Coincidencia
        self.assertTrue(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, package_id=self.pack_01)
        )
        # Paquete hermano / no relacionado (pallet_02) -> Sin coincidencia
        self.assertFalse(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, package_id=self.pallet_02)
        )
        # Candidato sin paquete -> Sin coincidencia
        self.assertFalse(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, package_id=False)
        )

        block_pallet.with_user(self.user_supervisor).action_release()

        # 2. Bloqueo en CASE-01 (hijo)
        self.Block.create({
            "block_scope": "PACKAGE",
            "package_id": self.case_01.id,
            "block_type": "HOLD",
            "reason": "Retención de caja específica",
        })

        # Nieto (pack_01) -> Coincidencia
        self.assertTrue(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, package_id=self.pack_01)
        )
        # Padre (pallet_01) -> Sin coincidencia
        self.assertFalse(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, package_id=self.pallet_01)
        )

    # ------------------------------------------------------------------
    # TEST-INV-022: Matching jerárquico de OWNER_LOCATION
    # ------------------------------------------------------------------

    def test_inv_22_owner_location_hierarchy_matching(self):
        """INV-022: Bloqueo OWNER_LOCATION exige propietario exacto y aplica al subtree de ubicación."""
        self.Block.create({
            "block_scope": "OWNER_LOCATION",
            "owner_id": self.owner_partner.id,
            "location_id": self.loc_parent.id,
            "block_type": "HOLD",
            "reason": "Retención de mercancía de cliente",
        })

        # Mismo propietario en hijo (loc_child) -> Coincidencia
        self.assertTrue(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, owner_id=self.owner_partner)
        )
        # Mismo propietario en nieto (loc_grandchild) -> Coincidencia
        self.assertTrue(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_grandchild, owner_id=self.owner_partner)
        )
        # Propietario diferente en hijo -> Sin coincidencia
        self.assertFalse(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, owner_id=self.other_partner)
        )
        # Candidato sin propietario -> Sin coincidencia
        self.assertFalse(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, owner_id=False)
        )
        # Mismo propietario fuera del subárbol (loc_root) -> Sin coincidencia
        self.assertFalse(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_root, owner_id=self.owner_partner)
        )

    # ------------------------------------------------------------------
    # TEST-INV-023: Bloque liberado deja de coincidir inmediatamente
    # ------------------------------------------------------------------

    def test_inv_23_released_block_stops_matching_immediately(self):
        """INV-023: Un bloque liberado con action_release() deja de hacer match inmediatamente."""
        block = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_child.id,
            "block_type": "HOLD",
            "reason": "Bloqueo temporal",
        })

        self.assertTrue(self.Block.is_blocked(self.main_company, self.product_a, self.loc_child))
        self.assertEqual(len(self.Block.get_matching_blocks(self.main_company, self.product_a, self.loc_child)), 1)

        # Liberación por supervisor
        block.with_user(self.user_supervisor).action_release()
        self.assertTrue(block.released_at)

        # Inmediatamente no debe coincidir
        self.assertFalse(self.Block.is_blocked(self.main_company, self.product_a, self.loc_child))
        self.assertEqual(len(self.Block.get_matching_blocks(self.main_company, self.product_a, self.loc_child)), 0)

    # ------------------------------------------------------------------
    # TEST-INV-024: Múltiples bloques solapados retornan todos
    # ------------------------------------------------------------------

    def test_inv_24_multiple_overlapping_scopes_returned(self):
        """INV-024: Múltiples bloques aplicables de distintos scopes son todos retornados."""
        b1 = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_parent.id,
            "block_type": "HOLD",
            "reason": "Bloqueo por zona",
        })
        b2 = self.Block.create({
            "block_scope": "PRODUCT_LOCATION",
            "product_id": self.product_a.id,
            "location_id": self.loc_child.id,
            "block_type": "INVESTIGATION",
            "reason": "Bloqueo de SKU en pasillo",
        })
        b3 = self.Block.create({
            "block_scope": "LOT",
            "product_id": self.product_a.id,
            "lot_id": self.lot_a.id,
            "block_type": "CYCLE_COUNT",
            "reason": "Bloqueo por conteo de lote",
        })

        # Candidato con Product A, Loc Child y Lot A
        blocks = self.Block.get_matching_blocks(
            self.main_company,
            self.product_a,
            self.loc_child,
            lot_id=self.lot_a,
        )
        self.assertEqual(len(blocks), 3)
        self.assertEqual(set(blocks.ids), {b1.id, b2.id, b3.id})
        self.assertTrue(self.Block.is_blocked(self.main_company, self.product_a, self.loc_child, lot_id=self.lot_a))

    # ------------------------------------------------------------------
    # TEST-INV-025: Múltiples bloques en mismo scope y dimensión coexisten
    # ------------------------------------------------------------------

    def test_inv_25_multiple_blocks_same_scope_and_dimension_coexist(self):
        """INV-025: Dos bloques concurrentes sobre la misma dimensión coexisten y se liberan independientemente."""
        b1 = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_child.id,
            "block_type": "CYCLE_COUNT",
            "reason": "Conteo cíclico",
        })
        b2 = self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_child.id,
            "block_type": "INVESTIGATION",
            "reason": "Investigación",
        })

        matching = self.Block.get_matching_blocks(self.main_company, self.product_a, self.loc_child)
        self.assertEqual(len(matching), 2)
        self.assertEqual(set(matching.ids), {b1.id, b2.id})

        # Liberar b1 no libera b2
        b1.with_user(self.user_supervisor).action_release()
        matching_after = self.Block.get_matching_blocks(self.main_company, self.product_a, self.loc_child)
        self.assertEqual(len(matching_after), 1)
        self.assertEqual(matching_after.id, b2.id)
        self.assertTrue(self.Block.is_blocked(self.main_company, self.product_a, self.loc_child))

    # ------------------------------------------------------------------
    # TEST-INV-026: Candidato sin dimensiones opcionales no genera coincidencias espurias
    # ------------------------------------------------------------------

    def test_inv_26_candidate_without_optional_dimensions_no_spurious_matches(self):
        """INV-026: Si el candidato no especifica lote/paquete/propietario, esos scopes no hacen match espurio."""
        self.Block.create({
            "block_scope": "LOT",
            "product_id": self.product_a.id,
            "lot_id": self.lot_a.id,
            "block_type": "HOLD",
            "reason": "Bloqueo de lote",
        })
        self.Block.create({
            "block_scope": "PACKAGE",
            "package_id": self.pallet_01.id,
            "block_type": "HOLD",
            "reason": "Bloqueo de pallet",
        })
        self.Block.create({
            "block_scope": "OWNER_LOCATION",
            "owner_id": self.owner_partner.id,
            "location_id": self.loc_child.id,
            "block_type": "HOLD",
            "reason": "Bloqueo de propietario",
        })

        # Candidato plano sin lote, sin paquete, sin propietario en loc_child
        matching = self.Block.get_matching_blocks(
            self.main_company,
            self.product_a,
            self.loc_child,
            lot_id=False,
            package_id=False,
            owner_id=False,
        )
        self.assertFalse(matching)
        self.assertFalse(
            self.Block.is_blocked(
                self.main_company,
                self.product_a,
                self.loc_child,
                lot_id=False,
                package_id=False,
                owner_id=False,
            )
        )

    # ------------------------------------------------------------------
    # TEST-INV-027: Control de acceso multi-compañía y RBAC
    # ------------------------------------------------------------------

    def test_inv_27_multi_company_and_rbac_access_control(self):
        """INV-027: Operator consulta normalmente sin sudo; compañía no autorizada o usuario plain lanzan AccessError."""
        # Crear bloqueo en main_company
        self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_child.id,
            "company_id": self.main_company.id,
            "block_type": "HOLD",
            "reason": "Bloqueo en main company",
        })

        # A. Operator con compañía autorizada -> Funciona normalmente (sin sudo)
        is_blk = self.Block.with_user(self.user_operator).is_blocked(
            self.main_company,
            self.product_a,
            self.loc_child,
        )
        self.assertTrue(is_blk, "Operator debe poder consultar bloqueos de su compañía autorizada")

        matching_op = self.Block.with_user(self.user_operator).get_matching_blocks(
            self.main_company,
            self.product_a,
            self.loc_child,
        )
        self.assertEqual(len(matching_op), 1)

        # B. Compañía no autorizada en env.companies -> AccessError explícito (nunca False)
        foreign_company = self.Company.create({"name": "Unauthorized Foreign Company"})
        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_operator).is_blocked(
                foreign_company,
                self.product_a,
                self.loc_child,
            )

        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_operator).get_matching_blocks(
                foreign_company,
                self.product_a,
                self.loc_child,
            )

        # C. Plain internal user sin permisos ACL de Inventory Block -> AccessError
        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_plain).get_matching_blocks(
                self.main_company,
                self.product_a,
                self.loc_child,
            )

    # ------------------------------------------------------------------
    # TEST-INV-028: Frontera de disponibilidad nativa de stock
    # ------------------------------------------------------------------

    def test_inv_28_native_stock_availability_boundary(self):
        """INV-028: Boundary: el matcher ve el bloqueo activo mientras _get_available_quantity() de Odoo permanece inalterado."""
        # 1. Establecer inventario estándar con _update_available_quantity
        self.env["stock.quant"]._update_available_quantity(
            self.product_a,
            self.loc_child,
            10.0,
        )
        avail_before = self.env["stock.quant"]._get_available_quantity(
            self.product_a,
            self.loc_child,
        )
        self.assertEqual(avail_before, 10.0, "Disponibilidad nativa inicial debe ser 10.0")

        # 2. Crear bloqueo operacional WMS activo
        self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_child.id,
            "block_type": "HOLD",
            "reason": "Bloqueo operacional de pasillo",
        })

        # 3. El matcher confirma que el candidato está bloqueado
        self.assertTrue(
            self.Block.is_blocked(self.main_company, self.product_a, self.loc_child),
            "El matcher WMS debe reportar el candidato como bloqueado",
        )

        # 4. _get_available_quantity() nativo de Odoo permanece intacto en 10.0
        avail_after = self.env["stock.quant"]._get_available_quantity(
            self.product_a,
            self.loc_child,
        )
        self.assertEqual(
            avail_after,
            10.0,
            "El bloqueo WMS NO debe modificar _get_available_quantity() nativo de Odoo en INV-003",
        )
