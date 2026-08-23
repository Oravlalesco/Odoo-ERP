# -*- coding: utf-8 -*-
"""Acceptance test suite para HU-004D: Consolidación Física de Handling Units (Physical Merge Core).

Valida el contrato técnico congelado de la primitive transaccional privada
stock.package._wms_merge_physical(destination_package_id, correlation_id=None)
según ADR-001, ADR-004, ADR-006, ADR-010, ADR-011, ADR-013, ADR-019, ADR-022, ADR-023, ADR-026 y ADR-027.
"""

import threading
import time
from unittest.mock import patch

from odoo import api, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestPhysicalMerge(TransactionCase):
    """Suite de tests contractuales para _wms_merge_physical (TEST-HU-067 a TEST-HU-078)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_1 = cls.env.ref("base.main_company")
        cls.company_2 = cls.env["res.company"].create({"name": "WMS Secondary Company Test"})

        # Roles y usuarios WMS
        group_internal = cls.env.ref("base.group_user")
        group_wms_op = cls.env.ref("wms_core.group_wms_operator")
        group_wms_sup = cls.env.ref("wms_core.group_wms_supervisor")
        group_wms_mgr = cls.env.ref("wms_core.group_wms_manager")
        group_stock_usr = cls.env.ref("stock.group_stock_user")

        cls.u_wms_op = cls.env["res.users"].create({
            "name": "WMS Merge Operator",
            "login": "u_hu_merge_op",
            "email": "hu_merge_op@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_op.id])],
        })

        cls.u_wms_sup = cls.env["res.users"].create({
            "name": "WMS Merge Supervisor",
            "login": "u_hu_merge_sup",
            "email": "hu_merge_sup@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_sup.id])],
        })

        cls.u_wms_mgr = cls.env["res.users"].create({
            "name": "WMS Merge Manager",
            "login": "u_hu_merge_mgr",
            "email": "hu_merge_mgr@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_mgr.id])],
        })

        cls.u_stock_usr = cls.env["res.users"].create({
            "name": "Stock User No WMS",
            "login": "u_hu_merge_stock_usr",
            "email": "hu_merge_stock_usr@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id, group_stock_usr.id])],
        })

        cls.u_plain = cls.env["res.users"].create({
            "name": "Plain Internal User",
            "login": "u_hu_merge_plain",
            "email": "hu_merge_plain@test.com",
            "company_id": cls.company_1.id,
            "company_ids": [(6, 0, [cls.company_1.id])],
            "group_ids": [(6, 0, [group_internal.id])],
        })

        cls.u_cross_op = cls.env["res.users"].create({
            "name": "WMS Cross Operator Company 2",
            "login": "u_hu_merge_cross_op",
            "email": "hu_merge_cross_op@test.com",
            "company_id": cls.company_2.id,
            "company_ids": [(6, 0, [cls.company_2.id])],
            "group_ids": [(6, 0, [group_internal.id, group_wms_op.id])],
        })

        # Ubicaciones
        cls.location_internal_1 = cls.env.ref("stock.stock_location_stock")
        cls.location_internal_2 = cls.env["stock.location"].create({
            "name": "LOC-INTERNAL-MERGE-2",
            "usage": "internal",
            "location_id": cls.location_internal_1.location_id.id,
            "company_id": cls.company_1.id,
        })
        cls.location_customer = cls.env.ref("stock.stock_location_customers")

        # Productos
        cls.product_standard = cls.env["product.product"].create({
            "name": "Product Merge Standard",
            "is_storable": True,
            "tracking": "none",
        })
        cls.product_second = cls.env["product.product"].create({
            "name": "Product Merge Second",
            "is_storable": True,
            "tracking": "none",
        })
        cls.product_lot = cls.env["product.product"].create({
            "name": "Product Merge Lot Tracked",
            "is_storable": True,
            "tracking": "lot",
        })
        cls.product_serial = cls.env["product.product"].create({
            "name": "Product Merge Serial Tracked",
            "is_storable": True,
            "tracking": "serial",
        })

        # Tipos de paquete
        cls.pkg_type_standard = cls.env["stock.package.type"].create({
            "name": "BOX-MERGE-STD",
            "company_id": cls.company_1.id,
        })
        cls.pkg_type_cross = cls.env["stock.package.type"].create({
            "name": "BOX-MERGE-CROSS",
            "company_id": cls.company_2.id,
        })

        # Partner Owner
        cls.partner_owner = cls.env["res.partner"].create({
            "name": "Merge Test Owner",
        })

        # SSCC Allocator Sequence
        cls.ir_seq_c1 = cls.env["ir.sequence"].create({
            "name": "Merge SSCC ir_seq",
            "padding": 7,
            "number_increment": 1,
            "company_id": cls.company_1.id,
        })
        cls.sscc_sequence_c1 = cls.env["wms.sscc.sequence"].create({
            "name": "Merge SSCC Allocator",
            "company_id": cls.company_1.id,
            "gs1_company_prefix": "750123456",
            "extension_digit": "0",
            "sequence_id": cls.ir_seq_c1.id,
        })

    def _create_packed_quant(self, product, location, quantity, package, lot=None, owner=None, company=None):
        """Helper para crear un quant empaquetado inicial mediante _update_available_quantity nativo."""
        comp = company or self.company_1
        self.env["stock.quant"].with_company(comp)._update_available_quantity(
            product,
            location,
            quantity,
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

    # =========================================================================
    # TEST-HU-067: Contrato de API y Preflights
    # =========================================================================
    def test_hu_067_physical_merge_api_contract(self):
        """TEST-HU-067: Singleton, firma, tipos inválidos, same-package y normalización de correlation ID."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-067-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-067-DST", "hu_state": "OPEN"})
        self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, pkg_source)
        self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_dest)

        # 1. Multi-record / empty set lanza error
        empty_pkg = self.env["stock.package"]
        multi_pkg = pkg_source | pkg_dest
        with self.assertRaises(ValueError):
            empty_pkg._wms_merge_physical(pkg_dest.id)
        with self.assertRaises(ValueError):
            multi_pkg._wms_merge_physical(pkg_dest.id)

        # 2. Tipos inválidos de destination_package_id
        with self.assertRaises(ValidationError):
            pkg_source._wms_merge_physical(False)
        with self.assertRaises(ValidationError):
            pkg_source._wms_merge_physical("invalid_id")
        with self.assertRaises(ValidationError):
            pkg_source._wms_merge_physical(-5)
        with self.assertRaises(ValidationError):
            pkg_source._wms_merge_physical(0)

        # 3. Same-package rechazo
        with self.assertRaises(ValidationError):
            pkg_source._wms_merge_physical(pkg_source.id)

        # 4. Correlation ID inválido
        with self.assertRaises(ValidationError):
            pkg_source._wms_merge_physical(pkg_dest.id, correlation_id=12345)
        with self.assertRaises(ValidationError):
            pkg_source._wms_merge_physical(pkg_dest.id, correlation_id="   ")

        # 5. Happy path con correlation_id=None genera UUID / valor no vacío
        res = pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id, correlation_id=None)
        self.assertEqual(res["source_package_id"], pkg_source.id)
        self.assertEqual(res["destination_package_id"], pkg_dest.id)
        self.assertTrue(isinstance(res["correlation_id"], str) and len(res["correlation_id"]) > 0)

    # =========================================================================
    # TEST-HU-068: Merge Básico Multi-Quant, Moves, History y Preservación
    # =========================================================================
    def test_hu_068_basic_multi_quant_merge_moves_and_history(self):
        """TEST-HU-068: Merge multi-quant básico, N moves done, N lines, 1 history en destino, SSCC y metadatos intactos."""
        pkg_source = self.env["stock.package"].create({
            "name": "PKG-HU-068-SRC",
            "hu_state": "OPEN",
            "hu_class": "CASE",
            "package_type_id": self.pkg_type_standard.id,
            "shipping_weight": 2.5,
            "company_id": self.company_1.id,
        })
        pkg_dest = self.env["stock.package"].create({
            "name": "PKG-HU-068-DST",
            "hu_state": "OPEN",
            "hu_class": "CASE",
            "package_type_id": self.pkg_type_standard.id,
            "shipping_weight": 5.0,
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_source)
        self._create_packed_quant(self.product_second, self.location_internal_1, 3.0, pkg_source)
        self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, pkg_dest)

        # Asignar SSCC válido a ambos paquetes
        pkg_source.assign_sscc(self.sscc_sequence_c1.id)
        pkg_dest.assign_sscc(self.sscc_sequence_c1.id)
        self.assertTrue(pkg_source.valid_sscc)
        self.assertTrue(pkg_dest.valid_sscc)
        src_sscc_name = pkg_source.name
        dst_sscc_name = pkg_dest.name

        init_moves_count = self.env["stock.move"].search_count([])
        init_history_count = self.env["stock.package.history"].search_count([])

        res = pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id, correlation_id="CORR-HU-068")
        self.assertEqual(res["source_package_id"], pkg_source.id)
        self.assertEqual(res["destination_package_id"], pkg_dest.id)

        # SSCC preservado intacto
        self.assertEqual(pkg_source.name, src_sscc_name)
        self.assertEqual(pkg_dest.name, dst_sscc_name)
        self.assertTrue(pkg_source.valid_sscc)
        self.assertTrue(pkg_dest.valid_sscc)

        # 1. Exactamente N moves creados y confirmados (N=2 líneas entrantes)
        self.assertEqual(self.env["stock.move"].search_count([]), init_moves_count + 2)
        new_moves = self.env["stock.move"].search([], order="id desc", limit=2)
        for move in new_moves:
            self.assertEqual(move.state, "done")
            self.assertEqual(move.is_inventory, True)
            self.assertEqual(move.location_id, self.location_internal_1)
            self.assertEqual(move.location_dest_id, self.location_internal_1)
            self.assertEqual(len(move.move_line_ids), 1)
            self.assertEqual(move.move_line_ids.package_id, pkg_source)
            self.assertEqual(move.move_line_ids.result_package_id, pkg_dest)

        # 2. Historial nativo: exactamente 1 nuevo registro para el destino
        self.assertEqual(self.env["stock.package.history"].search_count([]), init_history_count + 1)
        new_histories = self.env["stock.package.history"].search([("package_id", "=", pkg_dest.id)])
        self.assertEqual(len(new_histories), 1)

        # 3. Ciclo de vida y masa física
        self.assertEqual(pkg_source.hu_state, "EMPTY")
        self.assertEqual(len(pkg_source.contained_quant_ids), 0)
        self.assertEqual(pkg_dest.hu_state, "OPEN")
        dest_quant_sum = sum(pkg_dest.contained_quant_ids.mapped("quantity"))
        self.assertEqual(dest_quant_sum, 10.0)  # 5 + 3 + 2 = 10

        # 4. Preservación intacta de metadatos de ambos paquetes
        self.assertEqual(pkg_source.name, src_sscc_name)
        self.assertEqual(pkg_source.hu_class, "CASE")
        self.assertEqual(pkg_source.package_type_id, self.pkg_type_standard)
        self.assertEqual(pkg_source.shipping_weight, 2.5)

        self.assertEqual(pkg_dest.name, dst_sscc_name)
        self.assertEqual(pkg_dest.hu_class, "CASE")
        self.assertEqual(pkg_dest.package_type_id, self.pkg_type_standard)
        self.assertEqual(pkg_dest.shipping_weight, 5.0)

    # =========================================================================
    # TEST-HU-069: Preservación de 6 Dimensiones de Quants y Fusión Nativa
    # =========================================================================
    def test_hu_069_quant_dimensions_preservation_and_native_fusion(self):
        """TEST-HU-069: Preservación de 6 dimensiones (product, lot, owner, package, location, company) y fusión nativa."""
        lot_a = self.env["stock.lot"].create({
            "name": "LOT-HU-069-A",
            "product_id": self.product_lot.id,
            "company_id": self.company_1.id,
        })
        lot_b = self.env["stock.lot"].create({
            "name": "LOT-HU-069-B",
            "product_id": self.product_lot.id,
            "company_id": self.company_1.id,
        })

        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-069-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-069-DST", "hu_state": "OPEN"})

        # Fuente: standard prod (4.0), lot_a con owner (3.0), lot_b sin owner (2.0)
        self._create_packed_quant(self.product_standard, self.location_internal_1, 4.0, pkg_source)
        self._create_packed_quant(self.product_lot, self.location_internal_1, 3.0, pkg_source, lot=lot_a, owner=self.partner_owner)
        self._create_packed_quant(self.product_lot, self.location_internal_1, 2.0, pkg_source, lot=lot_b)

        # Destino: standard prod (6.0 -> debe fusionarse a 10.0), lot_a con owner (1.0 -> debe fusionarse a 4.0)
        self._create_packed_quant(self.product_standard, self.location_internal_1, 6.0, pkg_dest)
        self._create_packed_quant(self.product_lot, self.location_internal_1, 1.0, pkg_dest, lot=lot_a, owner=self.partner_owner)

        pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id, correlation_id="CORR-HU-069")

        # 1. Cero filas huérfanas en la fuente
        source_remaining_quants = self.env["stock.quant"].search([("package_id", "=", pkg_source.id)])
        self.assertEqual(len(source_remaining_quants), 0)

        # 2. Quants en destino: 3 quants resultantes con dimensiones exactas
        dest_quants = self.env["stock.quant"].search([("package_id", "=", pkg_dest.id)])
        self.assertEqual(len(dest_quants), 3)

        q_std = dest_quants.filtered(lambda q: q.product_id == self.product_standard)
        self.assertEqual(len(q_std), 1)
        self.assertEqual(q_std.quantity, 10.0)  # 4 + 6 = 10
        self.assertEqual(q_std.company_id, self.company_1)
        self.assertEqual(q_std.location_id, self.location_internal_1)
        self.assertFalse(q_std.lot_id)
        self.assertFalse(q_std.owner_id)

        q_lot_a = dest_quants.filtered(lambda q: q.product_id == self.product_lot and q.lot_id == lot_a)
        self.assertEqual(len(q_lot_a), 1)
        self.assertEqual(q_lot_a.quantity, 4.0)  # 3 + 1 = 4
        self.assertEqual(q_lot_a.owner_id, self.partner_owner)

        q_lot_b = dest_quants.filtered(lambda q: q.product_id == self.product_lot and q.lot_id == lot_b)
        self.assertEqual(len(q_lot_b), 1)
        self.assertEqual(q_lot_b.quantity, 2.0)
        self.assertFalse(q_lot_b.owner_id)

    # =========================================================================
    # TEST-HU-070: Contrato de 2N Eventos y 1 Outbox (ADR-019)
    # =========================================================================
    def test_hu_070_event_outbox_contract(self):
        """TEST-HU-070: Contrato exacto de 2N eventos (UNPACK fuente y PACK destino) y 1 mensaje outbox inventory.hu.merged."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-070-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-070-DST", "hu_state": "OPEN"})
        self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_source)
        self._create_packed_quant(self.product_second, self.location_internal_1, 3.0, pkg_source)
        self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, pkg_dest)

        corr_id = "CORR-MERGE-070-UUID"
        pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id, correlation_id=corr_id)

        # 1. Exactamente 2N eventos (N=2 -> 4 eventos)
        events = self.env["wms.inventory.event"].search([("correlation_id", "=", corr_id)], order="id asc")
        self.assertEqual(len(events), 4)

        # Orden estricto por cada línea: UNPACK(source) -> PACK(destination)
        self.assertEqual(events[0].event_type, "UNPACK")
        self.assertEqual(events[0].package_id, pkg_source)
        self.assertEqual(events[0].product_id, self.product_standard)
        self.assertEqual(events[0].quantity, 5.0)
        self.assertEqual(events[0].operator_id, self.u_wms_op)
        self.assertEqual(events[0].company_id, self.company_1)
        self.assertEqual(events[0].source_location_id, self.location_internal_1)
        self.assertEqual(events[0].dest_location_id, self.location_internal_1)

        self.assertEqual(events[1].event_type, "PACK")
        self.assertEqual(events[1].package_id, pkg_dest)
        self.assertEqual(events[1].product_id, self.product_standard)
        self.assertEqual(events[1].quantity, 5.0)
        self.assertEqual(events[1].operator_id, self.u_wms_op)

        self.assertEqual(events[2].event_type, "UNPACK")
        self.assertEqual(events[2].package_id, pkg_source)
        self.assertEqual(events[2].product_id, self.product_second)
        self.assertEqual(events[2].quantity, 3.0)

        self.assertEqual(events[3].event_type, "PACK")
        self.assertEqual(events[3].package_id, pkg_dest)
        self.assertEqual(events[3].product_id, self.product_second)
        self.assertEqual(events[3].quantity, 3.0)

        # 2. Exactamente 1 mensaje Outbox con 7 claves raíz y 5 claves por línea
        outbox_msgs = self.env["wms.outbox"].search([("correlation_id", "=", corr_id)])
        self.assertEqual(len(outbox_msgs), 1)
        msg = outbox_msgs[0]
        self.assertEqual(msg.event_name, "inventory.hu.merged")
        self.assertEqual(msg.schema_version, 1)
        self.assertEqual(msg.company_id, self.company_1)

        payload = msg.payload
        self.assertEqual(set(payload.keys()), {
            "source_package_id",
            "source_package_ref",
            "destination_package_id",
            "destination_package_ref",
            "location_id",
            "line_count",
            "lines",
        })
        self.assertEqual(payload["source_package_id"], pkg_source.id)
        self.assertEqual(payload["source_package_ref"], pkg_source.name)
        self.assertEqual(payload["destination_package_id"], pkg_dest.id)
        self.assertEqual(payload["destination_package_ref"], pkg_dest.name)
        self.assertEqual(payload["location_id"], self.location_internal_1.id)
        self.assertEqual(payload["line_count"], 2)

        for line in payload["lines"]:
            self.assertEqual(set(line.keys()), {
                "product_id",
                "lot_id",
                "owner_id",
                "quantity",
                "uom_id",
            })

    # =========================================================================
    # TEST-HU-071: Rollback Atómico ante Fallo de Outbox / Integración
    # =========================================================================
    def test_hu_071_merge_atomic_rollback_on_outbox_failure(self):
        """TEST-HU-071: Transacción atómica revierte mutación física y eventos si el outbox falla."""
        pkg_source = self.env["stock.package"].create({
            "name": "PKG-HU-071-SRC",
            "hu_state": "OPEN",
            "shipping_weight": 3.0,
        })
        pkg_dest = self.env["stock.package"].create({
            "name": "PKG-HU-071-DST",
            "hu_state": "OPEN",
            "shipping_weight": 6.0,
        })
        self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_source)
        self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, pkg_dest)

        init_moves_count = self.env["stock.move"].search_count([])
        init_lines_count = self.env["stock.move.line"].search_count([])
        init_hist_count = self.env["stock.package.history"].search_count([])
        init_events_count = self.env["wms.inventory.event"].search_count([])
        init_outbox_count = self.env["wms.outbox"].search_count([])

        with patch.object(
            type(self.env["wms.inventory.event"]),
            "_append_events_with_outbox",
            side_effect=RuntimeError("Simulated Outbox Failure"),
        ):
            with self.assertRaises(RuntimeError):
                pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id, correlation_id="CORR-FAIL-071")

        # Rollback check explícito de 0 registros nuevos
        self.assertEqual(self.env["stock.move"].search_count([]), init_moves_count)
        self.assertEqual(self.env["stock.move.line"].search_count([]), init_lines_count)
        self.assertEqual(self.env["stock.package.history"].search_count([]), init_hist_count)
        self.assertEqual(self.env["wms.inventory.event"].search_count([]), init_events_count)
        self.assertEqual(self.env["wms.outbox"].search_count([]), init_outbox_count)

        # Estados, quants, masa y metadata intactos
        self.assertEqual(pkg_source.hu_state, "OPEN")
        self.assertEqual(pkg_dest.hu_state, "OPEN")
        self.assertEqual(pkg_source.contained_quant_ids.quantity, 5.0)
        self.assertEqual(pkg_dest.contained_quant_ids.quantity, 2.0)
        self.assertEqual(pkg_source.shipping_weight, 3.0)
        self.assertEqual(pkg_dest.shipping_weight, 6.0)

    # =========================================================================
    # TEST-HU-072: Guards de Scope y Lifecycle
    # =========================================================================
    def test_hu_072_scope_and_lifecycle_guards(self):
        """TEST-HU-072: Rechazo de paquetes anidados (padres e hijos), contenido exclusivamente indirecto, estados no OPEN, fuente vacía y destino vacío."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-072-SRC", "hu_state": "OPEN", "company_id": self.company_1.id})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-072-DST", "hu_state": "OPEN", "company_id": self.company_1.id})
        self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_source)
        self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, pkg_dest)

        # 1. Paquetes anidados (con parent_package_id)
        pkg_parent = self.env["stock.package"].create({"name": "PKG-PARENT", "hu_state": "OPEN", "company_id": self.company_1.id})
        pkg_source.parent_package_id = pkg_parent.id
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)
        pkg_source.parent_package_id = False

        pkg_dest.parent_package_id = pkg_parent.id
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)
        pkg_dest.parent_package_id = False

        # 2. Paquetes anidados (con child_package_ids)
        pkg_child_src = self.env["stock.package"].create({"name": "PKG-CHILD-SRC", "hu_state": "OPEN", "parent_package_id": pkg_source.id, "company_id": self.company_1.id})
        pkg_source.invalidate_recordset(["child_package_ids"])
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)
        pkg_child_src.parent_package_id = False
        pkg_source.invalidate_recordset(["child_package_ids"])

        pkg_child_dst = self.env["stock.package"].create({"name": "PKG-CHILD-DST", "hu_state": "OPEN", "parent_package_id": pkg_dest.id, "company_id": self.company_1.id})
        pkg_dest.invalidate_recordset(["child_package_ids"])
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)
        pkg_child_dst.parent_package_id = False
        pkg_dest.invalidate_recordset(["child_package_ids"])

        # 3. Contenido exclusivamente indirecto (quants en paquetes hijos, 0 quants directos)
        pkg_indirect_src = self.env["stock.package"].create({"name": "PKG-IND-SRC", "hu_state": "OPEN", "company_id": self.company_1.id})
        pkg_indirect_child = self.env["stock.package"].create({
            "name": "PKG-IND-CHILD",
            "hu_state": "OPEN",
            "parent_package_id": pkg_indirect_src.id,
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_indirect_child)
        with self.assertRaises(ValidationError):
            pkg_indirect_src.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)

        # 4. Estados no OPEN en fuente
        pkg_source.hu_state = "EMPTY"
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)
        pkg_source.hu_state = "CLOSED"
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)
        pkg_source.hu_state = "OPEN"

        # 5. Estados no OPEN en destino (incluyendo EMPTY y False)
        pkg_dest.hu_state = "EMPTY"
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)
        pkg_dest.hu_state = False
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)
        pkg_dest.hu_state = "OPEN"

        # 6. Fuente sin quants
        pkg_empty_src = self.env["stock.package"].create({"name": "PKG-EMPTY-SRC", "hu_state": "OPEN", "company_id": self.company_1.id})
        with self.assertRaises(ValidationError):
            pkg_empty_src.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)

        # 7. Destino sin quants
        pkg_empty_dest = self.env["stock.package"].create({"name": "PKG-EMPTY-DST", "hu_state": "OPEN", "company_id": self.company_1.id})
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_empty_dest.id)

    # =========================================================================
    # TEST-HU-073: Guards de Compañía y Ubicación
    # =========================================================================
    def test_hu_073_company_and_location_guards(self):
        """TEST-HU-073: Cross-company, compañía no asignada, ubicaciones distintas y ubicación no interna."""
        pkg_source = self.env["stock.package"].create({
            "name": "PKG-HU-073-SRC",
            "hu_state": "OPEN",
            "company_id": self.company_1.id,
        })
        pkg_dest = self.env["stock.package"].create({
            "name": "PKG-HU-073-DST",
            "hu_state": "OPEN",
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_source)
        self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, pkg_dest)

        # 1. Cross-company entre paquetes
        pkg_dest.write({"company_id": self.company_2.id})
        with self.assertRaises(AccessError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)
        pkg_dest.write({"company_id": self.company_1.id})

        # 2. Operador cross-company sin acceso a la compañía del inventario origen
        with self.assertRaises(AccessError):
            pkg_source.with_user(self.u_cross_op)._wms_merge_physical(pkg_dest.id)

        # 3. Compañía no resuelta en fuente o destino (company_id=False)
        loc_global = self.env["stock.location"].create({
            "name": "LOC-GLOBAL-073",
            "usage": "internal",
            "location_id": False,
            "company_id": False,
        })
        pkg_unres_src = self.env["stock.package"].create({
            "name": "PKG-UNRES-SRC",
            "hu_state": "OPEN",
            "company_id": False,
        })
        self.env["stock.quant"].create({
            "product_id": self.product_standard.id,
            "location_id": loc_global.id,
            "quantity": 5.0,
            "package_id": pkg_unres_src.id,
            "company_id": False,
        })
        pkg_unres_src.invalidate_recordset(["company_id", "contained_quant_ids", "quant_ids"])
        with self.assertRaises(ValidationError):
            pkg_unres_src.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)

        pkg_unres_dst = self.env["stock.package"].create({
            "name": "PKG-UNRES-DST",
            "hu_state": "OPEN",
            "company_id": False,
        })
        self.env["stock.quant"].create({
            "product_id": self.product_standard.id,
            "location_id": loc_global.id,
            "quantity": 2.0,
            "package_id": pkg_unres_dst.id,
            "company_id": False,
        })
        pkg_unres_dst.invalidate_recordset(["company_id", "contained_quant_ids", "quant_ids"])
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_unres_dst.id)

        # 4. Ubicaciones diferentes entre paquetes
        pkg_dest_loc2 = self.env["stock.package"].create({
            "name": "PKG-HU-073-L2",
            "hu_state": "OPEN",
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_standard, self.location_internal_2, 2.0, pkg_dest_loc2)
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest_loc2.id)

        # 5. Ubicación no interna
        loc_non_int = self.env["stock.location"].create({
            "name": "LOC-NON-INT",
            "usage": "inventory",
            "location_id": self.location_internal_1.location_id.id,
            "company_id": self.company_1.id,
        })
        pkg_non_int_src = self.env["stock.package"].create({
            "name": "PKG-NONINT-SRC",
            "hu_state": "OPEN",
            "company_id": self.company_1.id,
        })
        pkg_non_int_dest = self.env["stock.package"].create({
            "name": "PKG-NONINT-DST",
            "hu_state": "OPEN",
            "company_id": self.company_1.id,
        })
        self.env["stock.quant"].create({
            "product_id": self.product_standard.id,
            "location_id": loc_non_int.id,
            "quantity": 5.0,
            "package_id": pkg_non_int_src.id,
            "company_id": self.company_1.id,
        })
        self.env["stock.quant"].create({
            "product_id": self.product_standard.id,
            "location_id": loc_non_int.id,
            "quantity": 2.0,
            "package_id": pkg_non_int_dest.id,
            "company_id": self.company_1.id,
        })
        with self.assertRaises(ValidationError):
            pkg_non_int_src.with_user(self.u_wms_op)._wms_merge_physical(pkg_non_int_dest.id)

    # =========================================================================
    # TEST-HU-074: Guards de Reservas, Quants Negativos y Tracking
    # =========================================================================
    def test_hu_074_reservations_negative_quants_and_tracking_guards(self):
        """TEST-HU-074: Cero reservas en fuente/destino, rechazo de quants negativos, lote obligatorio y serial=1.0."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-074-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-074-DST", "hu_state": "OPEN"})
        q_src = self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_source)
        q_dst = self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, pkg_dest)

        # 1. Reservas activas en fuente
        q_src.write({"reserved_quantity": 2.0})
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)
        q_src.write({"reserved_quantity": 0.0})

        # 2. Reservas activas en destino
        q_dst.write({"reserved_quantity": 1.0})
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)
        q_dst.write({"reserved_quantity": 0.0})

        # 3. Quant con cantidad negativa en fuente
        q_src.write({"quantity": -1.0})
        with self.assertRaises(ValidationError):
            pkg_source.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)
        q_src.write({"quantity": 5.0})

        # 4. Producto tracked por lote sin lote asignado
        pkg_lot_src = self.env["stock.package"].create({"name": "PKG-LOT-SRC", "hu_state": "OPEN"})
        self._create_packed_quant(self.product_lot, self.location_internal_1, 3.0, pkg_lot_src, lot=None)
        with self.assertRaises(ValidationError):
            pkg_lot_src.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)

        # 5. Producto tracked por serie con cantidad > 1.0
        lot_sn = self.env["stock.lot"].create({
            "name": "SN-074-001",
            "product_id": self.product_serial.id,
            "company_id": self.company_1.id,
        })
        pkg_sn_src = self.env["stock.package"].create({"name": "PKG-SN-SRC", "hu_state": "OPEN"})
        self._create_packed_quant(self.product_serial, self.location_internal_1, 2.0, pkg_sn_src, lot=lot_sn)
        with self.assertRaises(ValidationError):
            pkg_sn_src.with_user(self.u_wms_op)._wms_merge_physical(pkg_dest.id)

    # =========================================================================
    # TEST-HU-075: Guards de Inventory Block (5 Scopes)
    # =========================================================================
    def test_hu_075_inventory_block_guards(self):
        """TEST-HU-075: Verificación individual de los 5 scopes de wms.inventory.block en source y destination."""
        block_model = self.env["wms.inventory.block"]

        def _setup_pair():
            src = self.env["stock.package"].create({"name": f"PKG-BLK-SRC-{time.time()}", "hu_state": "OPEN"})
            dst = self.env["stock.package"].create({"name": f"PKG-BLK-DST-{time.time()}", "hu_state": "OPEN"})
            lot = self.env["stock.lot"].create({
                "name": f"LOT-BLK-{time.time()}",
                "product_id": self.product_lot.id,
                "company_id": self.company_1.id,
            })
            self._create_packed_quant(self.product_lot, self.location_internal_1, 5.0, src, lot=lot, owner=self.partner_owner)
            self._create_packed_quant(self.product_lot, self.location_internal_1, 2.0, dst, lot=lot, owner=self.partner_owner)
            return src, dst, lot

        # 1. Scope PACKAGE en SOURCE
        s1, d1, l1 = _setup_pair()
        block_model.create({
            "company_id": self.company_1.id,
            "block_scope": "PACKAGE",
            "package_id": s1.id,
            "block_type": "HOLD",
            "reason": "Block Package Source Test",
        })
        with self.assertRaises(ValidationError):
            s1.with_user(self.u_wms_op)._wms_merge_physical(d1.id)

        # 2. Scope PACKAGE en DESTINATION
        s2, d2, l2 = _setup_pair()
        block_model.create({
            "company_id": self.company_1.id,
            "block_scope": "PACKAGE",
            "package_id": d2.id,
            "block_type": "HOLD",
            "reason": "Block Package Dest Test",
        })
        with self.assertRaises(ValidationError):
            s2.with_user(self.u_wms_op)._wms_merge_physical(d2.id)

        # 3. Scope LOT
        s3, d3, l3 = _setup_pair()
        block_model.create({
            "company_id": self.company_1.id,
            "block_scope": "LOT",
            "product_id": self.product_lot.id,
            "lot_id": l3.id,
            "block_type": "HOLD",
            "reason": "Block Lot Test",
        })
        with self.assertRaises(ValidationError):
            s3.with_user(self.u_wms_op)._wms_merge_physical(d3.id)

        # 4. Scope PRODUCT_LOCATION
        s4, d4, l4 = _setup_pair()
        block_model.create({
            "company_id": self.company_1.id,
            "block_scope": "PRODUCT_LOCATION",
            "product_id": self.product_lot.id,
            "location_id": self.location_internal_1.id,
            "block_type": "HOLD",
            "reason": "Block Product Location Test",
        })
        with self.assertRaises(ValidationError):
            s4.with_user(self.u_wms_op)._wms_merge_physical(d4.id)

        # 5. Scope OWNER_LOCATION
        s5, d5, l5 = _setup_pair()
        block_model.create({
            "company_id": self.company_1.id,
            "block_scope": "OWNER_LOCATION",
            "owner_id": self.partner_owner.id,
            "location_id": self.location_internal_1.id,
            "block_type": "HOLD",
            "reason": "Block Owner Location Test",
        })
        with self.assertRaises(ValidationError):
            s5.with_user(self.u_wms_op)._wms_merge_physical(d5.id)

        # 6. Scope LOCATION en ubicación interna
        s6, d6, l6 = _setup_pair()
        block_loc = block_model.create({
            "company_id": self.company_1.id,
            "block_scope": "LOCATION",
            "location_id": self.location_internal_1.id,
            "block_type": "HOLD",
            "reason": "Block Location Internal Test",
        })
        with self.assertRaises(ValidationError):
            s6.with_user(self.u_wms_op)._wms_merge_physical(d6.id)
        # Verificar que no hubo mutación física ni efectos
        self.assertEqual(s6.hu_state, "OPEN")
        self.assertEqual(d6.hu_state, "OPEN")
        self.assertEqual(sum(s6.contained_quant_ids.mapped("quantity")), 5.0)
        self.assertEqual(sum(d6.contained_quant_ids.mapped("quantity")), 2.0)

    # =========================================================================
    # TEST-HU-076: Guards de Admisión PLM en Destino
    # =========================================================================
    def test_hu_076_plm_destination_admission_guards(self):
        """TEST-HU-076: PLM destination admission: multi-producto atómico, allowlist vacía, destino sin tipo, cross-company y tipo de fuente intacto."""
        pkg_type_box = self.env["stock.package.type"].create({"name": "BOX-PLM-ALLOW", "company_id": False})
        pkg_type_pallet = self.env["stock.package.type"].create({"name": "PALLET-PLM-DISALLOW", "company_id": False})

        # Configurar PLM: product_standard solo permite BOX, product_second solo permite PALLET
        logistics_std = self.env["wms.product.logistics"].create({
            "product_tmpl_id": self.product_standard.product_tmpl_id.id,
            "company_id": False,
            "allowed_hu_type_ids": [(6, 0, [pkg_type_box.id])],
        })
        logistics_sec = self.env["wms.product.logistics"].create({
            "product_tmpl_id": self.product_second.product_tmpl_id.id,
            "company_id": False,
            "allowed_hu_type_ids": [(6, 0, [pkg_type_pallet.id])],
        })

        pkg_src = self.env["stock.package"].create({
            "name": "PKG-PLM-SRC",
            "hu_state": "OPEN",
            "package_type_id": pkg_type_pallet.id,  # Fuente puede tener cualquier tipo
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_src)

        # 1. Multi-producto entrante: una línea permitida (product_standard en BOX) y otra línea restringida (product_second requiere PALLET)
        pkg_src_multi = self.env["stock.package"].create({
            "name": "PKG-PLM-MULTI-SRC",
            "hu_state": "OPEN",
            "package_type_id": pkg_type_pallet.id,
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_standard, self.location_internal_1, 5.0, pkg_src_multi)
        self._create_packed_quant(self.product_second, self.location_internal_1, 3.0, pkg_src_multi)

        pkg_dst_box = self.env["stock.package"].create({
            "name": "PKG-PLM-BOX-DST",
            "hu_state": "OPEN",
            "package_type_id": pkg_type_box.id,
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, pkg_dst_box)

        # Debe rechazar atómicamente porque product_second no admite BOX en destino
        with self.assertRaises(ValidationError):
            pkg_src_multi.with_user(self.u_wms_op)._wms_merge_physical(pkg_dst_box.id)
        # Cero efectos físicos
        self.assertEqual(pkg_src_multi.hu_state, "OPEN")
        self.assertEqual(len(pkg_src_multi.contained_quant_ids), 2)
        self.assertEqual(len(pkg_dst_box.contained_quant_ids), 1)
        self.assertEqual(pkg_src_multi.package_type_id, pkg_type_pallet)
        self.assertEqual(pkg_dst_box.package_type_id, pkg_type_box)
        self.assertEqual(logistics_sec.allowed_hu_type_ids.ids, [pkg_type_pallet.id])
        self.assertEqual(logistics_std.allowed_hu_type_ids.ids, [pkg_type_box.id])

        # 2. Allowlist vacía (producto sin restricciones PLM -> unrestricted admission)
        logistics_sec.write({"allowed_hu_type_ids": [(5, 0, 0)]})  # Allowlist vacía
        pkg_src_unrestricted = self.env["stock.package"].create({
            "name": "PKG-PLM-UNRES-SRC",
            "hu_state": "OPEN",
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_second, self.location_internal_1, 3.0, pkg_src_unrestricted)
        pkg_dst_notype_unres = self.env["stock.package"].create({
            "name": "PKG-PLM-NOTYPE-UNRES",
            "hu_state": "OPEN",
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_second, self.location_internal_1, 2.0, pkg_dst_notype_unres)
        # Con allowlist vacía, el destino sin tipo de paquete es admitido
        res_unres = pkg_src_unrestricted.with_user(self.u_wms_op)._wms_merge_physical(pkg_dst_notype_unres.id)
        self.assertEqual(res_unres["source_package_id"], pkg_src_unrestricted.id)
        self.assertEqual(pkg_dst_notype_unres.hu_state, "OPEN")
        self.assertEqual(sum(pkg_dst_notype_unres.contained_quant_ids.mapped("quantity")), 5.0)

        # 3. Destino sin tipo de paquete (rechazado cuando PLM exige allowlist no vacía)
        pkg_dst_notype = self.env["stock.package"].create({
            "name": "PKG-PLM-NOTYPE",
            "hu_state": "OPEN",
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, pkg_dst_notype)
        with self.assertRaises(ValidationError):
            pkg_src.with_user(self.u_wms_op)._wms_merge_physical(pkg_dst_notype.id)

        # 4. Destino con tipo no permitido
        pkg_dst_disallow = self.env["stock.package"].create({
            "name": "PKG-PLM-DISALLOW",
            "hu_state": "OPEN",
            "package_type_id": pkg_type_pallet.id,
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, pkg_dst_disallow)
        with self.assertRaises(ValidationError):
            pkg_src.with_user(self.u_wms_op)._wms_merge_physical(pkg_dst_disallow.id)

        # 5. Destino con tipo cross-company
        pkg_dst_cross = self.env["stock.package"].create({
            "name": "PKG-PLM-CROSS",
            "hu_state": "OPEN",
            "package_type_id": self.pkg_type_cross.id,
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, pkg_dst_cross)
        with self.assertRaises(ValidationError):
            pkg_src.with_user(self.u_wms_op)._wms_merge_physical(pkg_dst_cross.id)

        # 6. Destino con tipo permitido (Happy path)
        pkg_dst_ok = self.env["stock.package"].create({
            "name": "PKG-PLM-OK",
            "hu_state": "OPEN",
            "package_type_id": pkg_type_box.id,
            "company_id": self.company_1.id,
        })
        self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, pkg_dst_ok)
        res = pkg_src.with_user(self.u_wms_op)._wms_merge_physical(pkg_dst_ok.id)
        self.assertEqual(res["source_package_id"], pkg_src.id)
        self.assertEqual(pkg_src.package_type_id, pkg_type_pallet)  # Tipo de fuente intacto

        # Cleanup
        logistics_std.unlink()
        logistics_sec.unlink()

    # =========================================================================
    # TEST-HU-077: Matriz RBAC, Direct CRUD y Operador Real por Correlación
    def test_hu_077_rbac_matrix_direct_crud_and_operator_per_correlation(self):
        """TEST-HU-077: RBAC, rechazo Direct CRUD, rechazo no autorizados y operador real verificado por correlación."""
        pkg_source = self.env["stock.package"].create({"name": "PKG-HU-077-SRC", "hu_state": "OPEN"})
        pkg_dest = self.env["stock.package"].create({"name": "PKG-HU-077-DST", "hu_state": "OPEN"})
        quant_src = self._create_packed_quant(self.product_standard, self.location_internal_1, 10.0, pkg_source)
        self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, pkg_dest)

        # 1. Direct CRUD denegado a Operator
        with self.assertRaises(AccessError):
            pkg_source.with_user(self.u_wms_op).write({"hu_state": "EMPTY"})
        with self.assertRaises(AccessError):
            quant_src.with_user(self.u_wms_op).write({"package_id": pkg_dest.id})

        # 2. Usuarios denegados (Plain, Stock user, Cross-company)
        with self.assertRaises(AccessError):
            pkg_source.with_user(self.u_plain)._wms_merge_physical(pkg_dest.id)
        with self.assertRaises(AccessError):
            pkg_source.with_user(self.u_stock_usr)._wms_merge_physical(pkg_dest.id)
        with self.assertRaises(AccessError):
            pkg_source.with_user(self.u_cross_op)._wms_merge_physical(pkg_dest.id)

        # 3. Usuarios autorizados (Operator, Supervisor, Manager, System Admin)
        u_admin = self.env.ref("base.user_admin")
        u_admin.sudo().write({"company_ids": [(4, self.company_1.id)], "company_id": self.company_1.id})
        auth_users = [self.u_wms_op, self.u_wms_sup, self.u_wms_mgr, u_admin]
        user_executions = []

        for user in auth_users:
            src_temp = self.env["stock.package"].create({"name": f"PKG-SRC-{user.login}", "hu_state": "OPEN"})
            dst_temp = self.env["stock.package"].create({"name": f"PKG-DST-{user.login}", "hu_state": "OPEN"})
            self._create_packed_quant(self.product_standard, self.location_internal_1, 4.0, src_temp)
            self._create_packed_quant(self.product_standard, self.location_internal_1, 2.0, dst_temp)

            corr_id = f"CORR-MERGE-077-{user.login}"
            res = src_temp.with_user(user).with_company(self.company_1)._wms_merge_physical(
                dst_temp.id, correlation_id=corr_id
            )
            self.assertEqual(res["source_package_id"], src_temp.id)
            self.assertEqual(res["destination_package_id"], dst_temp.id)
            self.assertEqual(res["correlation_id"], corr_id)
            user_executions.append((user, corr_id))

        # 4. Operador real verificado discriminado exactamente por correlation_id
        for user, corr_id in user_executions:
            user_events = self.env["wms.inventory.event"].search([("correlation_id", "=", corr_id)])
            self.assertEqual(len(user_events), 2, f"Deben existir exactamente 2 eventos para {user.login}")
            self.assertEqual(set(user_events.mapped("event_type")), {"UNPACK", "PACK"})
            for ev in user_events:
                self.assertEqual(ev.operator_id, user, f"El evento {ev.id} debe estar atribuido a {user.login}")
                self.assertEqual(ev.company_id, self.company_1)

    # =========================================================================
    # TEST-HU-078: Concurrencia Pesimista Multi-Thread (3 Escenarios)
    # =========================================================================
    @mute_logger("odoo.sql_db")
    def test_hu_078_concurrency_deterministic_serialization(self):
        """TEST-HU-078: Concurrencia pesimista multi-thread en 3 escenarios: mismo par, dos fuentes/un destino, y cruzado A->B vs B->A."""
        # -------------------------------------------------------------------------
        # Escenario 1: Dos transacciones concurrentes sobre la MISMA pareja (A -> B)
        # -------------------------------------------------------------------------
        with self.env.registry.cursor() as cr_setup_1:
            env_setup_1 = api.Environment(cr_setup_1, 1, {})
            loc_conc_1 = env_setup_1["stock.location"].create({
                "name": "LOC-CONC-MERGE-1",
                "usage": "internal",
                "location_id": env_setup_1.ref("stock.stock_location_stock").location_id.id,
                "company_id": self.company_1.id,
            })
            prod_1 = env_setup_1["product.product"].create({
                "name": "Product Concurrency Merge 1",
                "is_storable": True,
            })
            pkg_src_1 = env_setup_1["stock.package"].create({"name": "PKG-C1-SRC", "hu_state": "OPEN"})
            pkg_dst_1 = env_setup_1["stock.package"].create({"name": "PKG-C1-DST", "hu_state": "OPEN"})
            env_setup_1["stock.quant"].create({
                "product_id": prod_1.id,
                "location_id": loc_conc_1.id,
                "quantity": 6.0,
                "package_id": pkg_src_1.id,
                "company_id": self.company_1.id,
            })
            env_setup_1["stock.quant"].create({
                "product_id": prod_1.id,
                "location_id": loc_conc_1.id,
                "quantity": 4.0,
                "package_id": pkg_dst_1.id,
                "company_id": self.company_1.id,
            })
            src_1_id = pkg_src_1.id
            dst_1_id = pkg_dst_1.id
            loc_1_id = loc_conc_1.id
            prod_1_id = prod_1.id
            tmpl_1_id = prod_1.product_tmpl_id.id
            cr_setup_1.commit()

        cr2_1 = self.env.registry.cursor()
        env2_1 = api.Environment(cr2_1, 1, {})
        pkg2_1 = env2_1["stock.package"].browse(src_1_id)

        try:
            barrier_t1_locked_1 = threading.Event()
            barrier_t2_calling_1 = threading.Event()
            t2_1_result = {}

            def thread_worker_1():
                try:
                    barrier_t1_locked_1.wait(timeout=10.0)
                    barrier_t2_calling_1.set()
                    try:
                        pkg2_1._wms_merge_physical(dst_1_id, correlation_id="CORR-CONC-1-TH2")
                        cr2_1.commit()
                        t2_1_result["success"] = True
                    except Exception as exc:
                        cr2_1.rollback()
                        t2_1_result["error_class"] = type(exc).__name__
                        t2_1_result["error_msg"] = str(exc)
                        t2_1_result["is_serialization_failure"] = (
                            type(exc).__name__ == "SerializationFailure"
                            or "could not serialize access" in str(exc)
                        )
                except BaseException as exc:
                    barrier_t2_calling_1.set()
                    t2_1_result["outer_error"] = str(exc)
                finally:
                    cr2_1.close()

            t2_1 = threading.Thread(target=thread_worker_1)
            t2_1.start()

            with self.env.registry.cursor() as cr1_1:
                env1_1 = api.Environment(cr1_1, 1, {})
                pkg1_1 = env1_1["stock.package"].browse(src_1_id)
                res1_1 = pkg1_1._wms_merge_physical(dst_1_id, correlation_id="CORR-CONC-1-TH1")
                self.assertEqual(res1_1.get("source_package_id"), src_1_id)
                self.assertEqual(res1_1.get("destination_package_id"), dst_1_id)

                barrier_t1_locked_1.set()
                self.assertTrue(barrier_t2_calling_1.wait(timeout=5.0))
                time.sleep(0.4)

                cr1_1.execute("SELECT COUNT(*) FROM pg_locks l WHERE NOT l.granted AND l.locktype = 'transactionid'")
                waiting_locks_1 = cr1_1.fetchone()[0]
                self.assertGreaterEqual(waiting_locks_1, 1, "T2-1 debe estar bloqueada en PostgreSQL esperando el lock de T1-1")

                cr1_1.commit()

            t2_1.join(timeout=10.0)
            self.assertFalse(t2_1.is_alive())

            self.assertFalse(t2_1_result.get("success"))
            self.assertTrue(t2_1_result.get("is_serialization_failure"), f"T2-1 debió recibir SerializationFailure: {t2_1_result}")
            self.assertEqual(t2_1_result.get("error_class"), "SerializationFailure")

            # Invariantes físicas del Escenario 1
            with self.env.registry.cursor() as cr_chk_1:
                env_chk_1 = api.Environment(cr_chk_1, 1, {})
                p_src_chk_1 = env_chk_1["stock.package"].browse(src_1_id)
                p_dst_chk_1 = env_chk_1["stock.package"].browse(dst_1_id)
                self.assertEqual(p_src_chk_1.hu_state, "EMPTY")
                self.assertEqual(len(p_src_chk_1.contained_quant_ids), 0)
                self.assertEqual(p_dst_chk_1.hu_state, "OPEN")
                self.assertEqual(sum(p_dst_chk_1.contained_quant_ids.mapped("quantity")), 10.0)  # 6 + 4 = 10

                # Verificación de ADR-019 exclusivo del ganador y cero efectos del perdedor
                events_win_1 = env_chk_1["wms.inventory.event"].search([("correlation_id", "=", "CORR-CONC-1-TH1")])
                self.assertEqual(len(events_win_1), 2)
                outbox_win_1 = env_chk_1["wms.outbox"].search([("correlation_id", "=", "CORR-CONC-1-TH1")])
                self.assertEqual(len(outbox_win_1), 1)
                self.assertEqual(outbox_win_1.event_name, "inventory.hu.merged")

                events_lose_1 = env_chk_1["wms.inventory.event"].search([("correlation_id", "=", "CORR-CONC-1-TH2")])
                self.assertEqual(len(events_lose_1), 0)
                outbox_lose_1 = env_chk_1["wms.outbox"].search([("correlation_id", "=", "CORR-CONC-1-TH2")])
                self.assertEqual(len(outbox_lose_1), 0)
        finally:
            with self.env.registry.cursor() as cr_clean_1:
                cr_clean_1.execute("DELETE FROM wms_outbox WHERE correlation_id IN (%s, %s)", ["CORR-CONC-1-TH1", "CORR-CONC-1-TH2"])
                cr_clean_1.execute("DELETE FROM wms_inventory_event WHERE correlation_id IN (%s, %s)", ["CORR-CONC-1-TH1", "CORR-CONC-1-TH2"])
                cr_clean_1.execute("DELETE FROM stock_package_history WHERE package_id IN (%s, %s)", [src_1_id, dst_1_id])
                cr_clean_1.execute("DELETE FROM stock_move_line WHERE package_id IN (%s, %s) OR result_package_id IN (%s, %s)", [src_1_id, dst_1_id, src_1_id, dst_1_id])
                cr_clean_1.execute("DELETE FROM stock_move WHERE product_id = %s", [prod_1_id])
                cr_clean_1.execute("DELETE FROM stock_quant WHERE package_id IN (%s, %s)", [src_1_id, dst_1_id])
                cr_clean_1.execute("DELETE FROM stock_package WHERE id IN (%s, %s)", [src_1_id, dst_1_id])
                cr_clean_1.execute("DELETE FROM product_product WHERE id = %s", [prod_1_id])
                cr_clean_1.execute("DELETE FROM product_template WHERE id = %s", [tmpl_1_id])
                cr_clean_1.execute("DELETE FROM stock_location WHERE id = %s", [loc_1_id])
                cr_clean_1.commit()
                cr_clean_1.execute("SELECT count(*) FROM stock_package WHERE id IN (%s, %s)", [src_1_id, dst_1_id])
                self.assertEqual(cr_clean_1.fetchone()[0], 0)
                cr_clean_1.execute("SELECT count(*) FROM stock_quant WHERE package_id IN (%s, %s)", [src_1_id, dst_1_id])
                self.assertEqual(cr_clean_1.fetchone()[0], 0)
                cr_clean_1.execute("SELECT count(*) FROM stock_move_line WHERE package_id IN (%s, %s) OR result_package_id IN (%s, %s)", [src_1_id, dst_1_id, src_1_id, dst_1_id])
                self.assertEqual(cr_clean_1.fetchone()[0], 0)
                cr_clean_1.execute("SELECT count(*) FROM wms_outbox WHERE correlation_id IN (%s, %s)", ["CORR-CONC-1-TH1", "CORR-CONC-1-TH2"])
                self.assertEqual(cr_clean_1.fetchone()[0], 0)
                cr_clean_1.execute("SELECT count(*) FROM wms_inventory_event WHERE correlation_id IN (%s, %s)", ["CORR-CONC-1-TH1", "CORR-CONC-1-TH2"])
                self.assertEqual(cr_clean_1.fetchone()[0], 0)

        # -------------------------------------------------------------------------
        # Escenario 2: Dos fuentes compitiendo por el MISMO destino (A -> C y B -> C)
        # -------------------------------------------------------------------------
        with self.env.registry.cursor() as cr_setup_2:
            env_setup_2 = api.Environment(cr_setup_2, 1, {})
            loc_conc_2 = env_setup_2["stock.location"].create({
                "name": "LOC-CONC-MERGE-2",
                "usage": "internal",
                "location_id": env_setup_2.ref("stock.stock_location_stock").location_id.id,
                "company_id": self.company_1.id,
            })
            prod_2 = env_setup_2["product.product"].create({
                "name": "Product Concurrency Merge 2",
                "is_storable": True,
            })
            pkg_src2_a = env_setup_2["stock.package"].create({"name": "PKG-C2-SRC-A", "hu_state": "OPEN"})
            pkg_src2_b = env_setup_2["stock.package"].create({"name": "PKG-C2-SRC-B", "hu_state": "OPEN"})
            pkg_dst_2 = env_setup_2["stock.package"].create({"name": "PKG-C2-DST", "hu_state": "OPEN"})
            env_setup_2["stock.quant"].create({
                "product_id": prod_2.id,
                "location_id": loc_conc_2.id,
                "quantity": 5.0,
                "package_id": pkg_src2_a.id,
                "company_id": self.company_1.id,
            })
            env_setup_2["stock.quant"].create({
                "product_id": prod_2.id,
                "location_id": loc_conc_2.id,
                "quantity": 3.0,
                "package_id": pkg_src2_b.id,
                "company_id": self.company_1.id,
            })
            env_setup_2["stock.quant"].create({
                "product_id": prod_2.id,
                "location_id": loc_conc_2.id,
                "quantity": 2.0,
                "package_id": pkg_dst_2.id,
                "company_id": self.company_1.id,
            })
            src2_a_id = pkg_src2_a.id
            src2_b_id = pkg_src2_b.id
            dst_2_id = pkg_dst_2.id
            loc_2_id = loc_conc_2.id
            prod_2_id = prod_2.id
            tmpl_2_id = prod_2.product_tmpl_id.id
            cr_setup_2.commit()

        cr2_2 = self.env.registry.cursor()
        env2_2 = api.Environment(cr2_2, 1, {})
        pkg2_2 = env2_2["stock.package"].browse(src2_b_id)

        try:
            barrier_t1_locked_2 = threading.Event()
            barrier_t2_calling_2 = threading.Event()
            t2_2_result = {}

            def thread_worker_2():
                try:
                    barrier_t1_locked_2.wait(timeout=10.0)
                    barrier_t2_calling_2.set()
                    try:
                        pkg2_2._wms_merge_physical(dst_2_id, correlation_id="CORR-CONC-2-TH2")
                        cr2_2.commit()
                        t2_2_result["success"] = True
                    except Exception as exc:
                        cr2_2.rollback()
                        t2_2_result["error_class"] = type(exc).__name__
                        t2_2_result["error_msg"] = str(exc)
                        t2_2_result["is_serialization_failure"] = (
                            type(exc).__name__ == "SerializationFailure"
                            or "could not serialize access" in str(exc)
                        )
                except BaseException as exc:
                    barrier_t2_calling_2.set()
                    t2_2_result["outer_error"] = str(exc)
                finally:
                    cr2_2.close()

            t2_2 = threading.Thread(target=thread_worker_2)
            t2_2.start()

            with self.env.registry.cursor() as cr1_2:
                env1_2 = api.Environment(cr1_2, 1, {})
                pkg1_2 = env1_2["stock.package"].browse(src2_a_id)
                res1_2 = pkg1_2._wms_merge_physical(dst_2_id, correlation_id="CORR-CONC-2-TH1")
                self.assertEqual(res1_2.get("source_package_id"), src2_a_id)
                self.assertEqual(res1_2.get("destination_package_id"), dst_2_id)

                barrier_t1_locked_2.set()
                self.assertTrue(barrier_t2_calling_2.wait(timeout=5.0))
                time.sleep(0.4)

                cr1_2.execute("SELECT COUNT(*) FROM pg_locks l WHERE NOT l.granted AND l.locktype = 'transactionid'")
                waiting_locks_2 = cr1_2.fetchone()[0]
                self.assertGreaterEqual(waiting_locks_2, 1, "T2-2 debe estar bloqueada en PostgreSQL esperando el lock de destino de T1-2")

                cr1_2.commit()

            t2_2.join(timeout=10.0)
            self.assertFalse(t2_2.is_alive())

            self.assertFalse(t2_2_result.get("success"))
            self.assertTrue(t2_2_result.get("is_serialization_failure"), f"T2-2 debió recibir SerializationFailure: {t2_2_result}")
            self.assertEqual(t2_2_result.get("error_class"), "SerializationFailure")

            # Invariantes físicas del Escenario 2
            with self.env.registry.cursor() as cr_chk_2:
                env_chk_2 = api.Environment(cr_chk_2, 1, {})
                p_src2_a_chk = env_chk_2["stock.package"].browse(src2_a_id)
                p_src2_b_chk = env_chk_2["stock.package"].browse(src2_b_id)
                p_dst2_chk = env_chk_2["stock.package"].browse(dst_2_id)
                self.assertEqual(p_src2_a_chk.hu_state, "EMPTY")
                self.assertEqual(len(p_src2_a_chk.contained_quant_ids), 0)
                self.assertEqual(p_src2_b_chk.hu_state, "OPEN")
                self.assertEqual(sum(p_src2_b_chk.contained_quant_ids.mapped("quantity")), 3.0)
                self.assertEqual(p_dst2_chk.hu_state, "OPEN")
                self.assertEqual(sum(p_dst2_chk.contained_quant_ids.mapped("quantity")), 7.0)  # 5 + 2 = 7

                # Verificación de ADR-019 exclusivo del ganador y cero efectos del perdedor
                events_win_2 = env_chk_2["wms.inventory.event"].search([("correlation_id", "=", "CORR-CONC-2-TH1")])
                self.assertEqual(len(events_win_2), 2)
                outbox_win_2 = env_chk_2["wms.outbox"].search([("correlation_id", "=", "CORR-CONC-2-TH1")])
                self.assertEqual(len(outbox_win_2), 1)

                events_lose_2 = env_chk_2["wms.inventory.event"].search([("correlation_id", "=", "CORR-CONC-2-TH2")])
                self.assertEqual(len(events_lose_2), 0)
                outbox_lose_2 = env_chk_2["wms.outbox"].search([("correlation_id", "=", "CORR-CONC-2-TH2")])
                self.assertEqual(len(outbox_lose_2), 0)
        finally:
            with self.env.registry.cursor() as cr_clean_2:
                cr_clean_2.execute("DELETE FROM wms_outbox WHERE correlation_id IN (%s, %s)", ["CORR-CONC-2-TH1", "CORR-CONC-2-TH2"])
                cr_clean_2.execute("DELETE FROM wms_inventory_event WHERE correlation_id IN (%s, %s)", ["CORR-CONC-2-TH1", "CORR-CONC-2-TH2"])
                cr_clean_2.execute("DELETE FROM stock_package_history WHERE package_id IN (%s, %s, %s)", [src2_a_id, src2_b_id, dst_2_id])
                cr_clean_2.execute("DELETE FROM stock_move_line WHERE package_id IN (%s, %s, %s) OR result_package_id IN (%s, %s, %s)", [src2_a_id, src2_b_id, dst_2_id, src2_a_id, src2_b_id, dst_2_id])
                cr_clean_2.execute("DELETE FROM stock_move WHERE product_id = %s", [prod_2_id])
                cr_clean_2.execute("DELETE FROM stock_quant WHERE package_id IN (%s, %s, %s)", [src2_a_id, src2_b_id, dst_2_id])
                cr_clean_2.execute("DELETE FROM stock_package WHERE id IN (%s, %s, %s)", [src2_a_id, src2_b_id, dst_2_id])
                cr_clean_2.execute("DELETE FROM product_product WHERE id = %s", [prod_2_id])
                cr_clean_2.execute("DELETE FROM product_template WHERE id = %s", [tmpl_2_id])
                cr_clean_2.execute("DELETE FROM stock_location WHERE id = %s", [loc_2_id])
                cr_clean_2.commit()
                cr_clean_2.execute("SELECT count(*) FROM stock_package WHERE id IN (%s, %s, %s)", [src2_a_id, src2_b_id, dst_2_id])
                self.assertEqual(cr_clean_2.fetchone()[0], 0)
                cr_clean_2.execute("SELECT count(*) FROM stock_quant WHERE package_id IN (%s, %s, %s)", [src2_a_id, src2_b_id, dst_2_id])
                self.assertEqual(cr_clean_2.fetchone()[0], 0)
                cr_clean_2.execute("SELECT count(*) FROM stock_move_line WHERE package_id IN (%s, %s, %s) OR result_package_id IN (%s, %s, %s)", [src2_a_id, src2_b_id, dst_2_id, src2_a_id, src2_b_id, dst_2_id])
                self.assertEqual(cr_clean_2.fetchone()[0], 0)
                cr_clean_2.execute("SELECT count(*) FROM wms_outbox WHERE correlation_id IN (%s, %s)", ["CORR-CONC-2-TH1", "CORR-CONC-2-TH2"])
                self.assertEqual(cr_clean_2.fetchone()[0], 0)
                cr_clean_2.execute("SELECT count(*) FROM wms_inventory_event WHERE correlation_id IN (%s, %s)", ["CORR-CONC-2-TH1", "CORR-CONC-2-TH2"])
                self.assertEqual(cr_clean_2.fetchone()[0], 0)

        # -------------------------------------------------------------------------
        # Escenario 3: Operaciones Recíprocas Concurrentes Cruzadas (A -> B frente a B -> A)
        # -------------------------------------------------------------------------
        with self.env.registry.cursor() as cr_setup_3:
            env_setup_3 = api.Environment(cr_setup_3, 1, {})
            loc_conc_3 = env_setup_3["stock.location"].create({
                "name": "LOC-CONC-MERGE-3",
                "usage": "internal",
                "location_id": env_setup_3.ref("stock.stock_location_stock").location_id.id,
                "company_id": self.company_1.id,
            })
            prod_3 = env_setup_3["product.product"].create({
                "name": "Product Concurrency Merge 3",
                "is_storable": True,
            })
            pkg_cross_a = env_setup_3["stock.package"].create({"name": "PKG-C3-A", "hu_state": "OPEN"})
            pkg_cross_b = env_setup_3["stock.package"].create({"name": "PKG-C3-B", "hu_state": "OPEN"})
            env_setup_3["stock.quant"].create({
                "product_id": prod_3.id,
                "location_id": loc_conc_3.id,
                "quantity": 6.0,
                "package_id": pkg_cross_a.id,
                "company_id": self.company_1.id,
            })
            env_setup_3["stock.quant"].create({
                "product_id": prod_3.id,
                "location_id": loc_conc_3.id,
                "quantity": 4.0,
                "package_id": pkg_cross_b.id,
                "company_id": self.company_1.id,
            })
            cross_a_id = pkg_cross_a.id
            cross_b_id = pkg_cross_b.id
            loc_3_id = loc_conc_3.id
            prod_3_id = prod_3.id
            tmpl_3_id = prod_3.product_tmpl_id.id
            cr_setup_3.commit()

        cr2_3 = self.env.registry.cursor()
        env2_3 = api.Environment(cr2_3, 1, {})
        pkg2_3 = env2_3["stock.package"].browse(cross_b_id)  # T2 intenta B -> A

        try:
            barrier_t1_locked_3 = threading.Event()
            barrier_t2_calling_3 = threading.Event()
            t2_3_result = {}

            def thread_worker_3():
                try:
                    barrier_t1_locked_3.wait(timeout=10.0)
                    barrier_t2_calling_3.set()
                    try:
                        pkg2_3._wms_merge_physical(cross_a_id, correlation_id="CORR-CONC-3-TH2")
                        cr2_3.commit()
                        t2_3_result["success"] = True
                    except Exception as exc:
                        cr2_3.rollback()
                        t2_3_result["error_class"] = type(exc).__name__
                        t2_3_result["error_msg"] = str(exc)
                        t2_3_result["is_serialization_failure"] = (
                            type(exc).__name__ == "SerializationFailure"
                            or "could not serialize access" in str(exc)
                        )
                except BaseException as exc:
                    barrier_t2_calling_3.set()
                    t2_3_result["outer_error"] = str(exc)
                finally:
                    cr2_3.close()

            t2_3 = threading.Thread(target=thread_worker_3)
            t2_3.start()

            with self.env.registry.cursor() as cr1_3:
                env1_3 = api.Environment(cr1_3, 1, {})
                pkg1_3 = env1_3["stock.package"].browse(cross_a_id)  # T1 intenta A -> B
                res1_3 = pkg1_3._wms_merge_physical(cross_b_id, correlation_id="CORR-CONC-3-TH1")
                self.assertEqual(res1_3.get("source_package_id"), cross_a_id)
                self.assertEqual(res1_3.get("destination_package_id"), cross_b_id)

                barrier_t1_locked_3.set()
                self.assertTrue(barrier_t2_calling_3.wait(timeout=5.0))
                time.sleep(0.4)

                cr1_3.execute("SELECT COUNT(*) FROM pg_locks l WHERE NOT l.granted AND l.locktype = 'transactionid'")
                waiting_locks_3 = cr1_3.fetchone()[0]
                self.assertGreaterEqual(waiting_locks_3, 1, "T2-3 debe estar bloqueada esperando el lock ordenado sin deadlock")

                cr1_3.commit()

            t2_3.join(timeout=10.0)
            self.assertFalse(t2_3.is_alive())

            self.assertFalse(t2_3_result.get("success"))
            self.assertTrue(t2_3_result.get("is_serialization_failure"), f"T2-3 debió recibir SerializationFailure: {t2_3_result}")
            self.assertEqual(t2_3_result.get("error_class"), "SerializationFailure")

            # Invariantes físicas del Escenario 3
            with self.env.registry.cursor() as cr_chk_3:
                env_chk_3 = api.Environment(cr_chk_3, 1, {})
                p_a_chk = env_chk_3["stock.package"].browse(cross_a_id)
                p_b_chk = env_chk_3["stock.package"].browse(cross_b_id)
                self.assertEqual(p_a_chk.hu_state, "EMPTY")
                self.assertEqual(len(p_a_chk.contained_quant_ids), 0)
                self.assertEqual(p_b_chk.hu_state, "OPEN")
                self.assertEqual(sum(p_b_chk.contained_quant_ids.mapped("quantity")), 10.0)

                # Verificación de ADR-019 exclusivo del ganador y cero efectos del perdedor
                events_win_3 = env_chk_3["wms.inventory.event"].search([("correlation_id", "=", "CORR-CONC-3-TH1")])
                self.assertEqual(len(events_win_3), 2)
                outbox_win_3 = env_chk_3["wms.outbox"].search([("correlation_id", "=", "CORR-CONC-3-TH1")])
                self.assertEqual(len(outbox_win_3), 1)

                events_lose_3 = env_chk_3["wms.inventory.event"].search([("correlation_id", "=", "CORR-CONC-3-TH2")])
                self.assertEqual(len(events_lose_3), 0)
                outbox_lose_3 = env_chk_3["wms.outbox"].search([("correlation_id", "=", "CORR-CONC-3-TH2")])
                self.assertEqual(len(outbox_lose_3), 0)
        finally:
            with self.env.registry.cursor() as cr_clean_3:
                cr_clean_3.execute("DELETE FROM wms_outbox WHERE correlation_id IN (%s, %s)", ["CORR-CONC-3-TH1", "CORR-CONC-3-TH2"])
                cr_clean_3.execute("DELETE FROM wms_inventory_event WHERE correlation_id IN (%s, %s)", ["CORR-CONC-3-TH1", "CORR-CONC-3-TH2"])
                cr_clean_3.execute("DELETE FROM stock_package_history WHERE package_id IN (%s, %s)", [cross_a_id, cross_b_id])
                cr_clean_3.execute("DELETE FROM stock_move_line WHERE package_id IN (%s, %s) OR result_package_id IN (%s, %s)", [cross_a_id, cross_b_id, cross_a_id, cross_b_id])
                cr_clean_3.execute("DELETE FROM stock_move WHERE product_id = %s", [prod_3_id])
                cr_clean_3.execute("DELETE FROM stock_quant WHERE package_id IN (%s, %s)", [cross_a_id, cross_b_id])
                cr_clean_3.execute("DELETE FROM stock_package WHERE id IN (%s, %s)", [cross_a_id, cross_b_id])
                cr_clean_3.execute("DELETE FROM product_product WHERE id = %s", [prod_3_id])
                cr_clean_3.execute("DELETE FROM product_template WHERE id = %s", [tmpl_3_id])
                cr_clean_3.execute("DELETE FROM stock_location WHERE id = %s", [loc_3_id])
                cr_clean_3.commit()
                cr_clean_3.execute("SELECT count(*) FROM stock_package WHERE id IN (%s, %s)", [cross_a_id, cross_b_id])
                self.assertEqual(cr_clean_3.fetchone()[0], 0)
                cr_clean_3.execute("SELECT count(*) FROM stock_quant WHERE package_id IN (%s, %s)", [cross_a_id, cross_b_id])
                self.assertEqual(cr_clean_3.fetchone()[0], 0)
                cr_clean_3.execute("SELECT count(*) FROM stock_move_line WHERE package_id IN (%s, %s) OR result_package_id IN (%s, %s)", [cross_a_id, cross_b_id, cross_a_id, cross_b_id])
                self.assertEqual(cr_clean_3.fetchone()[0], 0)
                cr_clean_3.execute("SELECT count(*) FROM wms_outbox WHERE correlation_id IN (%s, %s)", ["CORR-CONC-3-TH1", "CORR-CONC-3-TH2"])
                self.assertEqual(cr_clean_3.fetchone()[0], 0)
                cr_clean_3.execute("SELECT count(*) FROM wms_inventory_event WHERE correlation_id IN (%s, %s)", ["CORR-CONC-3-TH1", "CORR-CONC-3-TH2"])
                self.assertEqual(cr_clean_3.fetchone()[0], 0)
