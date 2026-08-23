import math
import threading
import time
from unittest.mock import patch

from odoo import api
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools.misc import mute_logger


class TestPhysicalSplit(TransactionCase):
    """Suite de pruebas unitarias para HU-004C — Physical Split Core (TEST-HU-055 a TEST-HU-066).

    Verifica el primitive transaccional _wms_split_physical() en stock.package,
    garantizando la transferencia física paquete a paquete vía stock.move, la preservación
    de la fuente en estado OPEN, la transición del destino a OPEN, la persistencia atómica
    de 2 eventos de inventario (UNPACK en fuente, PACK en destino) y 1 mensaje outbox
    (inventory.hu.split con 10 claves canónicas) bajo un mismo correlation_id (ADR-019),
    guards operacionales, bloqueos de inventario, PLM destination admission, fronteras RBAC,
    direct CRUD boundary y concurrencia pesimista multi-thread con serialización determinista.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_1 = cls.env["res.company"].create({"name": "HU Split Test Company 1"})
        cls.company_2 = cls.env["res.company"].create({"name": "HU Split Test Company 2"})

        cls.warehouse_1 = cls.env["stock.warehouse"].search([
            ("company_id", "=", cls.company_1.id),
        ], limit=1)
        if not cls.warehouse_1:
            cls.warehouse_1 = cls.env["stock.warehouse"].create({
                "name": "Warehouse Split 1",
                "code": "WHSP1",
                "company_id": cls.company_1.id,
            })

        cls.location_internal_1 = cls.warehouse_1.lot_stock_id
        cls.location_internal_2 = cls.env["stock.location"].create({
            "name": "Split Shelf 2",
            "usage": "internal",
            "location_id": cls.location_internal_1.id,
            "company_id": cls.company_1.id,
        })
        cls.location_customer = cls.env.ref("stock.stock_location_customers")

        # Productos
        cls.product_standard = cls.env["product.product"].create({
            "name": "Standard Split Product",
            "is_storable": True,
            "tracking": "none",
            "company_id": False,
        })

        cls.product_standard_2 = cls.env["product.product"].create({
            "name": "Standard Split Product 2",
            "is_storable": True,
            "tracking": "none",
            "company_id": False,
        })

        cls.product_lot = cls.env["product.product"].create({
            "name": "Lot Tracked Split Product",
            "is_storable": True,
            "tracking": "lot",
            "company_id": False,
        })

        cls.product_serial = cls.env["product.product"].create({
            "name": "Serial Tracked Split Product",
            "is_storable": True,
            "tracking": "serial",
            "company_id": False,
        })

        # Lotes
        cls.lot_1 = cls.env["stock.lot"].create({
            "name": "LOT-SPLIT-001",
            "product_id": cls.product_lot.id,
            "company_id": cls.company_1.id,
        })
        cls.serial_1 = cls.env["stock.lot"].create({
            "name": "SN-SPLIT-001",
            "product_id": cls.product_serial.id,
            "company_id": cls.company_1.id,
        })

        # Partner
        cls.partner_owner = cls.env["res.partner"].create({
            "name": "Split Inventory Owner",
            "company_id": False,
        })

        # Package Types
        cls.package_type_box = cls.env["stock.package.type"].create({
            "name": "Box Type Split",
            "company_id": False,
        })
        cls.package_type_pallet = cls.env["stock.package.type"].create({
            "name": "Pallet Type Split",
            "company_id": False,
        })
        cls.package_type_c2 = cls.env["stock.package.type"].create({
            "name": "Company 2 Box Type",
            "company_id": cls.company_2.id,
        })

        # Usuarios de prueba RBAC
        group_internal = cls.env.ref("base.group_user")
        group_wms_op = cls.env.ref("wms_core.group_wms_operator")
        group_wms_sup = cls.env.ref("wms_core.group_wms_supervisor")
        group_wms_mgr = cls.env.ref("wms_core.group_wms_manager")
        group_stock_usr = cls.env.ref("stock.group_stock_user")

        cls.u_wms_op = cls.env["res.users"].create({
            "name": "u_hu_split_op",
            "login": "u_hu_split_op",
            "email": "hu_split_op@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_op.id])],
        })

        cls.u_wms_sup = cls.env["res.users"].create({
            "name": "u_hu_split_sup",
            "login": "u_hu_split_sup",
            "email": "hu_split_sup@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_sup.id])],
        })

        cls.u_wms_mgr = cls.env["res.users"].create({
            "name": "u_hu_split_mgr",
            "login": "u_hu_split_mgr",
            "email": "hu_split_mgr@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_mgr.id])],
        })

        cls.u_stock_usr = cls.env["res.users"].create({
            "name": "u_hu_split_stock_usr",
            "login": "u_hu_split_stock_usr",
            "email": "hu_split_stock_usr@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_stock_usr.id])],
        })

        cls.u_plain = cls.env["res.users"].create({
            "name": "u_hu_split_plain",
            "login": "u_hu_split_plain",
            "email": "hu_split_plain@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id])],
        })

        cls.u_cross_op = cls.env["res.users"].create({
            "name": "u_hu_split_cross_op",
            "login": "u_hu_split_cross_op",
            "email": "hu_split_cross_op@test.com",
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

    def _create_loose_quant(self, product, location, qty, lot=False, company=None):
        """Helper para crear inventario suelto usando _update_available_quantity nativo."""
        comp = company or self.company_1
        self.env["stock.quant"].with_company(comp)._update_available_quantity(
            product,
            location,
            qty,
            lot_id=lot or None,
            package_id=None,
        )
        quant = self.env["stock.quant"].search([
            ("product_id", "=", product.id),
            ("location_id", "=", location.id),
            ("lot_id", "=", lot.id if lot else False),
            ("company_id", "=", comp.id),
            ("package_id", "=", False),
        ], limit=1)
        return quant

    def test_hu_055_physical_split_api_contract(self):
        """TEST-HU-055: Validación estricta de firma de API, tipos de argumentos, singleton y correlation normalizado."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-055-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-055-DST", "hu_state": "EMPTY"})
        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, pkg_source)

        # 1. ensure_one()
        empty_pkg = self.env["stock.package"].browse()
        with self.assertRaises(ValueError):
            empty_pkg.with_user(self.u_wms_op)._wms_split_physical(quant.id, 4.0, pkg_dest.id)

        multi_pkg = pkg_source | self.env["stock.package"].create({"name": "PKG-HU-055-SRC2", "hu_state": "OPEN"})
        with self.assertRaises(ValueError):
            multi_pkg.with_user(self.u_wms_op)._wms_split_physical(quant.id, 4.0, pkg_dest.id)

        # 2. quant_id inválido
        for bad_quant_id in [False, True, 0, -1, "123", None]:
            with self.assertRaises(ValidationError):
                pkg_source.with_user(self.u_wms_op)._wms_split_physical(bad_quant_id, 4.0, pkg_dest.id)

        # 3. quantity inválida
        for bad_qty in [False, True, 0, 0.0, -1.0, float("nan"), float("inf"), float("-inf"), None]:
            with self.assertRaises(ValidationError):
                pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, bad_qty, pkg_dest.id)

        # 4. destination_package_id inválido
        for bad_dst_id in [False, True, 0, -1, "456", None]:
            with self.assertRaises(ValidationError):
                pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 4.0, bad_dst_id)

        # 5. source_package == destination_package (rechazo de misma HU)
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 4.0, pkg_source.id)

        # 6. correlation_id inválido
        for bad_corr in ["", "   "]:
            with self.assertRaises(ValidationError):
                pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 4.0, pkg_dest.id, correlation_id=bad_corr)

        # 7. Ejecución válida y estructura exacta de retorno
        res = pkg_source.with_user(self.u_wms_op)._wms_split_physical(
            quant.id, 4.0, pkg_dest.id, correlation_id="  CORR-HU-055  "
        )
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("source_package_id"), pkg_source.id)
        self.assertEqual(res.get("destination_package_id"), pkg_dest.id)
        self.assertEqual(res.get("correlation_id"), "CORR-HU-055")

    def test_hu_056_partial_split_native_move_and_history(self):
        """TEST-HU-056: Split parcial paquete a paquete, move nativo, conservación física e historial de destino."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-056-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-056-DST", "hu_state": "EMPTY"})
        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, pkg_source)

        init_moves_count = self.env["stock.move"].search_count([])
        init_history_count = self.env["stock.package.history"].search_count([])

        res = pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 4.0, pkg_dest.id)
        self.assertEqual(res["source_package_id"], pkg_source.id)
        self.assertEqual(res["destination_package_id"], pkg_dest.id)

        # 1. Exactamente un stock.move creado y confirmado
        moves = self.env["stock.move"].search([], order="id desc", limit=1)
        self.assertEqual(self.env["stock.move"].search_count([]), init_moves_count + 1)
        self.assertEqual(moves.state, "done")
        self.assertEqual(moves.is_inventory, True)
        self.assertEqual(moves.location_id, self.location_internal_1)
        self.assertEqual(moves.location_dest_id, self.location_internal_1)

        # 2. Exactamente una stock.move.line con package_id=source y result_package_id=destination
        lines = moves.move_line_ids
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.package_id, pkg_source)
        self.assertEqual(lines.result_package_id, pkg_dest)
        self.assertEqual(lines.quantity, 4.0)

        # 3. Conservación de masa e inventario
        self.assertEqual(pkg_source.contained_quant_ids.quantity, 6.0)
        self.assertEqual(pkg_dest.contained_quant_ids.quantity, 4.0)
        self.assertEqual(
            pkg_source.contained_quant_ids.quantity + pkg_dest.contained_quant_ids.quantity,
            10.0,
        )

        # 4. Historial nativo: exactamente un nuevo registro para el paquete destino
        self.assertEqual(self.env["stock.package.history"].search_count([]), init_history_count + 1)
        new_histories = self.env["stock.package.history"].search([("package_id", "=", pkg_dest.id)])
        self.assertEqual(len(new_histories), 1)

    def test_hu_057_lifecycle_and_metadata_preservation(self):
        """TEST-HU-057: Ciclo de vida OPEN->OPEN, EMPTY->OPEN, metadata intacta, transferir quant completo y prohibir vaciado."""
        pkg_source = self.env["stock.package"].create({
            "name": "PKG-HU-057-SRC",
            "hu_state": "OPEN",
            "hu_class": "PALLET",
        })
        pkg_dest_1 = self.env["stock.package"].create({
            "name": "PKG-HU-057-DST1",
            "hu_state": "EMPTY",
            "hu_class": "CASE",
            "package_type_id": self.package_type_box.id,
        })
        pkg_dest_2 = self.env["stock.package"].create({
            "name": "PKG-HU-057-DST2",
            "hu_state": False,  # Sin inicializar
            "hu_class": "TOTE",
        })

        quant_a = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, pkg_source)
        quant_b = self._create_packed_quant(self.product_standard_2, self.location_internal_1, 5.0, pkg_source)

        # 1. Transferir todo quant_a (10.0) hacia pkg_dest_1 (permanece quant_b en source -> VÁLIDO)
        pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant_a.id, 10.0, pkg_dest_1.id)

        self.assertEqual(pkg_source.hu_state, "OPEN")
        self.assertEqual(pkg_source.hu_class, "PALLET")
        self.assertEqual(pkg_dest_1.hu_state, "OPEN")
        self.assertEqual(pkg_dest_1.hu_class, "CASE")
        self.assertEqual(pkg_dest_1.package_type_id, self.package_type_box)
        self.assertEqual(pkg_dest_1.contained_quant_ids.quantity, 10.0)

        # 2. Ahora quant_b (5.0) es el único quant en source. Intentar transferir los 5.0 completos vaciaría la fuente
        with self.assertRaises(ValidationError) as ctx:
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant_b.id, 5.0, pkg_dest_2.id)
        self.assertIn("vaciar completamente", str(ctx.exception).lower())

        # 3. Transferir 2.0 de quant_b hacia pkg_dest_2 (quedan 3.0 en source -> VÁLIDO)
        pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant_b.id, 2.0, pkg_dest_2.id)
        self.assertEqual(pkg_source.hu_state, "OPEN")
        self.assertEqual(pkg_source.contained_quant_ids.quantity, 3.0)
        self.assertEqual(pkg_dest_2.hu_state, "OPEN")
        self.assertEqual(pkg_dest_2.contained_quant_ids.quantity, 2.0)

    def test_hu_058_split_event_outbox_contract(self):
        """TEST-HU-058: Contrato estricto de Journal (2 eventos) y Outbox (1 mensaje con 10 claves canónicas)."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-058-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-058-DST", "hu_state": "EMPTY"})
        quant = self._create_packed_quant(
            self.product_lot,
            self.location_internal_1,
            8.0,
            pkg_source,
            lot=self.lot_1,
            owner=self.partner_owner,
        )

        res = pkg_source.with_user(self.u_wms_op)._wms_split_physical(
            quant.id,
            3.0,
            pkg_dest.id,
            correlation_id="CORR-SPLIT-058-EXACT",
        )

        # 1. Verificar exactamente 2 eventos creados
        events = self.env["wms.inventory.event"].search([
            ("correlation_id", "=", "CORR-SPLIT-058-EXACT"),
        ], order="id asc")
        self.assertEqual(len(events), 2)

        ev_unpack, ev_pack = events[0], events[1]
        self.assertEqual(ev_unpack.event_type, "UNPACK")
        self.assertEqual(ev_unpack.package_id, pkg_source)
        self.assertEqual(ev_unpack.quantity, 3.0)
        self.assertEqual(ev_unpack.product_id, self.product_lot)
        self.assertEqual(ev_unpack.lot_id, self.lot_1)
        self.assertEqual(ev_unpack.owner_id, self.partner_owner)
        self.assertEqual(ev_unpack.operator_id, self.u_wms_op)

        self.assertEqual(ev_pack.event_type, "PACK")
        self.assertEqual(ev_pack.package_id, pkg_dest)
        self.assertEqual(ev_pack.quantity, 3.0)
        self.assertEqual(ev_pack.product_id, self.product_lot)
        self.assertEqual(ev_pack.lot_id, self.lot_1)
        self.assertEqual(ev_pack.owner_id, self.partner_owner)
        self.assertEqual(ev_pack.operator_id, self.u_wms_op)

        # 2. Verificar exactamente 1 mensaje Outbox
        outbox = self.env["wms.outbox"].search([
            ("correlation_id", "=", "CORR-SPLIT-058-EXACT"),
        ])
        self.assertEqual(len(outbox), 1)
        self.assertEqual(outbox.event_name, "inventory.hu.split")
        self.assertEqual(outbox.schema_version, 1)

        expected_keys = {
            "source_package_id",
            "source_package_ref",
            "destination_package_id",
            "destination_package_ref",
            "product_id",
            "lot_id",
            "owner_id",
            "location_id",
            "quantity",
            "uom_id",
        }
        self.assertEqual(set(outbox.payload.keys()), expected_keys)
        self.assertEqual(outbox.payload["source_package_id"], pkg_source.id)
        self.assertEqual(outbox.payload["source_package_ref"], pkg_source.name)
        self.assertEqual(outbox.payload["destination_package_id"], pkg_dest.id)
        self.assertEqual(outbox.payload["destination_package_ref"], pkg_dest.name)
        self.assertEqual(outbox.payload["product_id"], self.product_lot.id)
        self.assertEqual(outbox.payload["lot_id"], self.lot_1.id)
        self.assertEqual(outbox.payload["owner_id"], self.partner_owner.id)
        self.assertEqual(outbox.payload["location_id"], self.location_internal_1.id)
        self.assertEqual(outbox.payload["quantity"], 3.0)
        self.assertEqual(outbox.payload["uom_id"], self.product_lot.uom_id.id)

    def test_hu_059_split_atomic_rollback_on_outbox_failure(self):
        """TEST-HU-059: Atomicidad ADR-019, rollback total ante fallo simulado en outbox."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-059-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-059-DST", "hu_state": "EMPTY"})
        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, pkg_source)

        init_events_count = self.env["wms.inventory.event"].search_count([])
        init_outbox_count = self.env["wms.outbox"].search_count([])
        init_moves_count = self.env["stock.move"].search_count([])
        init_hist_count = self.env["stock.package.history"].search_count([("package_id", "=", pkg_dest.id)])

        with patch(
            "odoo.addons.wms_inventory.models.inventory_event.WmsInventoryEvent._append_events_with_outbox",
            side_effect=RuntimeError("Simulated Outbox Failure"),
        ):
            with self.assertRaises(RuntimeError):
                pkg_source.with_user(self.u_wms_op)._wms_split_physical(
                    quant.id, 4.0, pkg_dest.id, correlation_id="CORR-ROLLBACK-059"
                )

        pkg_source.invalidate_recordset()
        pkg_dest.invalidate_recordset()
        self.assertEqual(pkg_source.contained_quant_ids.quantity, 10.0)
        self.assertEqual(pkg_dest.hu_state, "EMPTY")
        self.assertFalse(pkg_dest.contained_quant_ids)

        self.assertEqual(self.env["stock.move"].search_count([]), init_moves_count)
        self.assertEqual(self.env["wms.inventory.event"].search_count([]), init_events_count)
        self.assertEqual(self.env["wms.outbox"].search_count([]), init_outbox_count)
        self.assertEqual(self.env["stock.package.history"].search_count([("package_id", "=", pkg_dest.id)]), init_hist_count)

    def test_hu_060_split_scope_and_lifecycle_guards(self):
        """TEST-HU-060: Rechazo de estados no OPEN en fuente, destino no EMPTY/False, destino con contenido, anidamiento y quants ajenos."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-060-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-060-DST", "hu_state": "EMPTY"})
        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, pkg_source)

        # 1. Estados no permitidos en fuente
        for bad_src_state in ["EMPTY", False, "CLOSED", "IN_TRANSIT", "SHIPPED", "RETURNED", "DISPOSED"]:
            pkg_bad_src = self.env["stock.package"].create({"name": f"PKG-BAD-SRC-{bad_src_state}", "hu_state": bad_src_state})
            q_bad = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, pkg_bad_src)
            with self.assertRaises(ValidationError):
                pkg_bad_src.with_user(self.u_wms_op)._wms_split_physical(q_bad.id, 2.0, pkg_dest.id)

        # 2. Estados no permitidos en destino (debe ser False o EMPTY)
        for bad_dst_state in ["OPEN", "CLOSED", "IN_TRANSIT", "SHIPPED", "RETURNED", "DISPOSED"]:
            pkg_bad_dst = self.env["stock.package"].create({"name": f"PKG-BAD-DST-{bad_dst_state}", "hu_state": bad_dst_state})
            with self.assertRaises(ValidationError):
                pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_bad_dst.id)

        # 3. Destino con contenido físico previo
        pkg_dest_with_content = self.env["stock.package"].create({"name": "PKG-DST-CONTENT", "hu_state": "EMPTY"})
        self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_dest_with_content)
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest_with_content.id)

        # 4. Anidamiento (nesting) en fuente o destino
        parent_pkg = self.env["stock.package"].create({"name": "PKG-PARENT", "hu_state": "OPEN"})
        pkg_source.write({"parent_package_id": parent_pkg.id})
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)
        pkg_source.write({"parent_package_id": False})

        pkg_dest.write({"parent_package_id": parent_pkg.id})
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)
        pkg_dest.write({"parent_package_id": False})

        # 5. Fuente OPEN pero vacía físicamente (sin quants)
        pkg_empty_open_src = self.env["stock.package"].create({"name": "PKG-EMPTY-OPEN-SRC", "hu_state": "OPEN"})
        with self.assertRaises(ValidationError):
            pkg_empty_open_src.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)

        # 6. Quant empaquetado en otra HU (no perteneciente a la fuente)
        pkg_other = self.env["stock.package"].create({"name": "PKG-OTHER-SRC", "hu_state": "OPEN"})
        quant_other = self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_other)
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant_other.id, 2.0, pkg_dest.id)

        # 7. Quant ajeno o suelto
        quant_loose = self._create_loose_quant(self.product_standard, self.location_internal_1, 5.0)
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant_loose.id, 2.0, pkg_dest.id)

    def test_hu_061_split_company_and_location_guards(self):
        """TEST-HU-061: Guards de ubicación interna, multi-compañía, adopción de compañía y tipos de paquete cross-company."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-061-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-061-DST", "hu_state": "EMPTY"})
        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, pkg_source)

        # 1. Ubicación no interna (ej. customer)
        self.env.cr.execute("UPDATE stock_quant SET location_id = %s WHERE id = %s", [self.location_customer.id, quant.id])
        quant.invalidate_recordset(["location_id"])
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)
        self.env.cr.execute("UPDATE stock_quant SET location_id = %s WHERE id = %s", [self.location_internal_1.id, quant.id])
        quant.invalidate_recordset(["location_id"])

        # 2. Package destination con compañía distinta
        pkg_dest.write({"company_id": self.company_2.id})
        with self.assertRaises(AccessError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)
        pkg_dest.write({"company_id": False})  # Global/unassigned -> adopta

        # 3. Tipo de paquete de destino con compañía distinta
        pkg_dest.write({"package_type_id": self.package_type_c2.id})
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)
        pkg_dest.write({"package_type_id": False})

        # 4. Operador sin acceso a la compañía del inventario origen recibe AccessError
        with self.assertRaises(AccessError):
            pkg_source.with_user(self.u_cross_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)

        # 5. Destino sin compañía (False) ejecuta split válido y adopta la compañía del quant
        pkg_dest_global = self.env["stock.package"].create({"name": "PKG-DST-GLOBAL", "hu_state": "EMPTY", "company_id": False})
        res_adopt = pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest_global.id)
        self.assertEqual(res_adopt["destination_package_id"], pkg_dest_global.id)
        self.assertEqual(pkg_dest_global.hu_state, "OPEN")
        self.assertEqual(pkg_dest_global.contained_quant_ids.company_id, self.company_1)

    def test_hu_062_split_reservations_tracking_uom_guards(self):
        """TEST-HU-062: Guards de reservas activas (zero reservations), cantidad disponible y trazabilidad lote/serie."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-062-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-062-DST", "hu_state": "EMPTY"})
        quant_std = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, pkg_source)

        # 1. Reserva activa en el quant (cualquier reserva debe bloquear)
        self.env.cr.execute("UPDATE stock_quant SET reserved_quantity = 2.0 WHERE id = %s", [quant_std.id])
        quant_std.invalidate_recordset(["reserved_quantity"])
        with self.assertRaises(ValidationError) as ctx:
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant_std.id, 3.0, pkg_dest.id)
        self.assertIn("reservas activas", str(ctx.exception).lower())
        self.env.cr.execute("UPDATE stock_quant SET reserved_quantity = 0.0 WHERE id = %s", [quant_std.id])
        quant_std.invalidate_recordset(["reserved_quantity"])

        # 2. Cantidad superior a la disponible
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant_std.id, 15.0, pkg_dest.id)

        # 3. Producto trazado por lote sin lote asignado
        pkg_lot_bad = self.env["stock.package"].create({"name": "PKG-LOT-BAD", "hu_state": "OPEN"})
        quant_no_lot = self._create_packed_quant(self.product_lot, self.location_internal_1, 10.0, pkg_lot_bad, lot=False)
        with self.assertRaises(ValidationError):
            pkg_lot_bad.with_user(self.u_wms_op)._wms_split_physical(quant_no_lot.id, 2.0, pkg_dest.id)

        # 4. Producto trazado por serie con cantidad distinta de 1.0
        pkg_sn = self.env["stock.package"].create({"name": "PKG-SN", "hu_state": "OPEN"})
        quant_sn = self._create_packed_quant(self.product_serial, self.location_internal_1, 1.0, pkg_sn, lot=self.serial_1)
        with self.assertRaises(ValidationError):
            pkg_sn.with_user(self.u_wms_op)._wms_split_physical(quant_sn.id, 2.0, pkg_dest.id)

    def test_hu_063_inventory_block_guards(self):
        """TEST-HU-063: Bloqueos de inventario (wms.inventory.block) en los 5 scopes sobre source y PACKAGE sobre destination."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-063-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-063-DST", "hu_state": "EMPTY"})
        quant = self._create_packed_quant(
            self.product_lot,
            self.location_internal_1,
            10.0,
            pkg_source,
            lot=self.lot_1,
            owner=self.partner_owner,
        )

        # 1. Bloqueo en LOCATION
        b_loc = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "LOCATION",
            "location_id": self.location_internal_1.id,
            "block_type": "HOLD",
            "reason": "Location hold split test",
        })
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)
        b_loc.action_release()

        # 2. Bloqueo en PACKAGE de la fuente
        b_pkg_src = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "PACKAGE",
            "package_id": pkg_source.id,
            "block_type": "HOLD",
            "reason": "Package source hold split test",
        })
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)
        b_pkg_src.action_release()

        # 3. Bloqueo en PACKAGE del destino
        b_pkg_dst = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "PACKAGE",
            "package_id": pkg_dest.id,
            "block_type": "HOLD",
            "reason": "Package dest hold split test",
        })
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)
        b_pkg_dst.action_release()

        # 4. Bloqueo en LOT
        b_lot = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "LOT",
            "product_id": self.product_lot.id,
            "lot_id": self.lot_1.id,
            "block_type": "HOLD",
            "reason": "Lot hold split test",
        })
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)
        b_lot.action_release()

        # 5. Bloqueo en PRODUCT_LOCATION
        b_prod_loc = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "PRODUCT_LOCATION",
            "product_id": self.product_lot.id,
            "location_id": self.location_internal_1.id,
            "block_type": "HOLD",
            "reason": "Product location hold split test",
        })
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)
        b_prod_loc.action_release()

        # 6. Bloqueo en OWNER_LOCATION
        b_owner_loc = self.env["wms.inventory.block"].create({
            "company_id": self.company_1.id,
            "block_scope": "OWNER_LOCATION",
            "owner_id": self.partner_owner.id,
            "location_id": self.location_internal_1.id,
            "block_type": "HOLD",
            "reason": "Owner location hold split test",
        })
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest.id)
        b_owner_loc.action_release()

    def test_hu_064_plm_destination_admission_guard(self):
        """TEST-HU-064: Restricciones PLM (allowed_hu_type_ids) aplicadas exclusivamente a la Handling Unit destino."""
        # Configurar perfil logístico para product_standard restringiendo a package_type_box
        plm_profile = self.env["wms.product.logistics"].create({
            "product_tmpl_id": self.product_standard.product_tmpl_id.id,
            "company_id": self.company_1.id,
            "allowed_hu_type_ids": [(6, 0, [self.package_type_box.id])],
            "default_hu_type_id": self.package_type_box.id,
        })

        # Fuente con tipo pallet (no permitido por PLM para el producto, pero source no se reevalúa)
        pkg_source = self.env["stock.package"].create({
            "name": "PKG-HU-064-SRC",
            "hu_state": "OPEN",
            "package_type_id": self.package_type_pallet.id,
        })
        pkg_dest_bad = self.env["stock.package"].create({
            "name": "PKG-HU-064-DST-BAD",
            "hu_state": "EMPTY",
            "package_type_id": self.package_type_pallet.id,
        })
        pkg_dest_ok = self.env["stock.package"].create({
            "name": "PKG-HU-064-DST-OK",
            "hu_state": "EMPTY",
            "package_type_id": self.package_type_box.id,
        })

        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, pkg_source)

        # 1. Destino con tipo pallet (no permitido) -> ValidationError
        with self.assertRaises(ValidationError) as ctx:
            pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 3.0, pkg_dest_bad.id)
        self.assertIn("no está permitido para el producto", str(ctx.exception))

        # 2. Destino con tipo box (permitido) -> PASS
        res = pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 3.0, pkg_dest_ok.id)
        self.assertEqual(res["destination_package_id"], pkg_dest_ok.id)
        self.assertEqual(pkg_dest_ok.contained_quant_ids.quantity, 3.0)

        # 3. Fuente conserva su package_type_id intacto
        self.assertEqual(pkg_source.package_type_id, self.package_type_pallet)

        # 4. Producto sin allowlist restrictiva en PLM (allowed_hu_type_ids vacía) -> admite cualquier tipo de paquete
        plm_profile.write({"allowed_hu_type_ids": [(5, 0, 0)]})
        pkg_dest_any = self.env["stock.package"].create({
            "name": "PKG-HU-064-DST-ANY",
            "hu_state": "EMPTY",
            "package_type_id": self.package_type_pallet.id,
        })
        res_any = pkg_source.with_user(self.u_wms_op)._wms_split_physical(quant.id, 2.0, pkg_dest_any.id)
        self.assertEqual(res_any["destination_package_id"], pkg_dest_any.id)
        self.assertEqual(pkg_dest_any.contained_quant_ids.quantity, 2.0)

    def test_hu_065_rbac_direct_crud_and_narrow_sudo(self):
        """TEST-HU-065: Matriz RBAC, rechazo de Direct CRUD para operador WMS y preservación de operator_id real."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-065-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-065-DST", "hu_state": "EMPTY"})
        quant = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, pkg_source)

        # 1. Usuarios autorizados (Operator, Supervisor, Manager, System Admin)
        u_admin = self.env.ref("base.user_admin")
        u_admin.sudo().write({"company_ids": [(4, self.company_1.id)], "company_id": self.company_1.id})
        auth_users = [self.u_wms_op, self.u_wms_sup, self.u_wms_mgr, u_admin]
        user_executions = []
        for user in auth_users:
            dest_temp = self.env["stock.package"].create({"name": f"PKG-DST-{user.login}", "hu_state": "EMPTY"})
            corr_id = f"CORR-RBAC-065-{user.login}"
            res = pkg_source.with_user(user).with_company(self.company_1)._wms_split_physical(
                quant.id, 1.0, dest_temp.id, correlation_id=corr_id
            )
            self.assertEqual(res["source_package_id"], pkg_source.id)
            self.assertEqual(res["destination_package_id"], dest_temp.id)
            self.assertEqual(res["correlation_id"], corr_id)
            user_executions.append((user, dest_temp, corr_id))

        # 2. Direct CRUD denegado a Operator en stock.package.hu_state y stock.quant
        with self.assertRaises(AccessError):
            pkg_source.with_user(self.u_wms_op).write({"hu_state": "CLOSED"})

        with self.assertRaises(AccessError):
            quant.with_user(self.u_wms_op).write({"package_id": False})

        # 3. Usuarios denegados (Plain internal y Stock user sin WMS)
        pkg_dest_deny = self.env["stock.package"].create({"name": "PKG-DST-DENY", "hu_state": "EMPTY"})
        with self.assertRaises(AccessError):
            pkg_source.with_user(self.u_plain)._wms_split_physical(quant.id, 1.0, pkg_dest_deny.id)

        with self.assertRaises(AccessError):
            pkg_source.with_user(self.u_stock_usr)._wms_split_physical(quant.id, 1.0, pkg_dest_deny.id)

        # 4. Operador real registrado por ejecución (demostrar atribución exacta de cada split)
        for user, dest_temp, corr_id in user_executions:
            user_events = self.env["wms.inventory.event"].search([
                ("correlation_id", "=", corr_id),
            ])
            self.assertEqual(len(user_events), 2, f"Deben existir exactamente 2 eventos para {user.login}")
            self.assertEqual(set(user_events.mapped("event_type")), {"UNPACK", "PACK"})
            for ev in user_events:
                self.assertEqual(ev.operator_id, user, f"El evento {ev.id} ({ev.event_type}) debe estar atribuido a {user.login}")
                self.assertEqual(ev.company_id, self.company_1)

    @mute_logger("odoo.sql_db")
    def test_hu_066_concurrency_deterministic_serialization(self):
        """TEST-HU-066: Concurrencia pesimista multi-thread, contención de locks en PostgreSQL y serialización determinista."""
        # =========================================================================
        # Escenario A: Dos transacciones sobre el MISMO source, quant y destination
        # =========================================================================
        with self.env.registry.cursor() as cr_setup:
            env_setup = api.Environment(cr_setup, 1, {})
            prod_a = env_setup["product.product"].create({
                "name": "Product Concurrency Split A",
                "is_storable": True,
            })
            loc_parent_a = env_setup.ref("stock.stock_location_stock").location_id
            loc_a = env_setup["stock.location"].create({
                "name": "LOC-CONC-SPLIT-A",
                "usage": "internal",
                "location_id": loc_parent_a.id if loc_parent_a else False,
            })
            pkg_src_a = env_setup["stock.package"].create({
                "name": "PKG-HU-066-SRC-A",
                "hu_state": "OPEN",
            })
            pkg_dst_a = env_setup["stock.package"].create({
                "name": "PKG-HU-066-DST-A",
                "hu_state": "EMPTY",
            })
            env_setup["stock.quant"]._update_available_quantity(
                prod_a,
                loc_a,
                10.0,
                package_id=pkg_src_a,
            )
            quant_a = env_setup["stock.quant"].search([
                ("product_id", "=", prod_a.id),
                ("package_id", "=", pkg_src_a.id),
            ], limit=1)

            src_a_id = pkg_src_a.id
            dst_a_id = pkg_dst_a.id
            quant_a_id = quant_a.id
            prod_a_id = prod_a.id
            tmpl_a_id = prod_a.product_tmpl_id.id
            loc_a_id = loc_a.id
            cr_setup.commit()

        cr2_a = self.env.registry.cursor()
        env2_a = api.Environment(cr2_a, 1, {})
        pkg2_a = env2_a["stock.package"].browse(src_a_id)

        try:
            barrier_t1_locked_a = threading.Event()
            barrier_t2_calling_a = threading.Event()
            t2_a_result = {}

            def thread_2_worker_a():
                try:
                    barrier_t1_locked_a.wait(timeout=10.0)
                    barrier_t2_calling_a.set()
                    try:
                        pkg2_a._wms_split_physical(quant_a_id, 5.0, dst_a_id, correlation_id="CORR-SPLIT-A-TH2")
                        cr2_a.commit()
                        t2_a_result["success"] = True
                    except Exception as exc:
                        cr2_a.rollback()
                        t2_a_result["error_class"] = type(exc).__name__
                        t2_a_result["error_msg"] = str(exc)
                        t2_a_result["is_serialization_failure"] = (
                            type(exc).__name__ == "SerializationFailure"
                            or "could not serialize access" in str(exc)
                        )
                except BaseException as exc:
                    barrier_t2_calling_a.set()
                    t2_a_result["outer_error"] = str(exc)
                finally:
                    cr2_a.close()

            t2_a = threading.Thread(target=thread_2_worker_a)
            t2_a.start()

            with self.env.registry.cursor() as cr1_a:
                env1_a = api.Environment(cr1_a, 1, {})
                pkg1_a = env1_a["stock.package"].browse(src_a_id)
                res1_a = pkg1_a._wms_split_physical(quant_a_id, 4.0, dst_a_id, correlation_id="CORR-SPLIT-A-TH1")
                self.assertEqual(res1_a.get("source_package_id"), src_a_id)
                self.assertEqual(res1_a.get("destination_package_id"), dst_a_id)

                barrier_t1_locked_a.set()
                self.assertTrue(barrier_t2_calling_a.wait(timeout=5.0), f"T2-A debió invocar el primitive: {t2_a_result}")
                time.sleep(0.4)

                cr1_a.execute('''
                    SELECT COUNT(*)
                    FROM pg_locks l
                    WHERE NOT l.granted AND l.locktype = 'transactionid'
                ''')
                waiting_locks_a = cr1_a.fetchone()[0]
                self.assertGreaterEqual(waiting_locks_a, 1, "T2-A debe estar bloqueada en PostgreSQL esperando el lock de T1-A")

                cr1_a.commit()

            t2_a.join(timeout=10.0)
            self.assertFalse(t2_a.is_alive(), "T2-A thread debió terminar")

            self.assertFalse(t2_a_result.get("success"), "T2-A no debió tener éxito tras la mutación concurrente de T1-A")
            self.assertTrue(
                t2_a_result.get("is_serialization_failure"),
                f"T2-A debió recibir SerializationFailure exacto: {t2_a_result}",
            )

            with self.env.registry.cursor() as cr_check_a:
                env_check_a = api.Environment(cr_check_a, 1, {})
                pkg_src_chk_a = env_check_a["stock.package"].browse(src_a_id)
                pkg_dst_chk_a = env_check_a["stock.package"].browse(dst_a_id)

                self.assertEqual(pkg_src_chk_a.hu_state, "OPEN")
                self.assertEqual(pkg_src_chk_a.contained_quant_ids.quantity, 6.0)
                self.assertEqual(pkg_dst_chk_a.hu_state, "OPEN")
                self.assertEqual(pkg_dst_chk_a.contained_quant_ids.quantity, 4.0)
                self.assertEqual(
                    pkg_src_chk_a.contained_quant_ids.quantity + pkg_dst_chk_a.contained_quant_ids.quantity,
                    10.0,
                )

                events_a = env_check_a["wms.inventory.event"].search([
                    ("correlation_id", "in", ["CORR-SPLIT-A-TH1", "CORR-SPLIT-A-TH2"]),
                ])
                self.assertEqual(len(events_a), 2)
                self.assertEqual(events_a.mapped("correlation_id"), ["CORR-SPLIT-A-TH1", "CORR-SPLIT-A-TH1"])

                outbox_a = env_check_a["wms.outbox"].search([
                    ("correlation_id", "in", ["CORR-SPLIT-A-TH1", "CORR-SPLIT-A-TH2"]),
                ])
                self.assertEqual(len(outbox_a), 1)
                self.assertEqual(outbox_a.correlation_id, "CORR-SPLIT-A-TH1")
        finally:
            with self.env.registry.cursor() as cr_clean:
                cr_clean.execute("DELETE FROM wms_outbox WHERE correlation_id IN (%s, %s)", ["CORR-SPLIT-A-TH1", "CORR-SPLIT-A-TH2"])
                cr_clean.execute("DELETE FROM wms_inventory_event WHERE correlation_id IN (%s, %s)", ["CORR-SPLIT-A-TH1", "CORR-SPLIT-A-TH2"])
                cr_clean.execute("DELETE FROM stock_move_line WHERE package_id = %s OR result_package_id = %s OR product_id = %s", [src_a_id, dst_a_id, prod_a_id])
                cr_clean.execute("DELETE FROM stock_move WHERE product_id = %s", [prod_a_id])
                cr_clean.execute("DELETE FROM stock_quant WHERE product_id = %s", [prod_a_id])
                cr_clean.execute("DELETE FROM stock_package WHERE id IN (%s, %s)", [src_a_id, dst_a_id])
                cr_clean.execute("DELETE FROM product_product WHERE id = %s", [prod_a_id])
                cr_clean.execute("DELETE FROM product_template WHERE id = %s", [tmpl_a_id])
                cr_clean.execute("DELETE FROM stock_location WHERE id = %s", [loc_a_id])
                cr_clean.commit()

        # =========================================================================
        # Escenario B: DOS fuentes distintas compitiendo por el MISMO destination
        # =========================================================================
        with self.env.registry.cursor() as cr_setup_b:
            env_setup_b = api.Environment(cr_setup_b, 1, {})
            prod_b = env_setup_b["product.product"].create({
                "name": "Product Concurrency Split B",
                "is_storable": True,
            })
            loc_parent_b = env_setup_b.ref("stock.stock_location_stock").location_id
            loc_b = env_setup_b["stock.location"].create({
                "name": "LOC-CONC-SPLIT-B",
                "usage": "internal",
                "location_id": loc_parent_b.id if loc_parent_b else False,
            })
            pkg_src1_b = env_setup_b["stock.package"].create({
                "name": "PKG-HU-066-SRC1-B",
                "hu_state": "OPEN",
            })
            pkg_src2_b = env_setup_b["stock.package"].create({
                "name": "PKG-HU-066-SRC2-B",
                "hu_state": "OPEN",
            })
            pkg_dst_b = env_setup_b["stock.package"].create({
                "name": "PKG-HU-066-DST-B",
                "hu_state": "EMPTY",
            })
            env_setup_b["stock.quant"]._update_available_quantity(
                prod_b,
                loc_b,
                10.0,
                package_id=pkg_src1_b,
            )
            env_setup_b["stock.quant"]._update_available_quantity(
                prod_b,
                loc_b,
                10.0,
                package_id=pkg_src2_b,
            )
            quant1_b = env_setup_b["stock.quant"].search([
                ("product_id", "=", prod_b.id),
                ("package_id", "=", pkg_src1_b.id),
            ], limit=1)
            quant2_b = env_setup_b["stock.quant"].search([
                ("product_id", "=", prod_b.id),
                ("package_id", "=", pkg_src2_b.id),
            ], limit=1)

            src1_b_id = pkg_src1_b.id
            src2_b_id = pkg_src2_b.id
            dst_b_id = pkg_dst_b.id
            quant1_b_id = quant1_b.id
            quant2_b_id = quant2_b.id
            prod_b_id = prod_b.id
            tmpl_b_id = prod_b.product_tmpl_id.id
            loc_b_id = loc_b.id
            cr_setup_b.commit()

        cr2_b = self.env.registry.cursor()
        env2_b = api.Environment(cr2_b, 1, {})
        pkg2_b = env2_b["stock.package"].browse(src2_b_id)

        try:
            barrier_t1_locked_b = threading.Event()
            barrier_t2_calling_b = threading.Event()
            t2_b_result = {}

            def thread_2_worker_b():
                try:
                    barrier_t1_locked_b.wait(timeout=10.0)
                    barrier_t2_calling_b.set()
                    try:
                        # T2 compite por el mismo destination bloqueado por T1
                        pkg2_b._wms_split_physical(quant2_b_id, 4.0, dst_b_id, correlation_id="CORR-SPLIT-B-TH2")
                        cr2_b.commit()
                        t2_b_result["success"] = True
                    except Exception as exc:
                        cr2_b.rollback()
                        t2_b_result["error_class"] = type(exc).__name__
                        t2_b_result["error_msg"] = str(exc)
                        t2_b_result["is_serialization_failure"] = (
                            type(exc).__name__ == "SerializationFailure"
                            or "could not serialize access" in str(exc)
                        )
                except BaseException as exc:
                    barrier_t2_calling_b.set()
                    t2_b_result["outer_error"] = str(exc)
                finally:
                    cr2_b.close()

            t2_b = threading.Thread(target=thread_2_worker_b)
            t2_b.start()

            with self.env.registry.cursor() as cr1_b:
                env1_b = api.Environment(cr1_b, 1, {})
                pkg1_b = env1_b["stock.package"].browse(src1_b_id)
                res1_b = pkg1_b._wms_split_physical(quant1_b_id, 4.0, dst_b_id, correlation_id="CORR-SPLIT-B-TH1")
                self.assertEqual(res1_b.get("source_package_id"), src1_b_id)
                self.assertEqual(res1_b.get("destination_package_id"), dst_b_id)

                barrier_t1_locked_b.set()
                self.assertTrue(barrier_t2_calling_b.wait(timeout=5.0), f"T2-B debió invocar el primitive: {t2_b_result}")
                time.sleep(0.4)

                cr1_b.execute('''
                    SELECT COUNT(*)
                    FROM pg_locks l
                    WHERE NOT l.granted AND l.locktype = 'transactionid'
                ''')
                waiting_locks_b = cr1_b.fetchone()[0]
                self.assertGreaterEqual(waiting_locks_b, 1, "T2-B debe estar bloqueada en PostgreSQL esperando el lock de destino de T1-B")

                cr1_b.commit()

            t2_b.join(timeout=10.0)
            self.assertFalse(t2_b.is_alive(), "T2-B thread debió terminar")

            # Aserciones del escenario B (dos fuentes / un destino)
            self.assertFalse(t2_b_result.get("success"), "T2-B no debió tener éxito porque el destino ya fue ocupado por T1-B")
            self.assertTrue(
                t2_b_result.get("is_serialization_failure"),
                f"T2-B debió recibir SerializationFailure exacto: {t2_b_result}",
            )
            self.assertEqual(
                t2_b_result.get("error_class"),
                "SerializationFailure",
                f"Clase de error de T2-B debió ser SerializationFailure: {t2_b_result}",
            )

            # Comprobar consistencia e invariantes físicas del escenario B
            with self.env.registry.cursor() as cr_check_b:
                env_check_b = api.Environment(cr_check_b, 1, {})
                pkg_src1_chk_b = env_check_b["stock.package"].browse(src1_b_id)
                pkg_src2_chk_b = env_check_b["stock.package"].browse(src2_b_id)
                pkg_dst_chk_b = env_check_b["stock.package"].browse(dst_b_id)

                self.assertEqual(pkg_src1_chk_b.hu_state, "OPEN")
                self.assertEqual(pkg_src1_chk_b.contained_quant_ids.quantity, 6.0)

                self.assertEqual(pkg_src2_chk_b.hu_state, "OPEN")
                self.assertEqual(pkg_src2_chk_b.contained_quant_ids.quantity, 10.0)

                self.assertEqual(pkg_dst_chk_b.hu_state, "OPEN")
                self.assertEqual(pkg_dst_chk_b.contained_quant_ids.quantity, 4.0)

                # Masa total: 6.0 + 10.0 + 4.0 = 20.0
                self.assertEqual(
                    pkg_src1_chk_b.contained_quant_ids.quantity
                    + pkg_src2_chk_b.contained_quant_ids.quantity
                    + pkg_dst_chk_b.contained_quant_ids.quantity,
                    20.0,
                )

                events_b = env_check_b["wms.inventory.event"].search([
                    ("correlation_id", "in", ["CORR-SPLIT-B-TH1", "CORR-SPLIT-B-TH2"]),
                ])
                self.assertEqual(len(events_b), 2)
                self.assertEqual(events_b.mapped("correlation_id"), ["CORR-SPLIT-B-TH1", "CORR-SPLIT-B-TH1"])

                outbox_b = env_check_b["wms.outbox"].search([
                    ("correlation_id", "in", ["CORR-SPLIT-B-TH1", "CORR-SPLIT-B-TH2"]),
                ])
                self.assertEqual(len(outbox_b), 1)
                self.assertEqual(outbox_b.correlation_id, "CORR-SPLIT-B-TH1")
        finally:
            with self.env.registry.cursor() as cr_clean_b:
                cr_clean_b.execute("DELETE FROM wms_outbox WHERE correlation_id IN (%s, %s)", ["CORR-SPLIT-B-TH1", "CORR-SPLIT-B-TH2"])
                cr_clean_b.execute("DELETE FROM wms_inventory_event WHERE correlation_id IN (%s, %s)", ["CORR-SPLIT-B-TH1", "CORR-SPLIT-B-TH2"])
                cr_clean_b.execute("DELETE FROM stock_move_line WHERE package_id IN (%s, %s) OR result_package_id = %s OR product_id = %s", [src1_b_id, src2_b_id, dst_b_id, prod_b_id])
                cr_clean_b.execute("DELETE FROM stock_move WHERE product_id = %s", [prod_b_id])
                cr_clean_b.execute("DELETE FROM stock_quant WHERE product_id = %s", [prod_b_id])
                cr_clean_b.execute("DELETE FROM stock_package WHERE id IN (%s, %s, %s)", [src1_b_id, src2_b_id, dst_b_id])
                cr_clean_b.execute("DELETE FROM product_product WHERE id = %s", [prod_b_id])
                cr_clean_b.execute("DELETE FROM product_template WHERE id = %s", [tmpl_b_id])
                cr_clean_b.execute("DELETE FROM stock_location WHERE id = %s", [loc_b_id])
                cr_clean_b.commit()
