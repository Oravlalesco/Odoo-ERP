import math
import threading
import time
from unittest.mock import patch

from odoo import api
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools.misc import mute_logger


class TestPhysicalUnpack(TransactionCase):
    """Suite de pruebas unitarias para HU-004B — Physical Unpack Core (TEST-HU-044 a TEST-HU-054).

    Verifica el primitive transaccional _wms_unpack_physical() en stock.package,
    garantizando la mutación física de stock.quant vía stock.move (package_dest_id=False),
    las transiciones de ciclo de vida OPEN -> OPEN y OPEN -> EMPTY, la persistencia atómica
    de wms.inventory.event (UNPACK) y wms.outbox (inventory.hu.unpacked) bajo un mismo
    correlation_id (ADR-019), guards operacionales, bloqueos de inventario, PLM admission-only,
    fronteras de seguridad RBAC y concurrencia determinista post-lock.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_1 = cls.env.company
        cls.company_2 = cls.env["res.company"].create({"name": "Secondary Company HU Unpack"})

        # Ubicaciones
        cls.location_internal_1 = cls.env["stock.location"].create({
            "name": "Unpack Loc Internal 1",
            "usage": "internal",
            "company_id": cls.company_1.id,
        })
        cls.location_internal_2 = cls.env["stock.location"].create({
            "name": "Unpack Loc Internal 2",
            "usage": "internal",
            "company_id": cls.company_2.id,
        })
        cls.location_customer = cls.env["stock.location"].create({
            "name": "Unpack Loc Customer",
            "usage": "customer",
            "company_id": cls.company_1.id,
        })

        # Productos
        cls.product_standard = cls.env["product.product"].create({
            "name": "Product Standard HU Unpack",
            "is_storable": True,
            "tracking": "none",
            "company_id": False,
        })
        cls.product_tracked_lot = cls.env["product.product"].create({
            "name": "Product Tracked Lot HU Unpack",
            "is_storable": True,
            "tracking": "lot",
            "company_id": False,
        })
        cls.product_tracked_serial = cls.env["product.product"].create({
            "name": "Product Tracked Serial HU Unpack",
            "is_storable": True,
            "tracking": "serial",
            "company_id": False,
        })

        # Lotes
        cls.lot_1 = cls.env["stock.lot"].create({
            "name": "LOT-UNPACK-001",
            "product_id": cls.product_tracked_lot.id,
            "company_id": cls.company_1.id,
        })
        cls.lot_serial_1 = cls.env["stock.lot"].create({
            "name": "SN-UNPACK-001",
            "product_id": cls.product_tracked_serial.id,
            "company_id": cls.company_1.id,
        })

        # Tipos de paquete
        cls.pkg_type_box = cls.env["stock.package.type"].create({
            "name": "Box Standard HU Unpack",
            "base_weight": 0.5,
            "max_weight": 25.0,
        })
        cls.pkg_type_pallet = cls.env["stock.package.type"].create({
            "name": "Euro Pallet HU Unpack",
            "base_weight": 20.0,
            "max_weight": 1000.0,
        })

        # Propietario 3PL
        cls.partner_owner = cls.env["res.partner"].create({
            "name": "3PL Logistics Owner",
            "company_id": False,
        })

        # Usuarios RBAC
        group_wms_op = cls.env.ref("wms_core.group_wms_operator")
        group_wms_sup = cls.env.ref("wms_core.group_wms_supervisor")
        group_wms_mgr = cls.env.ref("wms_core.group_wms_manager")
        group_stock_user = cls.env.ref("stock.group_stock_user")
        group_internal = cls.env.ref("base.group_user")

        cls.u_wms_op = cls.env["res.users"].create({
            "name": "u_hu_unpack_op",
            "login": "u_hu_unpack_op",
            "email": "hu_unpack_op@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_op.id])],
        })

        cls.u_wms_sup = cls.env["res.users"].create({
            "name": "u_hu_unpack_sup",
            "login": "u_hu_unpack_sup",
            "email": "hu_unpack_sup@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_sup.id])],
        })

        cls.u_wms_mgr = cls.env["res.users"].create({
            "name": "u_hu_unpack_mgr",
            "login": "u_hu_unpack_mgr",
            "email": "hu_unpack_mgr@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_mgr.id])],
        })

        cls.u_stock_usr = cls.env["res.users"].create({
            "name": "u_hu_unpack_stock_only",
            "login": "u_hu_unpack_stock_only",
            "email": "hu_unpack_stock_only@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_stock_user.id])],
        })

        cls.u_plain = cls.env["res.users"].create({
            "name": "u_hu_unpack_plain",
            "login": "u_hu_unpack_plain",
            "email": "hu_unpack_plain@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id])],
        })

        cls.u_cross_op = cls.env["res.users"].create({
            "name": "u_hu_unpack_cross_op",
            "login": "u_hu_unpack_cross_op",
            "email": "hu_unpack_cross_op@test.com",
            "company_id": cls.company_2.id,
            "company_ids": [(6, 0, [cls.company_2.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_op.id])],
        })

    def _create_packed_quant(self, product, location, qty, package, lot=False, owner=False, company=None):
        """Helper para crear stock empaquetado usando _update_available_quantity nativo."""
        comp = company or self.company_1
        self.env["stock.quant"].with_company(comp)._update_available_quantity(
            product,
            location,
            qty,
            lot_id=lot or None,
            package_id=package or None,
            owner_id=owner or None,
        )
        quant = self.env["stock.quant"].search([
            ("product_id", "=", product.id),
            ("location_id", "=", location.id),
            ("lot_id", "=", lot.id if lot else False),
            ("owner_id", "=", owner.id if owner else False),
            ("company_id", "=", comp.id),
            ("package_id", "=", package.id),
        ], limit=1)
        package.invalidate_recordset(["contained_quant_ids", "quant_ids", "location_id"])
        return quant

    def test_hu_044_physical_unpack_api_contract(self):
        """TEST-HU-044: Validación estricta de firma de API, tipos de argumentos y singleton."""
        package = self.env["stock.package"].create({"name": "PKG-HU-044", "hu_state": "OPEN"})
        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, package)

        # 1. ensure_one()
        empty_pkg = self.env["stock.package"].browse()
        with self.assertRaises(ValueError):
            empty_pkg.with_user(self.u_wms_op)._wms_unpack_physical(quant.id, 1.0)

        multi_pkg = package | self.env["stock.package"].create({"name": "PKG-HU-044-B", "hu_state": "OPEN"})
        with self.assertRaises(ValueError):
            multi_pkg.with_user(self.u_wms_op)._wms_unpack_physical(quant.id, 1.0)

        # 2. quant_id inválido
        for bad_quant_id in [False, True, 0, -1, "123", None]:
            with self.assertRaises(ValidationError):
                package.with_user(self.u_wms_op)._wms_unpack_physical(bad_quant_id, 1.0)

        # 3. quantity inválida
        for bad_qty in [False, True, 0, 0.0, -1.0, -0.5, float("nan"), float("inf"), -float("inf"), "two"]:
            with self.assertRaises(ValidationError):
                package.with_user(self.u_wms_op)._wms_unpack_physical(quant.id, bad_qty)

        # 4. correlation_id inválido
        for bad_corr in ["", "   ", True, False, 123]:
            with self.assertRaises(ValidationError):
                package.with_user(self.u_wms_op)._wms_unpack_physical(quant.id, 1.0, correlation_id=bad_corr)

        # 5. Quant inexistente
        with self.assertRaises(ValidationError):
            package.with_user(self.u_wms_op)._wms_unpack_physical(99999999, 1.0)

    def test_hu_045_partial_unpack_native_move_and_history(self):
        """TEST-HU-045: Desempaque parcial crea stock.move nativo, divide quant y no genera package history."""
        package = self.env["stock.package"].create({"name": "PKG-HU-045", "hu_state": "OPEN"})
        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, package)

        hist_count_before = self.env["stock.package.history"].search_count([])

        # Desempaque parcial: 4.0 de 10.0
        res = package.with_user(self.u_wms_op)._wms_unpack_physical(quant_id=quant.id, quantity=4.0)
        self.assertEqual(res["package_id"], package.id)
        self.assertTrue(res["correlation_id"])

        # Estado del paquete permanece OPEN
        self.assertEqual(package.hu_state, "OPEN")

        # Verificar inventario: 6.0 en paquete, 4.0 suelto, total 10.0
        packed_avail = self.env["stock.quant"]._get_available_quantity(
            self.product_standard,
            self.location_internal_1,
            package_id=package,
            strict=True,
            allow_negative=True,
        )
        loose_avail = self.env["stock.quant"]._get_available_quantity(
            self.product_standard,
            self.location_internal_1,
            package_id=None,
            strict=True,
            allow_negative=True,
        )
        self.assertEqual(packed_avail, 6.0)
        self.assertEqual(loose_avail, 4.0)

        # Verificar stock.move generado
        move = self.env["stock.move"].search([
            ("product_id", "=", self.product_standard.id),
            ("location_id", "=", self.location_internal_1.id),
            ("location_dest_id", "=", self.location_internal_1.id),
            ("inventory_name", "=", "WMS Physical Unpack"),
        ], order="id desc", limit=1)
        self.assertTrue(move, "Se debe haber materializado un stock.move para el unpack")
        self.assertEqual(move.state, "done")
        self.assertTrue(move.is_inventory)
        self.assertEqual(move.product_uom_qty, 4.0)

        # Verificar stock.move.line
        move_line = move.move_line_ids
        self.assertEqual(len(move_line), 1)
        self.assertEqual(move_line.package_id.id, package.id)
        self.assertEqual(move_line.result_package_id.id, False)

        # Verificar stock.package.history: upstream NO genera historia cuando result_package_id es False
        hist_count_after = self.env["stock.package.history"].search_count([])
        self.assertEqual(hist_count_after, hist_count_before, "No debe generarse stock.package.history en unpack hacia suelto")

    def test_hu_046_incremental_and_full_unpack_lifecycle_and_metadata(self):
        """TEST-HU-046: Desempaque incremental (OPEN -> OPEN) y total (OPEN -> EMPTY) preserva metadata de la HU."""
        package = self.env["stock.package"].create({
            "name": "075012345000000098",
            "hu_class": "CASE",
            "package_type_id": self.pkg_type_box.id,
            "shipping_weight": 1.5,
            "hu_state": "OPEN",
        })
        self.assertTrue(package.valid_sscc)
        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, package)

        # 1. Primer unpack parcial: 3.0 (remanente 7.0)
        package.with_user(self.u_wms_op)._wms_unpack_physical(quant_id=quant.id, quantity=3.0)
        self.assertEqual(package.name, "075012345000000098")
        self.assertTrue(package.valid_sscc)
        self.assertEqual(package.hu_state, "OPEN")
        self.assertEqual(package.hu_class, "CASE")
        self.assertEqual(package.package_type_id, self.pkg_type_box)
        self.assertEqual(package.shipping_weight, 1.5)

        # Refrescar quant empaquetado
        quant_packed_1 = self.env["stock.quant"].search([
            ("package_id", "=", package.id),
        ], limit=1)

        # 2. Segundo unpack parcial: 4.0 (remanente 3.0)
        package.with_user(self.u_wms_op)._wms_unpack_physical(quant_id=quant_packed_1.id, quantity=4.0)
        self.assertEqual(package.name, "075012345000000098")
        self.assertTrue(package.valid_sscc)
        self.assertEqual(package.hu_state, "OPEN")
        self.assertEqual(package.hu_class, "CASE")
        self.assertEqual(package.package_type_id, self.pkg_type_box)
        self.assertEqual(package.shipping_weight, 1.5)

        # Refrescar quant empaquetado
        quant_packed_2 = self.env["stock.quant"].search([
            ("package_id", "=", package.id),
        ], limit=1)

        # 3. Tercer unpack total: 3.0 (remanente 0 -> EMPTY)
        package.with_user(self.u_wms_op)._wms_unpack_physical(quant_id=quant_packed_2.id, quantity=3.0)
        self.assertEqual(package.name, "075012345000000098")
        self.assertTrue(package.valid_sscc)
        self.assertEqual(package.hu_state, "EMPTY", "Al quedar sin contenido, el paquete debe transicionar a EMPTY")
        self.assertEqual(package.hu_class, "CASE")
        self.assertEqual(package.package_type_id, self.pkg_type_box)
        self.assertEqual(package.shipping_weight, 1.5)
        self.assertFalse(package.contained_quant_ids)

        # Todo el stock (10.0) está suelto
        loose_avail = self.env["stock.quant"]._get_available_quantity(
            self.product_standard,
            self.location_internal_1,
            package_id=None,
            strict=True,
            allow_negative=True,
        )
        self.assertEqual(loose_avail, 10.0)

    def test_hu_047_unpack_event_outbox_contract(self):
        """TEST-HU-047: Contrato exacto de Event (UNPACK) y Outbox (inventory.hu.unpacked) v1 con lote y owner."""
        package = self.env["stock.package"].create({"name": "PKG-HU-047", "hu_state": "OPEN"})
        quant = self._create_packed_quant(
            self.product_tracked_lot,
            self.location_internal_1,
            10.0,
            package,
            lot=self.lot_1,
            owner=self.partner_owner,
        )
        corr_id_input = "  CORR-HU-047-UNPACK-CONTRACT  "
        corr_id_expected = "CORR-HU-047-UNPACK-CONTRACT"

        res = package.with_user(self.u_wms_op)._wms_unpack_physical(
            quant_id=quant.id,
            quantity=4.0,
            correlation_id=corr_id_input,
        )
        self.assertEqual(res["package_id"], package.id)
        self.assertEqual(res["correlation_id"], corr_id_expected)

        # Verificar wms.inventory.event
        event = self.env["wms.inventory.event"].search([
            ("correlation_id", "=", corr_id_expected),
        ])
        self.assertEqual(len(event), 1, "Debe existir exactamente un registro de evento para la correlación.")
        self.assertEqual(event.event_type, "UNPACK")
        self.assertEqual(event.company_id, self.company_1)
        self.assertEqual(event.product_id, self.product_tracked_lot)
        self.assertEqual(event.lot_id, self.lot_1)
        self.assertEqual(event.owner_id, self.partner_owner)
        self.assertEqual(event.quantity, 4.0)
        self.assertEqual(event.source_location_id, self.location_internal_1)
        self.assertEqual(event.dest_location_id, self.location_internal_1)
        self.assertEqual(event.package_id, package)
        self.assertEqual(event.operator_id, self.u_wms_op, "operator_id debe ser el usuario que ejecutó la acción.")
        self.assertEqual(event.warehouse_id, self.location_internal_1.warehouse_id)

        # Verificar wms.outbox
        outbox = self.env["wms.outbox"].search([
            ("correlation_id", "=", corr_id_expected),
        ])
        self.assertEqual(len(outbox), 1, "Debe existir exactamente un mensaje outbox para la correlación.")
        self.assertEqual(outbox.event_name, "inventory.hu.unpacked")
        self.assertEqual(outbox.company_id, self.company_1)
        self.assertEqual(outbox.schema_version, 1)
        self.assertEqual(outbox.status, "PENDING")
        self.assertEqual(outbox.attempt_count, 0)
        self.assertFalse(outbox.published_at)
        self.assertFalse(outbox.last_error)

        # Verificar payload del outbox (exactamente 8 claves)
        payload = outbox.payload
        self.assertIsInstance(payload, dict)
        self.assertEqual(set(payload.keys()), {
            "package_id", "package_ref", "product_id", "lot_id", "owner_id", "location_id", "quantity", "uom_id"
        })
        self.assertEqual(payload.get("package_id"), package.id)
        self.assertEqual(payload.get("package_ref"), package.name)
        self.assertEqual(payload.get("product_id"), self.product_tracked_lot.id)
        self.assertEqual(payload.get("lot_id"), self.lot_1.id)
        self.assertEqual(payload.get("owner_id"), self.partner_owner.id)
        self.assertEqual(payload.get("location_id"), self.location_internal_1.id)
        self.assertEqual(payload.get("quantity"), 4.0)
        self.assertEqual(payload.get("uom_id"), self.product_tracked_lot.uom_id.id)

    def test_hu_048_unpack_atomic_rollback_on_outbox_failure(self):
        """TEST-HU-048: Fallo en outbox revierte completamente la transacción (quant, move, hu_state, event)."""
        package = self.env["stock.package"].create({"name": "PKG-HU-048", "hu_state": "OPEN"})
        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, package)

        init_moves_count = self.env["stock.move"].search_count([])
        init_lines_count = self.env["stock.move.line"].search_count([])
        init_hist_count = self.env["stock.package.history"].search_count([])
        init_events_count = self.env["wms.inventory.event"].search_count([])
        init_outbox_count = self.env["wms.outbox"].search_count([])

        with patch.object(
            type(self.env["wms.outbox"]),
            "_enqueue_messages",
            side_effect=ValidationError("Error forzado en Outbox para probar rollback atómico en Unpack."),
        ):
            with self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    package.with_user(self.u_wms_op)._wms_unpack_physical(
                        quant_id=quant.id,
                        quantity=4.0,
                        correlation_id="CORR-ROLLBACK-UNPACK-TEST",
                    )

        # Verificar reversión total
        quant.invalidate_recordset(["quantity", "available_quantity", "package_id"])
        self.assertEqual(quant.quantity, 10.0)
        self.assertEqual(quant.package_id, package)

        package.invalidate_recordset(["hu_state", "contained_quant_ids"])
        self.assertEqual(package.hu_state, "OPEN")

        loose_avail = self.env["stock.quant"]._get_available_quantity(
            self.product_standard,
            self.location_internal_1,
            package_id=None,
            strict=True,
            allow_negative=True,
        )
        self.assertEqual(loose_avail, 0.0)

        self.assertEqual(self.env["stock.move"].search_count([]), init_moves_count)
        self.assertEqual(self.env["stock.move.line"].search_count([]), init_lines_count)
        self.assertEqual(self.env["stock.package.history"].search_count([]), init_hist_count)
        self.assertEqual(self.env["wms.inventory.event"].search_count([]), init_events_count)
        self.assertEqual(self.env["wms.outbox"].search_count([]), init_outbox_count)

    def test_hu_049_unpack_scope_and_lifecycle_guards(self):
        """TEST-HU-049: Rechazo de estados no OPEN, package vacío, quant ajeno o suelto, y anidamiento."""
        # 1. Estados prohibidos
        for bad_state in ["EMPTY", False, "CLOSED", "IN_TRANSIT", "SHIPPED", "RETURNED", "DISPOSED"]:
            pkg_bad = self.env["stock.package"].create({"name": f"PKG-UNP-{bad_state}", "hu_state": bad_state})
            quant_in_bad = self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_bad)
            with self.assertRaises(ValidationError):
                pkg_bad.with_user(self.u_wms_op)._wms_unpack_physical(quant_in_bad.id, 2.0)

        # 2. Package OPEN pero sin contenido físico
        pkg_open_empty = self.env["stock.package"].create({"name": "PKG-OPEN-EMPTY", "hu_state": "OPEN"})
        self.env["stock.quant"]._update_available_quantity(
            self.product_standard,
            self.location_internal_1,
            5.0,
            package_id=None,
        )
        quant_loose = self.env["stock.quant"].search([
            ("product_id", "=", self.product_standard.id),
            ("location_id", "=", self.location_internal_1.id),
            ("package_id", "=", False),
        ], limit=1)
        with self.assertRaises(ValidationError):
            pkg_open_empty.with_user(self.u_wms_op)._wms_unpack_physical(quant_loose.id, 2.0)

        # 3. Quant no pertenece a la HU (quant suelto)
        pkg_ok = self.env["stock.package"].create({"name": "PKG-UNP-OK", "hu_state": "OPEN"})
        quant_ok = self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_ok)
        with self.assertRaises(ValidationError):
            pkg_ok.with_user(self.u_wms_op)._wms_unpack_physical(quant_loose.id, 2.0)

        # 4. Quant pertenece a OTRA HU
        pkg_other = self.env["stock.package"].create({"name": "PKG-UNP-OTHER", "hu_state": "OPEN"})
        quant_other = self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_other)
        with self.assertRaises(ValidationError):
            pkg_ok.with_user(self.u_wms_op)._wms_unpack_physical(quant_other.id, 2.0)

        # 5. Jerarquía anidada prohibida (HU top-level plana)
        pkg_parent = self.env["stock.package"].create({"name": "PKG-UNP-PARENT", "hu_state": "OPEN"})
        pkg_child = self.env["stock.package"].create({
            "name": "PKG-UNP-CHILD",
            "parent_package_id": pkg_parent.id,
            "hu_state": "OPEN",
        })
        quant_child = self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_child)
        with self.assertRaises(ValidationError):
            pkg_child.with_user(self.u_wms_op)._wms_unpack_physical(quant_child.id, 2.0)
        with self.assertRaises(ValidationError):
            pkg_parent.with_user(self.u_wms_op)._wms_unpack_physical(quant_child.id, 2.0)

    def test_hu_050_unpack_reservations_tracking_uom_guards(self):
        """TEST-HU-050: Guards de reservas, ubicación, exceso, tracking; happy path de lote y serie."""
        package = self.env["stock.package"].create({"name": "PKG-HU-050", "hu_state": "OPEN"})
        quant_std = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, package)

        # 1. Quant con reservas activas
        quant_std.sudo().write({"reserved_quantity": 3.0})
        with self.assertRaises(ValidationError):
            package.with_user(self.u_wms_op)._wms_unpack_physical(quant_std.id, 2.0)
        quant_std.sudo().write({"reserved_quantity": 0.0})

        # 2. Cantidad solicitada excede disponibilidad
        with self.assertRaises(ValidationError):
            package.with_user(self.u_wms_op)._wms_unpack_physical(quant_std.id, 15.0)

        # 3. Ubicación no interna
        pkg_cust = self.env["stock.package"].create({"name": "PKG-CUST", "hu_state": "OPEN"})
        quant_cust = self._create_packed_quant(self.product_standard, self.location_customer, 10.0, pkg_cust)
        with self.assertRaises(ValidationError):
            pkg_cust.with_user(self.u_wms_op)._wms_unpack_physical(quant_cust.id, 2.0)

        # 4. Producto tracked por lote sin lote en quant
        pkg_no_lot = self.env["stock.package"].create({"name": "PKG-NO-LOT", "hu_state": "OPEN"})
        quant_no_lot = self._create_packed_quant(self.product_tracked_lot, self.location_internal_1, 5.0, pkg_no_lot)
        with self.assertRaises(ValidationError):
            pkg_no_lot.with_user(self.u_wms_op)._wms_unpack_physical(quant_no_lot.id, 2.0)

        # 5. Producto tracked serial con cantidad distinta de 1.0 (aislado: 0.5 con 1.0 disponible)
        pkg_serial = self.env["stock.package"].create({"name": "PKG-SERIAL", "hu_state": "OPEN"})
        quant_serial = self._create_packed_quant(
            self.product_tracked_serial, self.location_internal_1, 1.0, pkg_serial, lot=self.lot_serial_1
        )
        with self.assertRaises(ValidationError):
            pkg_serial.with_user(self.u_wms_op)._wms_unpack_physical(quant_serial.id, 0.5)

        # 6. Happy path: unpack con lote
        pkg_lot_ok = self.env["stock.package"].create({"name": "PKG-LOT-OK", "hu_state": "OPEN"})
        quant_lot_ok = self._create_packed_quant(
            self.product_tracked_lot, self.location_internal_1, 5.0, pkg_lot_ok, lot=self.lot_1
        )
        res_lot = pkg_lot_ok.with_user(self.u_wms_op)._wms_unpack_physical(quant_lot_ok.id, 2.0)
        self.assertEqual(res_lot["package_id"], pkg_lot_ok.id)

        # 7. Happy path: unpack serial exactamente 1.0
        res_sn = pkg_serial.with_user(self.u_wms_op)._wms_unpack_physical(quant_serial.id, 1.0)
        self.assertEqual(res_sn["package_id"], pkg_serial.id)
        self.assertEqual(pkg_serial.hu_state, "EMPTY")

    def test_hu_051_inventory_block_guards(self):
        """TEST-HU-051: Bloqueos de inventario (LOCATION, PRODUCT_LOCATION, LOT, PACKAGE, OWNER_LOCATION) abortan unpack."""
        package = self.env["stock.package"].create({"name": "PKG-HU-051", "hu_state": "OPEN"})
        quant_std = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, package)
        quant_lot = self._create_packed_quant(
            self.product_tracked_lot, self.location_internal_1, 10.0, package, lot=self.lot_1, owner=self.partner_owner
        )

        moves_before = self.env["stock.move"].search_count([])

        # 1. Bloqueo LOCATION
        b_loc = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "LOCATION",
            "location_id": self.location_internal_1.id,
            "block_type": "HOLD",
            "reason": "Location hold",
        })
        with self.assertRaises(ValidationError):
            package.with_user(self.u_wms_op)._wms_unpack_physical(quant_std.id, 2.0)
        self.assertEqual(self.env["stock.move"].search_count([]), moves_before)
        b_loc.action_release()

        # 2. Bloqueo PRODUCT_LOCATION
        b_prod_loc = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "PRODUCT_LOCATION",
            "product_id": self.product_standard.id,
            "location_id": self.location_internal_1.id,
            "block_type": "INVESTIGATION",
            "reason": "Product location hold",
        })
        with self.assertRaises(ValidationError):
            package.with_user(self.u_wms_op)._wms_unpack_physical(quant_std.id, 2.0)
        self.assertEqual(self.env["stock.move"].search_count([]), moves_before)
        b_prod_loc.action_release()

        # 3. Bloqueo LOT
        b_lot = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "LOT",
            "product_id": self.product_tracked_lot.id,
            "lot_id": self.lot_1.id,
            "block_type": "HOLD",
            "reason": "Lot hold",
        })
        with self.assertRaises(ValidationError):
            package.with_user(self.u_wms_op)._wms_unpack_physical(quant_lot.id, 2.0)
        self.assertEqual(self.env["stock.move"].search_count([]), moves_before)
        b_lot.action_release()

        # 4. Bloqueo PACKAGE
        b_pkg = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "PACKAGE",
            "package_id": package.id,
            "block_type": "HOLD",
            "reason": "Package hold",
        })
        with self.assertRaises(ValidationError):
            package.with_user(self.u_wms_op)._wms_unpack_physical(quant_std.id, 2.0)
        self.assertEqual(self.env["stock.move"].search_count([]), moves_before)
        b_pkg.action_release()

        # 5. Bloqueo OWNER_LOCATION
        b_owner_loc = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "OWNER_LOCATION",
            "owner_id": self.partner_owner.id,
            "location_id": self.location_internal_1.id,
            "block_type": "HOLD",
            "reason": "Owner location hold",
        })
        with self.assertRaises(ValidationError):
            package.with_user(self.u_wms_op)._wms_unpack_physical(quant_lot.id, 2.0)
        self.assertEqual(self.env["stock.move"].search_count([]), moves_before)
        b_owner_loc.action_release()

        # 6. Sin bloqueos -> unpack exitoso
        res = package.with_user(self.u_wms_op)._wms_unpack_physical(quant_std.id, 2.0)
        self.assertEqual(res["package_id"], package.id)

    def test_hu_052_plm_is_admission_only(self):
        """TEST-HU-052: PLM es política de admisión al empaque; no impide retirar inventario de una HU."""
        # Configurar perfil PLM restringiendo a PALLET únicamente
        self.env["wms.product.logistics"].create({
            "product_tmpl_id": self.product_standard.product_tmpl_id.id,
            "company_id": self.company_1.id,
            "allowed_hu_type_ids": [(6, 0, [self.pkg_type_pallet.id])],
            "default_hu_type_id": self.pkg_type_pallet.id,
        })

        # Paquete que contiene el producto pero tiene tipo BOX (no permitido para empaque nuevo)
        package = self.env["stock.package"].create({
            "name": "PKG-BOX-LEGACY",
            "package_type_id": self.pkg_type_box.id,
            "hu_state": "OPEN",
        })
        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, package)

        # Unpack DEBE tener éxito porque PLM no bloquea la salida
        res = package.with_user(self.u_wms_op)._wms_unpack_physical(quant.id, 4.0)
        self.assertEqual(res["package_id"], package.id)
        self.assertEqual(package.package_type_id, self.pkg_type_box, "Unpack no debe alterar el tipo de paquete existente")

    def test_hu_053_rbac_company_and_privilege_boundary(self):
        """TEST-HU-053: Matriz RBAC completa, aislamiento multi-compañía y narrow sudo."""
        package = self.env["stock.package"].create({"name": "PKG-HU-053", "hu_state": "OPEN"})
        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, package)

        # 1a. Operator ejecuta unpack exitosamente
        res = package.with_user(self.u_wms_op)._wms_unpack_physical(quant.id, 2.0)
        self.assertEqual(res["package_id"], package.id)

        # 1b. Supervisor ejecuta unpack exitosamente
        pkg_sup = self.env["stock.package"].create({"name": "PKG-HU-053-SUP", "hu_state": "OPEN"})
        quant_sup = self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_sup)
        res_sup = pkg_sup.with_user(self.u_wms_sup)._wms_unpack_physical(quant_sup.id, 2.0)
        self.assertEqual(res_sup["package_id"], pkg_sup.id)

        # 1c. Manager ejecuta unpack exitosamente
        pkg_mgr = self.env["stock.package"].create({"name": "PKG-HU-053-MGR", "hu_state": "OPEN"})
        quant_mgr = self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_mgr)
        res_mgr = pkg_mgr.with_user(self.u_wms_mgr)._wms_unpack_physical(quant_mgr.id, 2.0)
        self.assertEqual(res_mgr["package_id"], pkg_mgr.id)

        # 2a. Operator intentando modificar directamente el paquete recibe AccessError
        with self.assertRaises(AccessError):
            package.with_user(self.u_wms_op).write({"hu_state": "CLOSED"})

        # 2b. Operator intentando modificar directamente stock.quant.package_id recibe AccessError
        with self.assertRaises(AccessError):
            quant.with_user(self.u_wms_op).write({"package_id": False})

        # 3. Plain internal user recibe AccessError
        with self.assertRaises(AccessError):
            package.with_user(self.u_plain)._wms_unpack_physical(quant.id, 1.0)

        # 4. Pure stock user (sin rol WMS) recibe AccessError
        with self.assertRaises(AccessError):
            package.with_user(self.u_stock_usr)._wms_unpack_physical(quant.id, 1.0)

        # 5a. Operator de compañía 2 sobre quant de compañía 1 recibe AccessError
        with self.assertRaises(AccessError):
            package.with_user(self.u_cross_op)._wms_unpack_physical(quant.id, 1.0)

        # 5b. Unpack sobre paquete con quants mixtos de multi-compañía (company_id=False) se rechaza con ValidationError
        pkg_multi = self.env["stock.package"].create({"name": "PKG-HU-053-MULTI", "hu_state": "OPEN"})
        quant_c1 = self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_multi)
        self.env.cr.execute("UPDATE stock_package SET company_id = NULL WHERE id = %s", [pkg_multi.id])
        pkg_multi.invalidate_recordset(["company_id"])
        with self.assertRaises(ValidationError):
            pkg_multi.with_user(self.u_wms_op)._wms_unpack_physical(quant_c1.id, 2.0)

        # 6. El evento de inventario debe registrar el ID del operador real
        event = self.env["wms.inventory.event"].search([
            ("correlation_id", "=", res["correlation_id"]),
        ], limit=1)
        self.assertEqual(event.operator_id, self.u_wms_op)

    @mute_logger("odoo.sql_db")
    def test_hu_054_concurrency_post_lock_serialization(self):
        """TEST-HU-054: Concurrencia real con dos threads, bloqueo mutuo y serialización post-lock exacta."""
        # 1. Crear fixtures en un cursor independiente para que ambas transacciones los vean
        with self.env.registry.cursor() as cr_setup:
            env_setup = api.Environment(cr_setup, 1, {})
            prod = env_setup["product.product"].create({
                "name": "Product Concurrency Unpack",
                "is_storable": True,
            })
            loc_parent = env_setup.ref("stock.stock_location_stock").location_id
            loc = env_setup["stock.location"].create({
                "name": "LOC-CONC-UNPACK",
                "usage": "internal",
                "location_id": loc_parent.id if loc_parent else False,
            })
            pkg = env_setup["stock.package"].create({
                "name": "PKG-HU-054-CONC",
                "hu_state": "OPEN",
            })
            env_setup["stock.quant"]._update_available_quantity(
                prod,
                loc,
                10.0,
                package_id=pkg,
            )
            quant = env_setup["stock.quant"].search([
                ("product_id", "=", prod.id),
                ("package_id", "=", pkg.id),
            ], limit=1)
            pkg_id = pkg.id
            quant_id = quant.id
            prod_id = prod.id
            tmpl_id = prod.product_tmpl_id.id
            loc_id = loc.id
            cr_setup.commit()

        cr2 = self.env.registry.cursor()
        env2 = api.Environment(cr2, 1, {})
        pkg2 = env2["stock.package"].browse(pkg_id)

        try:
            barrier_t1_locked = threading.Event()
            barrier_t2_calling = threading.Event()
            t2_result = {}

            def thread_2_worker():
                try:
                    # Esperar a que T1 haya ejecutado la mutación y tomado los locks de fila
                    barrier_t1_locked.wait(timeout=10.0)
                    barrier_t2_calling.set()
                    try:
                        # T2 intentará desempaquetar y quedará bloqueada en PostgreSQL esperando el lock de T1
                        pkg2._wms_unpack_physical(quant_id, 8.0, correlation_id="CORR-2TH-T2")
                        cr2.commit()
                        t2_result["success"] = True
                    except Exception as exc:
                        cr2.rollback()
                        t2_result["error_class"] = type(exc).__name__
                        t2_result["error_msg"] = str(exc)
                        t2_result["is_serialization_failure"] = (
                            type(exc).__name__ == "SerializationFailure"
                            or "could not serialize access" in str(exc)
                        )
                except BaseException as exc:
                    barrier_t2_calling.set()
                    t2_result["outer_error"] = str(exc)
                finally:
                    cr2.close()

            t2 = threading.Thread(target=thread_2_worker)
            t2.start()

            with self.env.registry.cursor() as cr1:
                env1 = api.Environment(cr1, 1, {})
                pkg1 = env1["stock.package"].browse(pkg_id)
                # T1 ejecuta unpack de 6.0 adquiriendo los locks pero SIN commitear todavía
                res1 = pkg1._wms_unpack_physical(quant_id, 6.0, correlation_id="CORR-2TH-T1")
                self.assertEqual(res1.get("package_id"), pkg_id)
                self.assertEqual(res1.get("correlation_id"), "CORR-2TH-T1")

                # Señalar a T2 para que intente adquirir el lock y quede bloqueada
                barrier_t1_locked.set()
                self.assertTrue(barrier_t2_calling.wait(timeout=5.0), f"T2 debió invocar el primitive: {t2_result}")
                time.sleep(0.4)

                # Verificar en pg_locks que T2 está activamente bloqueada esperando la transacción de T1
                cr1.execute('''
                    SELECT COUNT(*)
                    FROM pg_locks l
                    WHERE NOT l.granted AND l.locktype = 'transactionid'
                ''')
                waiting_locks = cr1.fetchone()[0]
                self.assertGreaterEqual(waiting_locks, 1, "T2 debe estar bloqueada en PostgreSQL esperando el lock de T1")

                # T1 hace commit, liberando los locks
                cr1.commit()

            t2.join(timeout=10.0)
            self.assertFalse(t2.is_alive(), "T2 thread debió terminar")

            # Verificaciones de rechazo exacto por concurrencia
            self.assertFalse(t2_result.get("success"), "T2 no debió tener éxito tras la mutación concurrente de T1")
            self.assertTrue(
                t2_result.get("is_serialization_failure"),
                f"T2 debió recibir SerializationFailure exacto, pero ocurrió: {t2_result}",
            )
            self.assertEqual(
                t2_result.get("error_class"),
                "SerializationFailure",
                f"Clase de error de T2 debió ser SerializationFailure: {t2_result}",
            )

            # Comprobar consistencia e invariantes físicas en una lectura fresca
            with self.env.registry.cursor() as cr_check:
                env_check = api.Environment(cr_check, 1, {})
                pkg_check = env_check["stock.package"].browse(pkg_id)
                self.assertEqual(pkg_check.hu_state, "OPEN")
                self.assertEqual(pkg_check.contained_quant_ids.quantity, 4.0)

                loose_avail = env_check["stock.quant"]._get_available_quantity(
                    env_check["product.product"].browse(prod_id),
                    env_check["stock.location"].browse(loc_id),
                    package_id=None,
                    strict=True,
                    allow_negative=True,
                )
                self.assertEqual(loose_avail, 6.0)
                # Invariante de conservación de masa: 4.0 + 6.0 = 10.0
                self.assertEqual(pkg_check.contained_quant_ids.quantity + loose_avail, 10.0)

                # Verificar que sólo existe 1 evento y 1 outbox (de T1)
                events = env_check["wms.inventory.event"].search([("correlation_id", "in", ["CORR-2TH-T1", "CORR-2TH-T2"])])
                self.assertEqual(len(events), 1)
                self.assertEqual(events.correlation_id, "CORR-2TH-T1")

                outbox = env_check["wms.outbox"].search([("correlation_id", "in", ["CORR-2TH-T1", "CORR-2TH-T2"])])
                self.assertEqual(len(outbox), 1)
                self.assertEqual(outbox.correlation_id, "CORR-2TH-T1")
        finally:
            # Cleanup de registros creados en el cursor independiente mediante SQL directo
            with self.env.registry.cursor() as cr_clean:
                cr_clean.execute("DELETE FROM wms_outbox WHERE correlation_id IN (%s, %s)", ["CORR-2TH-T1", "CORR-2TH-T2"])
                cr_clean.execute("DELETE FROM wms_inventory_event WHERE correlation_id IN (%s, %s)", ["CORR-2TH-T1", "CORR-2TH-T2"])
                cr_clean.execute("DELETE FROM stock_move_line WHERE package_id = %s OR product_id = %s", [pkg_id, prod_id])
                cr_clean.execute("DELETE FROM stock_move WHERE product_id = %s", [prod_id])
                cr_clean.execute("DELETE FROM stock_quant WHERE product_id = %s", [prod_id])
                cr_clean.execute("DELETE FROM stock_package WHERE id = %s", [pkg_id])
                cr_clean.execute("DELETE FROM product_product WHERE id = %s", [prod_id])
                cr_clean.execute("DELETE FROM product_template WHERE id = %s", [tmpl_id])
                cr_clean.execute("DELETE FROM stock_location WHERE id = %s", [loc_id])
                cr_clean.commit()
