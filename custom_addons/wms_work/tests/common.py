# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.tests.common import TransactionCase


class WorkCommon(TransactionCase):
    """Clase base común para tests de Work Engine (WORK-002)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Company = cls.env["res.company"]
        cls.Warehouse = cls.env["stock.warehouse"]
        cls.Location = cls.env["stock.location"]
        cls.Product = cls.env["product.product"]
        cls.Uom = cls.env["uom.uom"]
        cls.Lot = cls.env["stock.lot"]
        cls.Package = cls.env["stock.package"]
        cls.Partner = cls.env["res.partner"]
        cls.Users = cls.env["res.users"]

        # Compañías
        cls.company_a = cls.env.company
        cls.company_b = cls.Company.create({
            "name": "WMS Beta Company",
            "currency_id": cls.company_a.currency_id.id,
        })

        # Almacenes
        cls.warehouse_a = cls.Warehouse.search(
            [("company_id", "=", cls.company_a.id)], limit=1
        )
        if not cls.warehouse_a:
            cls.warehouse_a = cls.Warehouse.create({
                "name": "WH Alpha",
                "code": "WHA",
                "company_id": cls.company_a.id,
            })

        cls.warehouse_b = cls.Warehouse.create({
            "name": "WH Beta",
            "code": "WHB",
            "company_id": cls.company_b.id,
        })

        # Ubicaciones
        cls.loc_source_a = cls.Location.create({
            "name": "LOC-SRC-A",
            "usage": "internal",
            "company_id": cls.company_a.id,
            "wms_location_role": "STORAGE",
        })
        cls.loc_dest_a = cls.Location.create({
            "name": "LOC-DST-A",
            "usage": "internal",
            "company_id": cls.company_a.id,
            "wms_location_role": "PICK_FACE",
        })
        cls.loc_source_b = cls.Location.create({
            "name": "LOC-SRC-B",
            "usage": "internal",
            "company_id": cls.company_b.id,
            "wms_location_role": "STORAGE",
        })
        cls.loc_dest_b = cls.Location.create({
            "name": "LOC-DST-B",
            "usage": "internal",
            "company_id": cls.company_b.id,
            "wms_location_role": "PICK_FACE",
        })

        # UOMs
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.uom_dozen = cls.env.ref("uom.product_uom_dozen")
        cls.uom_kg = cls.env.ref("uom.product_uom_kgm")
        cls.uom_gram = cls.env.ref("uom.product_uom_gram")
        cls.uom_meter = cls.env.ref("uom.product_uom_meter")

        # Productos
        cls.product_a = cls.Product.create({
            "name": "Product Alpha Work",
            "type": "consu",
            "is_storable": True,
            "uom_id": cls.uom_unit.id,
            "company_id": cls.company_a.id,
        })
        cls.env["product.uom"].create({
            "product_id": cls.product_a.id,
            "uom_id": cls.uom_dozen.id,
            "barcode": "BC-DOZEN-ALPHA",
        })

        cls.product_b = cls.Product.create({
            "name": "Product Beta Work",
            "type": "consu",
            "is_storable": True,
            "uom_id": cls.uom_kg.id,
            "company_id": cls.company_a.id,
        })

        # Lotes
        cls.lot_a1 = cls.Lot.create({
            "name": "LOT-A1",
            "product_id": cls.product_a.id,
            "company_id": cls.company_a.id,
        })
        cls.lot_b1 = cls.Lot.create({
            "name": "LOT-B1",
            "product_id": cls.product_b.id,
            "company_id": cls.company_a.id,
        })

        # Paquetes
        cls.package_a1 = cls.Package.create({
            "name": "PKG-WORK-A1",
            "company_id": cls.company_a.id,
        })
        cls.package_a2 = cls.Package.create({
            "name": "PKG-WORK-A2",
            "company_id": cls.company_a.id,
        })

        # Propietario
        cls.partner_a = cls.Partner.create({
            "name": "Partner Alpha 3PL",
            "company_id": cls.company_a.id,
        })

        # Grupos de seguridad
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_operator = cls.env.ref("wms_core.group_wms_operator")
        cls.group_supervisor = cls.env.ref("wms_core.group_wms_supervisor")
        cls.group_manager = cls.env.ref("wms_core.group_wms_manager")
        cls.group_system = cls.env.ref("base.group_system")
        cls.group_stock_user = cls.env.ref("stock.group_stock_user")

        # Usuarios RBAC
        cls.user_operator = cls.Users.create({
            "name": "WMS Work Operator",
            "login": "wms_work_operator",
            "email": "wms_work_operator@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_operator.id])],
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
        })

        cls.user_supervisor = cls.Users.create({
            "name": "WMS Work Supervisor",
            "login": "wms_work_supervisor",
            "email": "wms_work_supervisor@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_supervisor.id])],
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
        })

        cls.user_manager = cls.Users.create({
            "name": "WMS Work Manager",
            "login": "wms_work_manager",
            "email": "wms_work_manager@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_manager.id])],
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
        })

        cls.user_system = cls.Users.create({
            "name": "WMS Work System Admin",
            "login": "wms_work_system",
            "email": "wms_work_system@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_system.id])],
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id, cls.company_b.id])],
        })

        cls.user_plain = cls.Users.create({
            "name": "Plain Internal User",
            "login": "wms_work_plain",
            "email": "wms_work_plain@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id])],
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
        })

        cls.user_stock_user = cls.Users.create({
            "name": "Stock Only User",
            "login": "wms_work_stock_user",
            "email": "wms_work_stock_user@test.com",
            "group_ids": [(6, 0, [cls.group_internal.id, cls.group_stock_user.id])],
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
        })
