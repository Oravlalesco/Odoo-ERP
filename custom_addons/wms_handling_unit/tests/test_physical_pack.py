import math
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestPhysicalPack(TransactionCase):
    """Suite de pruebas unitarias para HU-004A — Physical Pack Core (TEST-HU-035 a TEST-HU-043).

    Verifica el primitive transaccional _wms_pack_physical() en stock.package,
    garantizando la mutación física de stock.quant vía stock.move, la transición
    de ciclo de vida hu_state -> OPEN, la persistencia atómica de wms.inventory.event (PACK)
    y wms.outbox (inventory.hu.packed) bajo un mismo correlation_id (ADR-019),
    guards operacionales, PLM, bloqueos de inventario y fronteras de seguridad RBAC.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_1 = cls.env.company
        cls.company_2 = cls.env["res.company"].create({"name": "Secondary Company HU"})

        # Ubicaciones
        cls.location_internal_1 = cls.env["stock.location"].create({
            "name": "Pack Loc Internal 1",
            "usage": "internal",
            "company_id": cls.company_1.id,
        })
        cls.location_internal_2 = cls.env["stock.location"].create({
            "name": "Pack Loc Internal 2",
            "usage": "internal",
            "company_id": cls.company_2.id,
        })
        cls.location_customer = cls.env["stock.location"].create({
            "name": "Pack Loc Customer",
            "usage": "customer",
            "company_id": cls.company_1.id,
        })

        # Productos
        cls.product_standard = cls.env["product.product"].create({
            "name": "Product Standard HU Pack",
            "is_storable": True,
            "tracking": "none",
            "company_id": False,
        })
        cls.product_tracked_lot = cls.env["product.product"].create({
            "name": "Product Tracked Lot HU Pack",
            "is_storable": True,
            "tracking": "lot",
            "company_id": False,
        })
        cls.product_tracked_serial = cls.env["product.product"].create({
            "name": "Product Tracked Serial HU Pack",
            "is_storable": True,
            "tracking": "serial",
            "company_id": False,
        })

        # Lotes
        cls.lot_1 = cls.env["stock.lot"].create({
            "name": "LOT-HU-001",
            "product_id": cls.product_tracked_lot.id,
            "company_id": cls.company_1.id,
        })
        cls.lot_serial_1 = cls.env["stock.lot"].create({
            "name": "SN-HU-001",
            "product_id": cls.product_tracked_serial.id,
            "company_id": cls.company_1.id,
        })

        # Tipos de paquete
        cls.pkg_type_box = cls.env["stock.package.type"].create({
            "name": "Box Standard HU",
            "base_weight": 0.5,
            "max_weight": 25.0,
        })
        cls.pkg_type_pallet = cls.env["stock.package.type"].create({
            "name": "Euro Pallet HU",
            "base_weight": 20.0,
            "max_weight": 1000.0,
        })

        # Usuarios RBAC
        group_wms_op = cls.env.ref("wms_core.group_wms_operator")
        group_wms_sup = cls.env.ref("wms_core.group_wms_supervisor")
        group_wms_mgr = cls.env.ref("wms_core.group_wms_manager")
        group_stock_user = cls.env.ref("stock.group_stock_user")
        group_internal = cls.env.ref("base.group_user")

        cls.u_wms_op = cls.env["res.users"].create({
            "name": "u_hu_op_only",
            "login": "u_hu_op_only",
            "email": "hu_op_only@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_op.id])],
        })

        cls.u_wms_sup = cls.env["res.users"].create({
            "name": "u_hu_sup",
            "login": "u_hu_sup",
            "email": "hu_sup@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_sup.id])],
        })

        cls.u_wms_mgr = cls.env["res.users"].create({
            "name": "u_hu_mgr",
            "login": "u_hu_mgr",
            "email": "hu_mgr@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_mgr.id])],
        })

        cls.u_stock_usr = cls.env["res.users"].create({
            "name": "u_hu_stock_only",
            "login": "u_hu_stock_only",
            "email": "hu_stock_only@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_stock_user.id])],
        })

        cls.u_plain = cls.env["res.users"].create({
            "name": "u_hu_plain",
            "login": "u_hu_plain",
            "email": "hu_plain@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id])],
        })

        cls.u_cross_op = cls.env["res.users"].create({
            "name": "u_hu_cross_op",
            "login": "u_hu_cross_op",
            "email": "hu_cross_op@test.com",
            "company_id": cls.company_2.id,
            "company_ids": [(6, 0, [cls.company_2.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_op.id])],
        })

    def _create_loose_quant(self, product, location, quantity, lot=None, company=None):
        company = company or self.company_1
        self.env["stock.quant"].with_company(company)._update_available_quantity(
            product,
            location,
            quantity,
            lot_id=lot,
        )
        quant = self.env["stock.quant"].search([
            ("product_id", "=", product.id),
            ("location_id", "=", location.id),
            ("lot_id", "=", lot.id if lot else False),
            ("company_id", "=", company.id),
            ("package_id", "=", False),
        ], limit=1)
        return quant

    def test_hu_035_physical_pack_api_contract(self):
        """TEST-HU-035: Contrato de API, preflights estrictos de argumentos y empaque singleton."""
        package = self.env["stock.package"].create({
            "name": "PKG-HU-035",
        })
        quant = self._create_loose_quant(self.product_standard, self.location_internal_1, 10.0)

        # 1. Validar quant_id inválido
        for bad_id in [False, True, 0, -5, "abc", 999999]:
            with self.assertRaises(ValidationError):
                package.with_user(self.u_wms_op)._wms_pack_physical(quant_id=bad_id, quantity=5.0)

        # 2. Validar quantity inválida
        for bad_qty in [False, True, 0, 0.0, -1.0, float("nan"), float("inf"), float("-inf")]:
            with self.assertRaises(ValidationError):
                package.with_user(self.u_wms_op)._wms_pack_physical(quant_id=quant.id, quantity=bad_qty)

        # 3. Validar correlation_id inválido
        for bad_corr in [False, True, 123, "", "   "]:
            with self.assertRaises(ValidationError):
                package.with_user(self.u_wms_op)._wms_pack_physical(quant_id=quant.id, quantity=5.0, correlation_id=bad_corr)

        # 4. Invocación válida singleton
        res = package.with_user(self.u_wms_op)._wms_pack_physical(quant_id=quant.id, quantity=5.0)
        self.assertIsInstance(res, dict)
        self.assertEqual(res["package_id"], package.id)
        self.assertTrue(res["correlation_id"])
        self.assertEqual(package.hu_state, "OPEN")
        self.assertEqual(package.company_id, self.company_1)
        self.assertEqual(package.location_id, self.location_internal_1)

    def test_hu_036_partial_pack_native_move_and_history(self):
        """TEST-HU-036: Empaque parcial, mutación nativa stock.move y generación de stock.package.history."""
        package = self.env["stock.package"].create({"name": "PKG-HU-036"})
        quant = self._create_loose_quant(self.product_standard, self.location_internal_1, 10.0)

        # Empaque parcial: 4.0 unidades de 10.0
        res = package.with_user(self.u_wms_op)._wms_pack_physical(quant_id=quant.id, quantity=4.0)

        # Verificar cantidades lógicas en la ubicación
        loose_avail = self.env["stock.quant"]._get_available_quantity(
            self.product_standard,
            self.location_internal_1,
            package_id=None,
            strict=True,
            allow_negative=True,
        )
        packed_avail = self.env["stock.quant"]._get_available_quantity(
            self.product_standard,
            self.location_internal_1,
            package_id=package,
            strict=True,
            allow_negative=True,
        )
        total_avail = self.env["stock.quant"]._get_available_quantity(
            self.product_standard,
            self.location_internal_1,
            strict=False,
            allow_negative=True,
        )

        self.assertEqual(loose_avail, 6.0)
        self.assertEqual(packed_avail, 4.0)
        self.assertEqual(total_avail, 10.0)

        # Verificar generación de stock.move en estado done
        move = self.env["stock.move"].search([
            ("product_id", "=", self.product_standard.id),
            ("location_id", "=", self.location_internal_1.id),
            ("state", "=", "done"),
            ("is_inventory", "=", True),
        ], order="id desc", limit=1)
        self.assertTrue(move)
        self.assertEqual(move.product_uom_qty, 4.0)

        # Verificar move line con result_package_id
        move_line = move.move_line_ids
        self.assertEqual(len(move_line), 1)
        self.assertEqual(move_line.package_id.id, False)
        self.assertEqual(move_line.result_package_id.id, package.id)

        # Verificar stock.package.history
        history = self.env["stock.package.history"].search([
            ("package_id", "=", package.id),
        ], limit=1)
        self.assertTrue(history, "Se debe haber generado un registro en stock.package.history")
        self.assertEqual(history.location_dest_id, self.location_internal_1)

    def test_hu_037_incremental_pack_preserves_package_metadata(self):
        """TEST-HU-037: Empaques incrementales preservan metadata de la HU (OPEN -> OPEN sin sobreescrituras)."""
        package = self.env["stock.package"].create({
            "name": "075012345000000098",
            "hu_class": "CASE",
            "package_type_id": self.pkg_type_box.id,
            "shipping_weight": 1.5,
        })
        self.assertTrue(package.valid_sscc)
        quant = self._create_loose_quant(self.product_standard, self.location_internal_1, 10.0)

        # Primer empaque: 4.0
        package.with_user(self.u_wms_op)._wms_pack_physical(quant_id=quant.id, quantity=4.0)
        self.assertEqual(package.name, "075012345000000098")
        self.assertTrue(package.valid_sscc)
        self.assertEqual(package.hu_state, "OPEN")
        self.assertEqual(package.hu_class, "CASE")
        self.assertEqual(package.package_type_id, self.pkg_type_box)
        self.assertEqual(package.shipping_weight, 1.5)

        # Refrescar quant suelto remanente
        quant_rem = self.env["stock.quant"].search([
            ("product_id", "=", self.product_standard.id),
            ("location_id", "=", self.location_internal_1.id),
            ("package_id", "=", False),
        ], limit=1)

        # Segundo empaque incremental: 3.0 adicionales
        package.with_user(self.u_wms_op)._wms_pack_physical(quant_id=quant_rem.id, quantity=3.0)
        self.assertEqual(package.name, "075012345000000098")
        self.assertTrue(package.valid_sscc)
        self.assertEqual(package.hu_state, "OPEN")
        self.assertEqual(package.hu_class, "CASE")
        self.assertEqual(package.package_type_id, self.pkg_type_box)
        self.assertEqual(package.shipping_weight, 1.5)

        # Total en paquete debe ser 7.0
        packed_avail = self.env["stock.quant"]._get_available_quantity(
            self.product_standard,
            self.location_internal_1,
            package_id=package,
            strict=True,
            allow_negative=True,
        )
        self.assertEqual(packed_avail, 7.0)

    def test_hu_038_pack_event_outbox_contract(self):
        """TEST-HU-038: Contrato exacto de Event (PACK) y Outbox (inventory.hu.packed) v1 con normalización de correlation_id."""
        package = self.env["stock.package"].create({"name": "PKG-HU-038"})
        quant = self._create_loose_quant(self.product_standard, self.location_internal_1, 10.0)
        corr_id_input = "  CORR-HU-038-PACK-CONTRACT  "
        corr_id_expected = "CORR-HU-038-PACK-CONTRACT"

        res = package.with_user(self.u_wms_op)._wms_pack_physical(
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
        self.assertEqual(event.event_type, "PACK")
        self.assertEqual(event.company_id, self.company_1)
        self.assertEqual(event.product_id, self.product_standard)
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
        self.assertEqual(outbox.event_name, "inventory.hu.packed")
        self.assertEqual(outbox.company_id, self.company_1)
        self.assertEqual(outbox.schema_version, 1)
        self.assertEqual(outbox.status, "PENDING")
        self.assertEqual(outbox.attempt_count, 0)
        self.assertFalse(outbox.published_at)
        self.assertFalse(outbox.last_error)

        # Verificar payload del outbox
        payload = outbox.payload
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload.get("package_id"), package.id)
        self.assertEqual(payload.get("package_ref"), package.name)
        self.assertEqual(payload.get("product_id"), self.product_standard.id)
        self.assertEqual(payload.get("lot_id"), False)
        self.assertEqual(payload.get("owner_id"), False)
        self.assertEqual(payload.get("location_id"), self.location_internal_1.id)
        self.assertEqual(payload.get("quantity"), 4.0)
        self.assertEqual(payload.get("uom_id"), self.product_standard.uom_id.id)

    def test_hu_039_pack_atomic_rollback_on_outbox_failure(self):
        """TEST-HU-039: Fallo en outbox revierte completamente la transacción (quant, move, history, event)."""
        package = self.env["stock.package"].create({"name": "PKG-HU-039", "hu_state": "EMPTY"})
        quant = self._create_loose_quant(self.product_standard, self.location_internal_1, 10.0)

        # Capturar snapshots previos
        init_moves_count = self.env["stock.move"].search_count([])
        init_lines_count = self.env["stock.move.line"].search_count([])
        init_hist_count = self.env["stock.package.history"].search_count([])
        init_events_count = self.env["wms.inventory.event"].search_count([])
        init_outbox_count = self.env["wms.outbox"].search_count([])

        # Simular fallo en outbox dentro de un savepoint
        with patch.object(
            type(self.env["wms.outbox"]),
            "_enqueue_messages",
            side_effect=ValidationError("Error forzado en Outbox para probar rollback atómico."),
        ):
            with self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    package.with_user(self.u_wms_op)._wms_pack_physical(
                        quant_id=quant.id,
                        quantity=4.0,
                        correlation_id="CORR-ROLLBACK-TEST",
                    )

        # Verificar reversión total de la base de datos
        # 1. Quant suelto intacto en 10.0
        quant.invalidate_recordset(["quantity", "available_quantity"])
        self.assertEqual(quant.quantity, 10.0)
        self.assertEqual(quant.available_quantity, 10.0)

        # 2. Sin quant en paquete
        packed_quants = self.env["stock.quant"].search([("package_id", "=", package.id)])
        self.assertFalse(packed_quants)

        # 3. Estado de la HU no mutó
        package.invalidate_recordset(["hu_state"])
        self.assertEqual(package.hu_state, "EMPTY")

        # 4. Conteos de registros idénticos a los iniciales
        self.assertEqual(self.env["stock.move"].search_count([]), init_moves_count)
        self.assertEqual(self.env["stock.move.line"].search_count([]), init_lines_count)
        self.assertEqual(self.env["stock.package.history"].search_count([]), init_hist_count)
        self.assertEqual(self.env["wms.inventory.event"].search_count([]), init_events_count)
        self.assertEqual(self.env["wms.outbox"].search_count([]), init_outbox_count)

    def test_hu_040_pack_operational_guards(self):
        """TEST-HU-040: Validaciones operacionales exhaustivas y rechazo de estados fuera de contrato."""
        quant = self._create_loose_quant(self.product_standard, self.location_internal_1, 10.0)

        # 1. Estados prohibidos
        for bad_state in ["CLOSED", "IN_TRANSIT", "SHIPPED", "RETURNED", "DISPOSED"]:
            pkg_bad = self.env["stock.package"].create({"name": f"PKG-{bad_state}", "hu_state": bad_state})
            with self.assertRaises(ValidationError):
                pkg_bad.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 2.0)

        # 2. Adopción inválida de paquete con contenido previo pero hu_state=False
        pkg_with_content = self.env["stock.package"].create({"name": "PKG-HIST-CONTENT"})
        self.env["stock.quant"]._update_available_quantity(
            self.product_standard,
            self.location_internal_1,
            5.0,
            package_id=pkg_with_content,
        )
        with self.assertRaises(ValidationError):
            pkg_with_content.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 2.0)

        # 3. Handling Unit con hu_state='EMPTY' pero con contenido preexistente -> FAIL
        pkg_empty_with_content = self.env["stock.package"].create({
            "name": "PKG-EMPTY-WITH-CONTENT",
            "hu_state": "EMPTY",
        })
        self.env["stock.quant"].with_company(self.company_1)._update_available_quantity(
            self.product_standard,
            self.location_internal_1,
            3.0,
            package_id=pkg_empty_with_content,
        )
        with self.assertRaises(ValidationError):
            pkg_empty_with_content.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 2.0)

        # 4. Quant ya empaquetado no puede ser empaquetado de nuevo
        pkg_ok = self.env["stock.package"].create({"name": "PKG-OK-1"})
        packed_quant = self.env["stock.quant"].search([("package_id", "=", pkg_with_content.id)], limit=1)
        with self.assertRaises(ValidationError):
            pkg_ok.with_user(self.u_wms_op)._wms_pack_physical(packed_quant.id, 2.0)

        # 5. Ubicación no interna
        quant_cust = self._create_loose_quant(self.product_standard, self.location_customer, 10.0)
        with self.assertRaises(ValidationError):
            pkg_ok.with_user(self.u_wms_op)._wms_pack_physical(quant_cust.id, 2.0)

        # 6. Quant con reservas activas
        quant_res = self._create_loose_quant(self.product_standard, self.location_internal_1, 10.0)
        quant_res.sudo().write({"reserved_quantity": 3.0})
        with self.assertRaises(ValidationError):
            pkg_ok.with_user(self.u_wms_op)._wms_pack_physical(quant_res.id, 2.0)

        # 7. Cantidad solicitada excede disponibilidad
        with self.assertRaises(ValidationError):
            pkg_ok.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 15.0)

        # 8. Mismatch de ubicación entre paquete y quant
        loc_sub = self.env["stock.location"].create({
            "name": "Pack Loc Sub 1",
            "usage": "internal",
            "company_id": self.company_1.id,
        })
        pkg_loc_sub = self.env["stock.package"].create({"name": "PKG-LOC-SUB", "hu_state": "OPEN"})
        self.env["stock.quant"].with_company(self.company_1)._update_available_quantity(
            self.product_standard,
            loc_sub,
            1.0,
            package_id=pkg_loc_sub,
        )
        with self.assertRaises(ValidationError):
            pkg_loc_sub.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 1.0)

        # 9. Jerarquía anidada prohibida (HU top-level plana)
        pkg_parent = self.env["stock.package"].create({"name": "PKG-PARENT"})
        pkg_child = self.env["stock.package"].create({"name": "PKG-CHILD", "parent_package_id": pkg_parent.id})
        with self.assertRaises(ValidationError):
            pkg_child.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 1.0)
        with self.assertRaises(ValidationError):
            pkg_parent.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 1.0)

        # 10. Producto tracked por lote sin lote en quant
        quant_no_lot = self._create_loose_quant(self.product_tracked_lot, self.location_internal_1, 5.0)
        with self.assertRaises(ValidationError):
            pkg_ok.with_user(self.u_wms_op)._wms_pack_physical(quant_no_lot.id, 1.0)

        # 11. Producto tracked serial con cantidad distinta de 1.0 (aislado con qty=0.5 con 1.0 disponible)
        quant_serial = self._create_loose_quant(
            self.product_tracked_serial,
            self.location_internal_1,
            1.0,
            lot=self.lot_serial_1,
        )
        with self.assertRaises(ValidationError):
            pkg_ok.with_user(self.u_wms_op)._wms_pack_physical(quant_serial.id, 0.5)

    def test_hu_041_inventory_block_guard(self):
        """TEST-HU-041: Bloqueos de inventario (LOCATION, PRODUCT_LOCATION, LOT, PACKAGE) abortan el empaque."""
        package = self.env["stock.package"].create({"name": "PKG-HU-041"})
        quant_std = self._create_loose_quant(self.product_standard, self.location_internal_1, 10.0)
        quant_lot = self._create_loose_quant(
            self.product_tracked_lot, self.location_internal_1, 10.0, lot=self.lot_1
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
            package.with_user(self.u_wms_op)._wms_pack_physical(quant_std.id, 2.0)
        self.assertEqual(self.env["stock.move"].search_count([]), moves_before)
        b_loc.action_release()

        # 2. Bloqueo PRODUCT_LOCATION
        b_prod_loc = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "PRODUCT_LOCATION",
            "product_id": self.product_standard.id,
            "location_id": self.location_internal_1.id,
            "block_type": "INVESTIGATION",
            "reason": "Product location investigation",
        })
        with self.assertRaises(ValidationError):
            package.with_user(self.u_wms_op)._wms_pack_physical(quant_std.id, 2.0)
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
            package.with_user(self.u_wms_op)._wms_pack_physical(quant_lot.id, 2.0)
        self.assertEqual(self.env["stock.move"].search_count([]), moves_before)
        b_lot.action_release()

        # 4. Bloqueo PACKAGE sobre la HU destino
        b_pkg = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "PACKAGE",
            "package_id": package.id,
            "block_type": "HOLD",
            "reason": "Package hold",
        })
        with self.assertRaises(ValidationError):
            package.with_user(self.u_wms_op)._wms_pack_physical(quant_std.id, 2.0)
        self.assertEqual(self.env["stock.move"].search_count([]), moves_before)
        b_pkg.action_release()

        # 5. Sin bloqueos activos -> empaque exitoso
        res = package.with_user(self.u_wms_op)._wms_pack_physical(quant_std.id, 4.0)
        self.assertEqual(res["package_id"], package.id)
        self.assertEqual(package.hu_state, "OPEN")

    def test_hu_042_plm_hu_type_guard(self):
        """TEST-HU-042: Políticas de producto PLM (allowed_hu_type_ids) condicionan el tipo de paquete permitido."""
        quant = self._create_loose_quant(self.product_standard, self.location_internal_1, 10.0)

        # 1. Caso sin perfil PLM configurado -> PASS
        pkg_unrestricted = self.env["stock.package"].create({"name": "PKG-UNRESTRICTED"})
        res_unres = pkg_unrestricted.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 1.0)
        self.assertEqual(res_unres["package_id"], pkg_unrestricted.id)

        # Refrescar quant remanente (9.0 disponible)
        quant = self.env["stock.quant"].search([
            ("product_id", "=", self.product_standard.id),
            ("location_id", "=", self.location_internal_1.id),
            ("package_id", "=", False),
        ], limit=1)

        # 2. Caso con perfil PLM pero allowed_hu_type_ids vacío -> PASS
        plm_profile = self.env["wms.product.logistics"].create({
            "product_tmpl_id": self.product_standard.product_tmpl_id.id,
            "company_id": self.company_1.id,
            "allowed_hu_type_ids": [(5, 0, 0)],
        })
        pkg_unrestricted_2 = self.env["stock.package"].create({
            "name": "PKG-UNRESTRICTED-2",
            "package_type_id": self.pkg_type_pallet.id,
        })
        res_unres_2 = pkg_unrestricted_2.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 1.0)
        self.assertEqual(res_unres_2["package_id"], pkg_unrestricted_2.id)

        # Refrescar quant remanente (8.0 disponible)
        quant = self.env["stock.quant"].search([
            ("product_id", "=", self.product_standard.id),
            ("location_id", "=", self.location_internal_1.id),
            ("package_id", "=", False),
        ], limit=1)

        # 3. Configurar restricción a BOX en el perfil PLM
        plm_profile.write({
            "allowed_hu_type_ids": [(6, 0, [self.pkg_type_box.id])],
        })

        # 3a. Paquete sin tipo asignado -> falla
        pkg_no_type = self.env["stock.package"].create({"name": "PKG-NO-TYPE"})
        with self.assertRaises(ValidationError):
            pkg_no_type.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 2.0)

        # 3b. Paquete con tipo PALLET no permitido -> falla
        pkg_pallet = self.env["stock.package"].create({
            "name": "PKG-PALLET",
            "package_type_id": self.pkg_type_pallet.id,
        })
        with self.assertRaises(ValidationError):
            pkg_pallet.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 2.0)

        # 3c. Paquete con tipo BOX permitido -> pasa
        pkg_box = self.env["stock.package"].create({
            "name": "PKG-BOX",
            "package_type_id": self.pkg_type_box.id,
        })
        res = pkg_box.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 2.0)
        self.assertEqual(res["package_id"], pkg_box.id)

        # 4. Caso con default_hu_type_id configurado en PLM: Physical Pack NO lo auto-asigna a la HU
        plm_profile.write({
            "default_hu_type_id": self.pkg_type_box.id,
            "allowed_hu_type_ids": [(5, 0, 0)],
        })
        pkg_untyped_check = self.env["stock.package"].create({"name": "PKG-UNTYPED-CHECK"})
        self.assertFalse(pkg_untyped_check.package_type_id)
        # Refrescar quant remanente
        quant_rem_plm = self.env["stock.quant"].search([
            ("product_id", "=", self.product_standard.id),
            ("location_id", "=", self.location_internal_1.id),
            ("package_id", "=", False),
        ], limit=1)
        res_untyped = pkg_untyped_check.with_user(self.u_wms_op)._wms_pack_physical(quant_rem_plm.id, 1.0)
        self.assertEqual(res_untyped["package_id"], pkg_untyped_check.id)
        # El paquete sigue sin package_type_id (no auto-asignado por physical pack)
        self.assertFalse(pkg_untyped_check.package_type_id)

    def test_hu_043_rbac_company_and_privilege_boundary(self):
        """TEST-HU-043: Frontera de privilegios RBAC, narrow sudo y aislamiento multi-compañía."""
        package = self.env["stock.package"].create({"name": "PKG-HU-043"})
        quant = self._create_loose_quant(self.product_standard, self.location_internal_1, 10.0)

        # 1a. Operator ejecuta pack exitosamente a través del primitive (narrow sudo)
        res = package.with_user(self.u_wms_op)._wms_pack_physical(quant.id, 2.0)
        self.assertEqual(res["package_id"], package.id)

        # 1b. Supervisor ejecuta pack exitosamente
        pkg_sup = self.env["stock.package"].create({"name": "PKG-HU-043-SUP"})
        quant_sup = self._create_loose_quant(self.product_standard, self.location_internal_1, 5.0)
        res_sup = pkg_sup.with_user(self.u_wms_sup)._wms_pack_physical(quant_sup.id, 2.0)
        self.assertEqual(res_sup["package_id"], pkg_sup.id)
        self.assertEqual(pkg_sup.hu_state, "OPEN")

        # 1c. Manager ejecuta pack exitosamente
        pkg_mgr = self.env["stock.package"].create({"name": "PKG-HU-043-MGR"})
        quant_mgr = self._create_loose_quant(self.product_standard, self.location_internal_1, 5.0)
        res_mgr = pkg_mgr.with_user(self.u_wms_mgr)._wms_pack_physical(quant_mgr.id, 2.0)
        self.assertEqual(res_mgr["package_id"], pkg_mgr.id)
        self.assertEqual(pkg_mgr.hu_state, "OPEN")

        # 2. Operator intentando modificar directamente el paquete recibe AccessError
        with self.assertRaises(AccessError):
            package.with_user(self.u_wms_op).write({"hu_state": "CLOSED"})

        # 3. Plain internal user recibe AccessError
        with self.assertRaises(AccessError):
            package.with_user(self.u_plain)._wms_pack_physical(quant.id, 1.0)

        # 4. Pure stock user (sin rol WMS) recibe AccessError
        with self.assertRaises(AccessError):
            package.with_user(self.u_stock_usr)._wms_pack_physical(quant.id, 1.0)

        # 5. Operator de compañía 2 sobre quant de compañía 1 recibe AccessError
        with self.assertRaises(AccessError):
            package.with_user(self.u_cross_op)._wms_pack_physical(quant.id, 1.0)

        # 6. El evento de inventario debe registrar el ID del operador real
        event = self.env["wms.inventory.event"].search([
            ("correlation_id", "=", res["correlation_id"]),
        ], limit=1)
        self.assertEqual(event.operator_id, self.u_wms_op)
