from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestInventoryBlockBatchMatching(TransactionCase):
    """Pruebas unitarias para la API de matching batch de bloqueos operacionales (INV-005).

    Valida:
    - INV-037: Firma de API, input/output stock.quant y batch vacío retorna vacío sin búsquedas ORM.
    - INV-038: Scope LOCATION: self + descendientes bloqueados, sibling y ancestro inverso libres.
    - INV-039: Scope PRODUCT_LOCATION: pairing exacto producto/ubicación (anti-cross-product false positives).
    - INV-040: Scope LOT: pairing exacto producto+lote, independiente de ubicación.
    - INV-041: Scope PACKAGE: paquete exacto + descendiente bloqueados; sibling y sin paquete libres.
    - INV-042: Scope OWNER_LOCATION: propietario exacto + subárbol; sin propietario libre.
    - INV-043: Múltiples scopes solapados y bloques liberados ignorados.
    - INV-044: Paridad semántica estricta batch vs is_blocked() sobre matriz mixta de quants.
    - INV-045: Rendimiento y seguridad: 1 search de bloqueos, 0 search_count, 0 is_blocked;
               Operator funciona; Plain Internal (con batch vacío y no vacío), compañía no autorizada
               e incoherencia de compañía lanzan AccessError.
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
        # WH-ROOT-BATCH -> WH-STOCK-BATCH (loc_parent) -> AISLE-01-BATCH (loc_child) -> BIN-01-BATCH (loc_grandchild)
        # WH-ROOT-BATCH -> WH-STOCK-BATCH (loc_parent) -> AISLE-02-BATCH (loc_sibling)
        cls.loc_root = cls.Location.create({
            "name": "WH-ROOT-BATCH",
            "usage": "internal",
            "company_id": cls.main_company.id,
        })
        cls.loc_parent = cls.Location.create({
            "name": "WH-STOCK-BATCH",
            "usage": "internal",
            "location_id": cls.loc_root.id,
            "company_id": cls.main_company.id,
        })
        cls.loc_child = cls.Location.create({
            "name": "AISLE-01-BATCH",
            "usage": "internal",
            "location_id": cls.loc_parent.id,
            "company_id": cls.main_company.id,
        })
        cls.loc_grandchild = cls.Location.create({
            "name": "BIN-01-BATCH",
            "usage": "internal",
            "location_id": cls.loc_child.id,
            "company_id": cls.main_company.id,
        })
        cls.loc_sibling = cls.Location.create({
            "name": "AISLE-02-BATCH",
            "usage": "internal",
            "location_id": cls.loc_parent.id,
            "company_id": cls.main_company.id,
        })

        # Productos
        cls.product_a = cls.Product.create({
            "name": "Product Alpha Batch",
            "type": "consu",
            "is_storable": True,
            "company_id": cls.main_company.id,
        })
        cls.product_b = cls.Product.create({
            "name": "Product Beta Batch",
            "type": "consu",
            "is_storable": True,
            "company_id": cls.main_company.id,
        })
        cls.product_tracked = cls.Product.create({
            "name": "Product Tracked Batch",
            "type": "consu",
            "is_storable": True,
            "tracking": "lot",
            "company_id": cls.main_company.id,
        })

        # Lotes
        cls.lot_a = cls.Lot.create({
            "name": "LOT-BATCH-A",
            "product_id": cls.product_tracked.id,
            "company_id": cls.main_company.id,
        })
        cls.lot_b = cls.Lot.create({
            "name": "LOT-BATCH-B",
            "product_id": cls.product_tracked.id,
            "company_id": cls.main_company.id,
        })

        # Jerarquía de paquetes: PALLET-01 -> CASE-01, PALLET-02
        cls.pallet_01 = cls.Package.create({"name": "PALLET-BATCH-01"})
        cls.case_01 = cls.Package.create({
            "name": "CASE-BATCH-01",
            "parent_package_id": cls.pallet_01.id,
        })
        cls.pallet_02 = cls.Package.create({"name": "PALLET-BATCH-02"})

        # Propietarios
        cls.owner_partner = cls.Partner.create({"name": "Owner Partner Batch Alpha"})
        cls.other_partner = cls.Partner.create({"name": "Owner Partner Batch Beta"})

        # Grupos y usuarios
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_supervisor = cls.env.ref("wms_core.group_wms_supervisor")

        cls.user_operator = cls.Users.create({
            "name": "WMS Batch Operator",
            "login": "wms_batch_operator",
            "email": "batch_operator@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_operator.id])],
        })
        cls.user_supervisor = cls.Users.create({
            "name": "WMS Batch Supervisor",
            "login": "wms_batch_supervisor",
            "email": "batch_supervisor@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_supervisor.id])],
        })
        cls.user_plain = cls.Users.create({
            "name": "WMS Batch Plain Internal",
            "login": "wms_batch_plain",
            "email": "batch_plain@test.com",
            "company_id": cls.main_company.id,
            "company_ids": [(6, 0, [cls.main_company.id])],
            "group_ids": [(6, 0, [cls.group_internal.id])],
        })

    # ------------------------------------------------------------------
    # TEST-INV-037: Firma de API, input/output stock.quant y batch vacío
    # ------------------------------------------------------------------

    def test_inv_37_batch_matching_api_signatures_and_empty_batch(self):
        """INV-037: get_blocked_quants retorna recordset stock.quant y el batch vacío no ejecuta búsquedas ORM."""
        empty_quants = self.Quant.browse([])

        # Batch vacío con usuario autorizado
        with patch.object(type(self.Block), "search", side_effect=AssertionError("No se debe ejecutar search con batch vacío")):
            blocked = self.Block.with_user(self.user_operator).get_blocked_quants(
                self.main_company,
                empty_quants,
            )
            self.assertEqual(blocked._name, "stock.quant")
            self.assertFalse(blocked)

        # Validación de parámetros
        with self.assertRaises(ValueError):
            self.Block.get_blocked_quants(False, empty_quants)
        with self.assertRaises(ValueError):
            self.Block.get_blocked_quants(self.main_company, None)
        with self.assertRaises(ValueError):
            self.Block.get_blocked_quants(self.main_company, self.product_a)

    # ------------------------------------------------------------------
    # TEST-INV-038: Scope LOCATION jerárquico en batch
    # ------------------------------------------------------------------

    def test_inv_38_location_hierarchy_batch_matching(self):
        """INV-038: Bloqueo LOCATION en padre bloquea self y descendientes en batch; sibling y ancestro libres."""
        self.Quant._update_available_quantity(self.product_a, self.loc_root, 10.0)
        self.Quant._update_available_quantity(self.product_a, self.loc_parent, 10.0)
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0)
        self.Quant._update_available_quantity(self.product_a, self.loc_grandchild, 10.0)
        self.Quant._update_available_quantity(self.product_a, self.loc_sibling, 10.0)

        q_root = self.Quant.search([("product_id", "=", self.product_a.id), ("location_id", "=", self.loc_root.id)])
        q_parent = self.Quant.search([("product_id", "=", self.product_a.id), ("location_id", "=", self.loc_parent.id)])
        q_child = self.Quant.search([("product_id", "=", self.product_a.id), ("location_id", "=", self.loc_child.id)])
        q_grandchild = self.Quant.search([("product_id", "=", self.product_a.id), ("location_id", "=", self.loc_grandchild.id)])
        q_sibling = self.Quant.search([("product_id", "=", self.product_a.id), ("location_id", "=", self.loc_sibling.id)])

        all_quants = q_root | q_parent | q_child | q_grandchild | q_sibling

        # Bloqueo en loc_parent (WH-STOCK-BATCH)
        self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_parent.id,
            "block_type": "HOLD",
            "reason": "Bloqueo de zona",
        })

        blocked = self.Block.get_blocked_quants(self.main_company, all_quants)
        self.assertEqual(blocked, q_parent | q_child | q_grandchild | q_sibling)
        self.assertNotIn(q_root, blocked)

    # ------------------------------------------------------------------
    # TEST-INV-039: Scope PRODUCT_LOCATION: protección anti-cross-product
    # ------------------------------------------------------------------

    def test_inv_39_product_location_cross_product_protection(self):
        """INV-039: PRODUCT_LOCATION exige pairing exacto producto/ubicación y previene falsos positivos cruzados."""
        # Q1: Product A en AISLE-01 (loc_child)
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0)
        q1 = self.Quant.search([("product_id", "=", self.product_a.id), ("location_id", "=", self.loc_child.id)])

        # Q2: Product B en AISLE-02 (loc_sibling)
        self.Quant._update_available_quantity(self.product_b, self.loc_sibling, 5.0)
        q2 = self.Quant.search([("product_id", "=", self.product_b.id), ("location_id", "=", self.loc_sibling.id)])

        # Bloqueo: Product A en AISLE-02 (loc_sibling)
        # En la Fase 1 SQL, el domain amplio recupera este bloque porque product_id in [A, B] y location_id in [child, sibling].
        # En la Fase 2 Python, Q1 no coincide (ubicación child != sibling) y Q2 no coincide (producto B != A).
        self.Block.create({
            "block_scope": "PRODUCT_LOCATION",
            "product_id": self.product_a.id,
            "location_id": self.loc_sibling.id,
            "block_type": "INVESTIGATION",
            "reason": "Investigación SKU A en pasillo 2",
        })

        blocked = self.Block.get_blocked_quants(self.main_company, q1 | q2)
        self.assertFalse(blocked, "Ni Q1 ni Q2 deben ser bloqueados (protección de producto cruzado)")

        # Agregar Q3 que sí coincide exactamente: Product A en AISLE-02 (loc_sibling)
        self.Quant._update_available_quantity(self.product_a, self.loc_sibling, 7.0)
        q3 = self.Quant.search([("product_id", "=", self.product_a.id), ("location_id", "=", self.loc_sibling.id)])

        blocked_with_q3 = self.Block.get_blocked_quants(self.main_company, q1 | q2 | q3)
        self.assertEqual(blocked_with_q3, q3, "Solo Q3 debe ser bloqueado")

    # ------------------------------------------------------------------
    # TEST-INV-040: Scope LOT pairing exacto e independiente de ubicación
    # ------------------------------------------------------------------

    def test_inv_40_lot_matching_location_independent(self):
        """INV-040: Scope LOT bloquea quants del lote exacto en cualquier ubicación; quants sin lote o de otro lote libres."""
        self.Quant._update_available_quantity(self.product_tracked, self.loc_child, 10.0, lot_id=self.lot_a)
        self.Quant._update_available_quantity(self.product_tracked, self.loc_sibling, 5.0, lot_id=self.lot_a)
        self.Quant._update_available_quantity(self.product_tracked, self.loc_child, 8.0, lot_id=self.lot_b)

        q_lot_a_child = self.Quant.search([("product_id", "=", self.product_tracked.id), ("location_id", "=", self.loc_child.id), ("lot_id", "=", self.lot_a.id)])
        q_lot_a_sib = self.Quant.search([("product_id", "=", self.product_tracked.id), ("location_id", "=", self.loc_sibling.id), ("lot_id", "=", self.lot_a.id)])
        q_lot_b_child = self.Quant.search([("product_id", "=", self.product_tracked.id), ("location_id", "=", self.loc_child.id), ("lot_id", "=", self.lot_b.id)])

        all_quants = q_lot_a_child | q_lot_a_sib | q_lot_b_child

        self.Block.create({
            "block_scope": "LOT",
            "product_id": self.product_tracked.id,
            "lot_id": self.lot_a.id,
            "block_type": "HOLD",
            "reason": "Retención de lote A",
        })

        blocked = self.Block.get_blocked_quants(self.main_company, all_quants)
        self.assertEqual(blocked, q_lot_a_child | q_lot_a_sib)
        self.assertNotIn(q_lot_b_child, blocked)

    # ------------------------------------------------------------------
    # TEST-INV-041: Scope PACKAGE jerárquico en batch
    # ------------------------------------------------------------------

    def test_inv_41_package_hierarchy_batch_matching(self):
        """INV-041: Scope PACKAGE bloquea paquetes exactos y contenidos; paquetes hermanos y quants sin paquete libres."""
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0, package_id=self.pallet_01)
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0, package_id=self.case_01)
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 5.0, package_id=self.pallet_02)
        self.Quant._update_available_quantity(self.product_b, self.loc_child, 8.0)

        q_pallet_01 = self.Quant.search([("package_id", "=", self.pallet_01.id)])
        q_case_01 = self.Quant.search([("package_id", "=", self.case_01.id)])
        q_pallet_02 = self.Quant.search([("package_id", "=", self.pallet_02.id)])
        q_no_pkg = self.Quant.search([("product_id", "=", self.product_b.id), ("package_id", "=", False)])

        all_quants = q_pallet_01 | q_case_01 | q_pallet_02 | q_no_pkg

        # Bloqueo en PALLET-01 (case_01 es hijo de pallet_01)
        self.Block.create({
            "block_scope": "PACKAGE",
            "package_id": self.pallet_01.id,
            "block_type": "CUSTOMS",
            "reason": "Retención de pallet",
        })

        blocked = self.Block.get_blocked_quants(self.main_company, all_quants)
        self.assertEqual(blocked, q_pallet_01 | q_case_01)
        self.assertNotIn(q_pallet_02, blocked)
        self.assertNotIn(q_no_pkg, blocked)

    # ------------------------------------------------------------------
    # TEST-INV-042: Scope OWNER_LOCATION jerárquico en batch
    # ------------------------------------------------------------------

    def test_inv_42_owner_location_hierarchy_batch_matching(self):
        """INV-042: Scope OWNER_LOCATION bloquea quants del propietario en el subárbol de ubicación."""
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0, owner_id=self.owner_partner)
        self.Quant._update_available_quantity(self.product_a, self.loc_root, 10.0, owner_id=self.owner_partner)
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 5.0, owner_id=self.other_partner)
        self.Quant._update_available_quantity(self.product_b, self.loc_child, 8.0)

        q_owner_child = self.Quant.search([("owner_id", "=", self.owner_partner.id), ("location_id", "=", self.loc_child.id)])
        q_owner_root = self.Quant.search([("owner_id", "=", self.owner_partner.id), ("location_id", "=", self.loc_root.id)])
        q_other_child = self.Quant.search([("owner_id", "=", self.other_partner.id), ("location_id", "=", self.loc_child.id)])
        q_no_owner = self.Quant.search([("product_id", "=", self.product_b.id), ("owner_id", "=", False)])

        all_quants = q_owner_child | q_owner_root | q_other_child | q_no_owner

        self.Block.create({
            "block_scope": "OWNER_LOCATION",
            "owner_id": self.owner_partner.id,
            "location_id": self.loc_parent.id,
            "block_type": "HOLD",
            "reason": "Retención de propietario",
        })

        blocked = self.Block.get_blocked_quants(self.main_company, all_quants)
        self.assertEqual(blocked, q_owner_child)
        self.assertNotIn(q_owner_root, blocked)
        self.assertNotIn(q_other_child, blocked)
        self.assertNotIn(q_no_owner, blocked)

    # ------------------------------------------------------------------
    # TEST-INV-043: Múltiples scopes solapados y bloques liberados ignorados
    # ------------------------------------------------------------------

    def test_inv_43_multiple_overlapping_scopes_and_released_blocks_ignored(self):
        """INV-043: Bloques liberados se ignoran; múltiples bloques activos de diferentes scopes se combinan correctamente."""
        # Q1: product_a en loc_child -> afectado por Bloque 1 (LOCATION en loc_child)
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0)
        # Q2: product_tracked en loc_root con lot_a -> afectado por Bloque 2 (LOT en lot_a)
        self.Quant._update_available_quantity(self.product_tracked, self.loc_root, 10.0, lot_id=self.lot_a)
        # Q3: product_b en loc_sibling -> protegido por liberación de Bloque 3 (PRODUCT_LOCATION en product_b + loc_sibling)
        self.Quant._update_available_quantity(self.product_b, self.loc_sibling, 5.0)

        q1 = self.Quant.search([("product_id", "=", self.product_a.id), ("location_id", "=", self.loc_child.id)])
        q2 = self.Quant.search([("product_id", "=", self.product_tracked.id), ("lot_id", "=", self.lot_a.id)])
        q3 = self.Quant.search([("product_id", "=", self.product_b.id), ("location_id", "=", self.loc_sibling.id)])

        # Bloque 1 activo: LOCATION en loc_child
        self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_child.id,
            "block_type": "HOLD",
            "reason": "Bloqueo activo de pasillo 1",
        })
        # Bloque 2 activo: LOT en lot_a
        self.Block.create({
            "block_scope": "LOT",
            "product_id": self.product_tracked.id,
            "lot_id": self.lot_a.id,
            "block_type": "INVESTIGATION",
            "reason": "Bloqueo activo de lote",
        })
        # Bloque 3 liberado: PRODUCT_LOCATION en product_b + loc_sibling
        b3 = self.Block.create({
            "block_scope": "PRODUCT_LOCATION",
            "product_id": self.product_b.id,
            "location_id": self.loc_sibling.id,
            "block_type": "CYCLE_COUNT",
            "reason": "Bloqueo liberado",
        })
        b3.with_user(self.user_supervisor).action_release()

        blocked = self.Block.get_blocked_quants(self.main_company, q1 | q2 | q3)
        self.assertEqual(blocked, q1 | q2)
        self.assertNotIn(q3, blocked)

    # ------------------------------------------------------------------
    # TEST-INV-044: Paridad semántica estricta batch vs is_blocked()
    # ------------------------------------------------------------------

    def test_inv_44_semantic_parity_batch_vs_is_blocked(self):
        """INV-044: Paridad estricta entre el resultado batch get_blocked_quants y evaluaciones individuales is_blocked."""
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0)
        self.Quant._update_available_quantity(self.product_b, self.loc_sibling, 5.0)
        self.Quant._update_available_quantity(self.product_tracked, self.loc_grandchild, 8.0, lot_id=self.lot_a)
        self.Quant._update_available_quantity(self.product_tracked, self.loc_child, 6.0, lot_id=self.lot_b)
        self.Quant._update_available_quantity(self.product_a, self.loc_parent, 12.0, package_id=self.case_01)
        self.Quant._update_available_quantity(self.product_b, self.loc_root, 15.0, owner_id=self.owner_partner)

        all_quants = self.Quant.search([("company_id", "=", self.main_company.id)])

        # Crear bloqueos activos variados
        self.Block.create({
            "block_scope": "LOCATION",
            "location_id": self.loc_child.id,
            "block_type": "CYCLE_COUNT",
            "reason": "Conteo en pasillo 1",
        })
        self.Block.create({
            "block_scope": "LOT",
            "product_id": self.product_tracked.id,
            "lot_id": self.lot_a.id,
            "block_type": "HOLD",
            "reason": "Retención de lote A",
        })
        self.Block.create({
            "block_scope": "PACKAGE",
            "package_id": self.pallet_01.id,
            "block_type": "CUSTOMS",
            "reason": "Aduana en pallet",
        })

        # Evaluación individual como oráculo canónico
        expected_blocked = self.Quant.browse([
            q.id for q in all_quants
            if self.Block.is_blocked(
                self.main_company,
                q.product_id,
                q.location_id,
                lot_id=q.lot_id or False,
                package_id=q.package_id or False,
                owner_id=q.owner_id or False,
            )
        ])

        # Evaluación batch
        actual_blocked = self.Block.get_blocked_quants(self.main_company, all_quants)

        self.assertEqual(
            set(actual_blocked.ids),
            set(expected_blocked.ids),
            "El resultado de get_blocked_quants debe ser idéntico al oráculo individual is_blocked",
        )

    # ------------------------------------------------------------------
    # TEST-INV-045: Rendimiento (1 query) y control de acceso RBAC / multi-compañía
    # ------------------------------------------------------------------

    def test_inv_45_performance_and_security_access_control(self):
        """INV-045: Batch no vacío ejecuta exactamente 1 búsqueda ORM y 0 N+1; RBAC y multi-compañía verificados."""
        self.Quant._update_available_quantity(self.product_a, self.loc_child, 10.0)
        self.Quant._update_available_quantity(self.product_b, self.loc_sibling, 5.0)
        quants = self.Quant.search([("company_id", "=", self.main_company.id)])

        # A. Performance: exactamente 1 search de bloqueos y 0 llamadas a helpers individuales
        with patch.object(type(self.Block), "is_blocked", side_effect=AssertionError("No se debe invocar is_blocked en batch")), \
             patch.object(type(self.Block), "search_count", side_effect=AssertionError("No se debe invocar search_count en batch")), \
             patch.object(type(self.Block), "get_matching_blocks", side_effect=AssertionError("No se debe invocar get_matching_blocks en batch")), \
             patch.object(type(self.Block), "search", wraps=self.Block.search) as spy_search:

            blocked = self.Block.with_user(self.user_operator).get_blocked_quants(self.main_company, quants)
            self.assertEqual(spy_search.call_count, 1, "Debe ejecutarse exactamente 1 consulta search sobre wms.inventory.block")

        # B. Operator con compañía autorizada -> Funciona
        blocked_op = self.Block.with_user(self.user_operator).get_blocked_quants(self.main_company, quants)
        self.assertEqual(blocked_op._name, "stock.quant")

        # C. Compañía no autorizada en env.companies -> AccessError
        foreign_company = self.Company.create({"name": "Unauthorized Foreign Company Batch"})
        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_operator).get_blocked_quants(
                foreign_company,
                quants,
            )

        # D. Incoherencia compañía-ubicación: quant en ubicación de main_company consultado bajo secondary_company
        secondary_company = self.Company.create({"name": "Secondary Batch Company"})
        user_multi = self.Users.create({
            "name": "WMS Multi Operator Batch",
            "login": "wms_multi_operator_batch",
            "email": "multi_batch@test.com",
            "company_id": self.main_company.id,
            "company_ids": [(6, 0, [self.main_company.id, secondary_company.id])],
            "group_ids": [(6, 0, [self.group_internal.id, self.group_operator.id])],
        })
        with self.assertRaises(AccessError):
            self.Block.with_user(user_multi).get_blocked_quants(
                secondary_company,
                quants,  # quants pertenecen a loc_child.company_id == main_company != secondary_company
            )

        # E. Plain Internal sin permisos ACL -> AccessError tanto con batch no vacío como con batch vacío
        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_plain).get_blocked_quants(self.main_company, quants)

        empty_quants = self.Quant.browse([])
        with self.assertRaises(AccessError):
            self.Block.with_user(self.user_plain).get_blocked_quants(self.main_company, empty_quants)
