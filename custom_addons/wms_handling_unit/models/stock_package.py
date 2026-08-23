import math
from odoo import fields, models
from odoo.exceptions import AccessError, ValidationError


class StockPackage(models.Model):
    """Extensión WMS del modelo nativo stock.package de Odoo 19 (ADR-013).

    HU-002: Incorpora metadata operativa y de ciclo de vida WMS:
        - hu_state: Estado de ciclo de vida WMS (opcional, sin default).
        - hu_class: Clasificación operacional de la unidad de manipulación (opcional, sin default).

    HU-003B: Asignación explícita e idempotente de identificadores GS1 SSCC-18:
        - assign_sscc(sscc_sequence_id): Vincula un SSCC generado por wms.sscc.sequence al campo nativo name.

    HU-004B: Primitive físico transaccional para desempaque de inventario (ADR-019):
        - _wms_unpack_physical(quant_id, quantity, correlation_id=None): Ejecuta la mutación física vía stock.move
          y coordina de forma atómica wms.inventory.event (UNPACK) + wms.outbox (inventory.hu.unpacked).

    HU-004C: Primitive físico transaccional para división (split) de inventario entre Handling Units (ADR-019):
        - _wms_split_physical(quant_id, quantity, destination_package_id, correlation_id=None): Ejecuta la mutación
          física directa paquete a paquete vía stock.move, transiciona el destino a OPEN, preserva la fuente en OPEN
          y coordina de forma atómica 2 eventos (UNPACK en fuente, PACK en destino) + 1 outbox (inventory.hu.split).
    """

    _inherit = "stock.package"

    hu_state = fields.Selection(
        selection=[
            ("EMPTY", "Vacía"),
            ("OPEN", "Abierta"),
            ("CLOSED", "Cerrada"),
            ("IN_TRANSIT", "En tránsito"),
            ("SHIPPED", "Despachada"),
            ("RETURNED", "Devuelta"),
            ("DISPOSED", "Dada de baja"),
        ],
        string="Estado HU",
        index=True,
        copy=False,
        help="Estado de ciclo de vida WMS cuando el paquete ha sido adoptado por un flujo WMS. "
             "False indica que el ciclo de vida WMS todavía no ha sido inicializado.",
    )

    hu_class = fields.Selection(
        selection=[
            ("PALLET", "Pallet"),
            ("CASE", "Caja"),
            ("TOTE", "Tote"),
            ("CONTAINER", "Contenedor"),
            ("MIXED", "Mixta"),
        ],
        string="Clase HU",
        index=True,
        copy=False,
        help="Clasificación operacional de la unidad de manipulación en el WMS. "
             "False indica que todavía no tiene clasificación asignada.",
    )

    def assign_sscc(self, sscc_sequence_id):
        """Asignar de forma explícita e idempotente un código GS1 SSCC-18 al paquete.

        Reemplaza la referencia genérica 'name' por un SSCC-18 generado por el asignador,
        reutilizando la validación nativa valid_sscc de Odoo 19.

        :param int sscc_sequence_id: ID entero positivo del registro wms.sscc.sequence.
        :return str: Referencia final del paquete (self.name).
        """
        self.ensure_one()
        self.check_access("write")

        # 1. Validar tipo y formato estricto del ID
        if isinstance(sscc_sequence_id, bool) or not isinstance(sscc_sequence_id, int) or sscc_sequence_id <= 0:
            raise ValidationError("El identificador de la secuencia SSCC debe ser un entero positivo.")

        # 2. Idempotencia: si ya tiene SSCC válido, retornar sin modificar ni consumir allocator
        if self.valid_sscc:
            return self.name

        # 3. Resolver y validar existencia del asignador
        allocator = self.env["wms.sscc.sequence"].browse(sscc_sequence_id).exists()
        if not allocator or len(allocator) != 1:
            raise ValidationError("La secuencia SSCC especificada no existe.")

        # 4. Verificar permiso de lectura sobre el asignador
        allocator.check_access("read")

        # 5. Validar que la compañía del paquete esté resuelta
        if not self.company_id:
            raise ValidationError("No se puede asignar un SSCC a un paquete sin compañía resuelta.")

        # 6. Validar coherencia de compañía entre paquete y asignador
        if self.company_id != allocator.company_id:
            raise ValidationError(
                f"La compañía del paquete ({self.company_id.name}) no coincide con la del asignador SSCC ({allocator.company_id.name})."
            )

        # 7. Generar SSCC-18 a través del allocator
        sscc = allocator.next_sscc()

        # 8. Guard de colisión sobre paquetes visibles al llamador
        existing_collision = self.search([
            ("name", "=", sscc),
            ("id", "!=", self.id),
        ], limit=1)
        if existing_collision:
            raise ValidationError(f"Colisión de SSCC: el código '{sscc}' ya está asignado a otro paquete visible.")

        # 9. Asignar el SSCC al name nativo
        self.write({"name": sscc})

        # 10. Validar que el campo nativo valid_sscc haya quedado en True
        if not self.valid_sscc:
            raise ValidationError(f"Error interno: el SSCC asignado '{self.name}' no es válido según el algoritmo GS1.")

        return self.name

    def _wms_pack_physical(self, quant_id, quantity, correlation_id=None):
        """Primitive físico transaccional para empaquetar inventario suelto en una Handling Unit (ADR-019).

        Ejecuta la mutación física mediante el mecanismo nativo de relocalización de stock de Odoo 19
        y coordina la persistencia atómica de wms.inventory.event (PACK) y wms.outbox (inventory.hu.packed)
        bajo un mismo correlation_id sin apropiarse de la transacción PostgreSQL del llamador.

        :param int quant_id: ID entero positivo del quant origen suelto (transitorio, no persistido como FK).
        :param float quantity: Cantidad positiva en la UoM del producto.
        :param str correlation_id: Opcional, identificador de correlación para el journal y outbox.
        :return dict: {'package_id': int, 'correlation_id': str}
        """
        self.ensure_one()

        # 1. RBAC Guard: el llamador debe pertenecer al grupo WMS Operator (o superior / admin)
        if not (
            self.env.user.has_group("wms_core.group_wms_operator")
            or self.env.user.has_group("base.group_system")
        ):
            raise AccessError("No tiene permisos para ejecutar operaciones WMS de empaque.")

        # 2. Preflight de argumentos
        if isinstance(quant_id, bool) or not isinstance(quant_id, int) or quant_id <= 0:
            raise ValidationError("El identificador del quant debe ser un entero positivo.")

        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, (int, float))
            or math.isnan(quantity)
            or math.isinf(quantity)
        ):
            raise ValidationError("La cantidad a empaquetar debe ser un valor numérico válido.")

        if correlation_id is not None:
            if not isinstance(correlation_id, str) or not correlation_id.strip():
                raise ValidationError("correlation_id debe ser una cadena de texto no vacía.")

        # 3. Row locks en orden estricto (package FOR UPDATE -> quant FOR UPDATE)
        self.env.cr.execute(
            "SELECT id FROM stock_package WHERE id = %s FOR UPDATE",
            [self.id],
        )
        if not self.env.cr.fetchone():
            raise ValidationError("La HU ya no existe.")

        self.env.cr.execute(
            "SELECT id FROM stock_quant WHERE id = %s FOR UPDATE",
            [quant_id],
        )
        if not self.env.cr.fetchone():
            raise ValidationError("El quant especificado no existe.")

        # 4. Invalidación de caché tras la adquisición de locks
        self.invalidate_recordset([
            "hu_state",
            "company_id",
            "location_id",
            "quant_ids",
            "contained_quant_ids",
            "package_type_id",
            "parent_package_id",
            "child_package_ids",
        ])

        quant = self.env["stock.quant"].browse(quant_id)
        quant.invalidate_recordset([
            "quantity",
            "reserved_quantity",
            "available_quantity",
            "package_id",
            "location_id",
            "company_id",
            "product_id",
            "lot_id",
            "owner_id",
        ])

        # 5. Scope guard post-lock: rechazar paquetes anidados (HU-004A opera sólo sobre HU top-level plana)
        if self.parent_package_id or self.child_package_ids:
            raise ValidationError("HU-004A opera únicamente sobre HU plana (top-level sin anidamiento).")

        # 6. Lifecycle guard de la HU destino y validación de contenido vacío
        if self.hu_state and self.hu_state not in ("EMPTY", "OPEN"):
            raise ValidationError(
                f"No se puede empaquetar en una HU en estado '{self.hu_state}'."
            )
        if self.hu_state in (False, "EMPTY") and self.contained_quant_ids:
            raise ValidationError(
                "Una Handling Unit en estado 'EMPTY' (o sin inicializar) no puede tener contenido preexistente."
            )

        # 7. Guards de compañía del quant y del package
        if not quant.company_id:
            raise ValidationError("El quant debe tener una compañía asignada.")

        if quant.company_id not in self.env.user.company_ids:
            raise AccessError("No tiene acceso a la compañía del inventario origen.")

        if self.company_id:
            if self.company_id != quant.company_id:
                raise ValidationError(
                    f"La compañía de la HU ({self.company_id.name}) no coincide con la del inventario ({quant.company_id.name})."
                )
        elif self.contained_quant_ids:
            raise ValidationError("La HU posee contenido pero su compañía no está resuelta.")

        # 8. Guards del quant origen (loose stock, internal location, reservations, tracking, UoM)
        if quant.package_id:
            raise ValidationError("El quant ya se encuentra dentro de un paquete. Use unpack, split o merge.")

        if quant.location_id.usage != "internal":
            raise ValidationError("El inventario a empaquetar debe estar en una ubicación interna.")

        if self.location_id and self.location_id != quant.location_id:
            raise ValidationError(
                f"La ubicación de la HU ({self.location_id.display_name}) no coincide con la del quant ({quant.location_id.display_name})."
            )

        product = quant.product_id
        uom = product.uom_id

        if uom.compare(quantity, 0.0) <= 0:
            raise ValidationError("La cantidad a empaquetar debe ser estrictamente positiva.")

        if not uom.is_zero(quant.reserved_quantity):
            raise ValidationError("No se puede empaquetar inventario con reservas activas.")

        if uom.compare(quantity, quant.available_quantity) > 0:
            raise ValidationError(
                f"La cantidad solicitada ({quantity}) excede la disponibilidad ({quant.available_quantity})."
            )

        if product.tracking != "none" and not quant.lot_id:
            raise ValidationError(f"El producto '{product.display_name}' requiere seguimiento por lote/serie.")

        if product.tracking == "serial" and uom.compare(quantity, 1.0) != 0:
            raise ValidationError("Los productos con seguimiento por número de serie deben empaquetarse en cantidad exacta de 1.0.")

        # 9. Operational Inventory Block guard (sin sudo)
        is_blocked = self.env["wms.inventory.block"].is_blocked(
            company_id=quant.company_id,
            product_id=product,
            location_id=quant.location_id,
            lot_id=quant.lot_id or False,
            package_id=self,
            owner_id=quant.owner_id or False,
        )
        if is_blocked:
            raise ValidationError("El inventario o paquete destino se encuentra bloqueado operacionalmente.")

        # 10. PLM (Product Logistics Master) HU Type Guard (sin sudo)
        # Consultamos directamente la tabla de relación M2M sin ORM traversal
        # para obtener los IDs permitidos sin disparar comprobaciones de ACL sobre el comodel stock.package.type
        # ni elevar privilegios con sudo().
        logistics = self.env["wms.product.logistics"].search([
            ("product_tmpl_id", "=", product.product_tmpl_id.id),
            "|",
            ("company_id", "=", quant.company_id.id),
            ("company_id", "=", False),
        ], limit=1)
        if logistics:
            self.env.cr.execute(
                "SELECT stock_package_type_id FROM stock_package_type_wms_product_logistics_rel WHERE wms_product_logistics_id = %s",
                [logistics.id],
            )
            allowed_type_ids = [row[0] for row in self.env.cr.fetchall()]
            if allowed_type_ids:
                package_type_id = self.package_type_id.id
                if not package_type_id:
                    raise ValidationError(
                        f"El producto '{product.display_name}' exige un tipo de HU permitido, pero el paquete destino no tiene tipo asignado."
                    )
                if package_type_id not in allowed_type_ids:
                    raise ValidationError(
                        f"El tipo de paquete asignado a la HU no está permitido para el producto '{product.display_name}'."
                    )

        # 11. Captura de metadatos de snapshot antes de la mutación
        product_id = product.id
        lot_id = quant.lot_id.id or False
        owner_id = quant.owner_id.id or False
        location_id = quant.location_id.id
        company_id = quant.company_id.id
        warehouse_id = quant.location_id.warehouse_id.id or False
        uom_id = uom.id
        package_ref = self.name

        # 12. Mutación física nativa con narrow sudo
        quant_sudo = quant.sudo()
        package_sudo = self.sudo()

        move_vals = quant_sudo.with_context(
            inventory_name="WMS Physical Pack"
        )._get_inventory_move_values(
            quantity,
            quant.location_id,
            quant.location_id,
            package_id=False,
            package_dest_id=package_sudo,
        )
        move = self.env["stock.move"].sudo().create(move_vals)
        move._action_done()

        if package_sudo.hu_state != "OPEN":
            package_sudo.hu_state = "OPEN"

        # 13. Persistencia de Event + Outbox en el entorno del usuario original (NO sudo)
        event_vals = {
            "company_id": company_id,
            "event_type": "PACK",
            "product_id": product_id,
            "lot_id": lot_id,
            "package_id": self.id,
            "owner_id": owner_id,
            "source_location_id": location_id,
            "dest_location_id": location_id,
            "quantity": quantity,
            "warehouse_id": warehouse_id,
        }

        message_vals = {
            "company_id": company_id,
            "event_name": "inventory.hu.packed",
            "schema_version": 1,
            "payload": {
                "package_id": self.id,
                "package_ref": package_ref,
                "product_id": product_id,
                "lot_id": lot_id,
                "owner_id": owner_id,
                "location_id": location_id,
                "quantity": quantity,
                "uom_id": uom_id,
            },
        }

        events, outbox = self.env["wms.inventory.event"]._append_events_with_outbox(
            [event_vals],
            [message_vals],
            correlation_id=correlation_id,
        )

        return {
            "package_id": self.id,
            "correlation_id": events.correlation_id,
        }

    def _wms_unpack_physical(self, quant_id, quantity, correlation_id=None):
        """Primitive físico transaccional para retirar inventario de una Handling Unit (ADR-019).

        Ejecuta la mutación física mediante el mecanismo nativo de relocalización de stock de Odoo 19,
        retirando una cantidad positiva de un quant perteneciente a la Handling Unit hacia inventario suelto
        (result_package_id=False) y coordinando la persistencia atómica de wms.inventory.event (UNPACK)
        y wms.outbox (inventory.hu.unpacked) bajo un mismo correlation_id sin apropiarse de la transacción
        PostgreSQL del llamador.

        :param int quant_id: ID entero positivo del quant empaquetado a retirar.
        :param float quantity: Cantidad positiva en la UoM del producto.
        :param str correlation_id: Opcional, identificador de correlación para el journal y outbox.
        :return dict: {'package_id': int, 'correlation_id': str}
        """
        self.ensure_one()

        # 1. RBAC Guard: el llamador debe pertenecer al grupo WMS Operator (o superior / admin)
        if not (
            self.env.user.has_group("wms_core.group_wms_operator")
            or self.env.user.has_group("base.group_system")
        ):
            raise AccessError("No tiene permisos para ejecutar operaciones WMS de desempaque.")

        # 2. Preflight de argumentos
        if isinstance(quant_id, bool) or not isinstance(quant_id, int) or quant_id <= 0:
            raise ValidationError("El identificador del quant debe ser un entero positivo.")

        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, (int, float))
            or math.isnan(quantity)
            or math.isinf(quantity)
        ):
            raise ValidationError("La cantidad a desempaquetar debe ser un valor numérico válido.")

        if correlation_id is not None:
            if not isinstance(correlation_id, str) or not correlation_id.strip():
                raise ValidationError("correlation_id debe ser una cadena de texto no vacía.")

        # 3. Row locks en orden estricto (package FOR UPDATE -> quant FOR UPDATE)
        self.env.cr.execute(
            "SELECT id FROM stock_package WHERE id = %s FOR UPDATE",
            [self.id],
        )
        if not self.env.cr.fetchone():
            raise ValidationError("La HU ya no existe.")

        self.env.cr.execute(
            "SELECT id FROM stock_quant WHERE id = %s FOR UPDATE",
            [quant_id],
        )
        if not self.env.cr.fetchone():
            raise ValidationError("El quant especificado no existe.")

        # 4. Invalidación de caché tras la adquisición de locks
        self.invalidate_recordset([
            "hu_state",
            "company_id",
            "location_id",
            "quant_ids",
            "contained_quant_ids",
            "package_type_id",
            "parent_package_id",
            "child_package_ids",
        ])

        quant = self.env["stock.quant"].browse(quant_id)
        quant.invalidate_recordset([
            "quantity",
            "reserved_quantity",
            "available_quantity",
            "package_id",
            "location_id",
            "company_id",
            "product_id",
            "lot_id",
            "owner_id",
        ])

        # 5. Scope guard post-lock: rechazar paquetes anidados (HU-004B opera sólo sobre HU top-level plana)
        if self.parent_package_id or self.child_package_ids:
            raise ValidationError("HU-004B opera únicamente sobre HU plana (top-level sin anidamiento).")

        # 6. Lifecycle guard de la HU origen: sólo una HU en estado OPEN puede desempaquetarse
        if self.hu_state != "OPEN":
            raise ValidationError(
                f"No se puede desempaquetar una Handling Unit en estado '{self.hu_state or 'SIN ESTADO'}'. Solo se permite en estado 'OPEN'."
            )

        if not self.contained_quant_ids:
            raise ValidationError(
                "La Handling Unit no posee contenido físico para desempaquetar."
            )

        # 7. Guards de pertenencia y compañía del quant y de la HU
        if quant.package_id != self:
            raise ValidationError(
                "El quant especificado no pertenece directamente a esta Handling Unit."
            )

        if not quant.company_id:
            raise ValidationError("El quant debe tener una compañía asignada.")

        if quant.company_id not in self.env.user.company_ids:
            raise AccessError("No tiene acceso a la compañía del inventario origen.")

        if not self.company_id:
            raise ValidationError("La HU posee contenido pero su compañía no está resuelta.")

        if self.company_id != quant.company_id:
            raise ValidationError(
                f"La compañía de la HU ({self.company_id.name}) no coincide con la del inventario ({quant.company_id.name})."
            )

        if self.company_id not in self.env.user.company_ids:
            raise AccessError("No tiene acceso a la compañía de la Handling Unit.")

        # 8. Guards de ubicación del quant (internal location, match si paquete está localizado)
        if quant.location_id.usage != "internal":
            raise ValidationError("El inventario a desempaquetar debe estar en una ubicación interna.")

        if self.location_id and self.location_id != quant.location_id:
            raise ValidationError(
                f"La ubicación de la HU ({self.location_id.display_name}) no coincide con la del quant ({quant.location_id.display_name})."
            )

        product = quant.product_id
        uom = product.uom_id

        if uom.compare(quantity, 0.0) <= 0:
            raise ValidationError("La cantidad a desempaquetar debe ser estrictamente positiva.")

        if not uom.is_zero(quant.reserved_quantity):
            raise ValidationError("No se puede desempaquetar inventario con reservas activas.")

        if uom.compare(quantity, quant.available_quantity) > 0:
            raise ValidationError(
                f"La cantidad solicitada ({quantity}) excede la disponibilidad ({quant.available_quantity})."
            )

        if product.tracking != "none" and not quant.lot_id:
            raise ValidationError(f"El producto '{product.display_name}' requiere seguimiento por lote/serie.")

        if product.tracking == "serial" and uom.compare(quantity, 1.0) != 0:
            raise ValidationError("Los productos con seguimiento por número de serie deben desempaquetarse en cantidad exacta de 1.0.")

        # 9. Operational Inventory Block guard (sin sudo)
        is_blocked = self.env["wms.inventory.block"].is_blocked(
            company_id=quant.company_id,
            product_id=product,
            location_id=quant.location_id,
            lot_id=quant.lot_id or False,
            package_id=self,
            owner_id=quant.owner_id or False,
        )
        if is_blocked:
            raise ValidationError("El inventario o paquete origen se encuentra bloqueado operacionalmente.")

        # 10. Captura de metadatos de snapshot inmutable antes de la mutación
        product_id = product.id
        lot_id = quant.lot_id.id or False
        owner_id = quant.owner_id.id or False
        location_id = quant.location_id.id
        company_id = quant.company_id.id
        warehouse_id = quant.location_id.warehouse_id.id or False
        uom_id = uom.id
        package_ref = self.name

        # 11. Mutación física nativa con narrow sudo (package_id=self -> package_dest_id=False)
        quant_sudo = quant.sudo()
        package_sudo = self.sudo()

        move_vals = quant_sudo.with_context(
            inventory_name="WMS Physical Unpack"
        )._get_inventory_move_values(
            quantity,
            quant.location_id,
            quant.location_id,
            package_id=package_sudo,
            package_dest_id=False,
        )
        move = self.env["stock.move"].sudo().create(move_vals)
        move._action_done()
        quant_sudo._quant_tasks()

        # 12. Actualización de hu_state según contenido remanente (sin leer quant post-cleanup)
        package_sudo.invalidate_recordset(["contained_quant_ids", "quant_ids", "location_id", "hu_state"])
        if not package_sudo.contained_quant_ids:
            package_sudo.hu_state = "EMPTY"
        else:
            package_sudo.hu_state = "OPEN"

        # 13. Persistencia de Event + Outbox en el entorno del usuario original (NO sudo)
        event_vals = {
            "company_id": company_id,
            "event_type": "UNPACK",
            "product_id": product_id,
            "lot_id": lot_id,
            "package_id": self.id,
            "owner_id": owner_id,
            "source_location_id": location_id,
            "dest_location_id": location_id,
            "quantity": quantity,
            "warehouse_id": warehouse_id,
        }

        message_vals = {
            "company_id": company_id,
            "event_name": "inventory.hu.unpacked",
            "schema_version": 1,
            "payload": {
                "package_id": self.id,
                "package_ref": package_ref,
                "product_id": product_id,
                "lot_id": lot_id,
                "owner_id": owner_id,
                "location_id": location_id,
                "quantity": quantity,
                "uom_id": uom_id,
            },
        }

        events, outbox = self.env["wms.inventory.event"]._append_events_with_outbox(
            [event_vals],
            [message_vals],
            correlation_id=correlation_id,
        )

        return {
            "package_id": self.id,
            "correlation_id": events.correlation_id,
        }

    def _wms_split_physical(self, quant_id, quantity, destination_package_id, correlation_id=None):
        """Primitive físico transaccional para dividir una Handling Unit transfiriendo parte de su contenido hacia otra Handling Unit vacía (ADR-019).

        Ejecuta la mutación física mediante el mecanismo nativo de relocalización de stock de Odoo 19,
        transfiriendo una cantidad positiva de un quant perteneciente a la Handling Unit fuente (self) hacia
        una Handling Unit destino existente, distinta y vacía (destination_package_id), manteniendo ambas
        Handling Units en estado 'OPEN' y coordinando la persistencia atómica de 2 eventos de inventario
        (UNPACK en fuente y PACK en destino) y 1 mensaje Outbox (inventory.hu.split) bajo un mismo correlation_id
        sin apropiarse de la transacción PostgreSQL del llamador.

        :param int quant_id: ID entero positivo del quant empaquetado origen a transferir.
        :param float quantity: Cantidad positiva en la UoM del producto.
        :param int destination_package_id: ID entero positivo del stock.package destino vacío.
        :param str correlation_id: Opcional, identificador de correlación para el journal y outbox.
        :return dict: {'source_package_id': int, 'destination_package_id': int, 'correlation_id': str}
        """
        self.ensure_one()

        # 1. RBAC Guard: el llamador debe pertenecer al grupo WMS Operator (o superior / admin)
        if not (
            self.env.user.has_group("wms_core.group_wms_operator")
            or self.env.user.has_group("base.group_system")
        ):
            raise AccessError("No tiene permisos para ejecutar operaciones WMS de división de HU.")

        # 2. Preflight de argumentos
        if isinstance(quant_id, bool) or not isinstance(quant_id, int) or quant_id <= 0:
            raise ValidationError("El identificador del quant debe ser un entero positivo.")

        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, (int, float))
            or math.isnan(quantity)
            or math.isinf(quantity)
            or quantity <= 0
        ):
            raise ValidationError("La cantidad a transferir debe ser un número finito estrictamente positivo.")

        if isinstance(destination_package_id, bool) or not isinstance(destination_package_id, int) or destination_package_id <= 0:
            raise ValidationError("El identificador del paquete destino debe ser un entero positivo.")

        if self.id == destination_package_id:
            raise ValidationError("La Handling Unit destino debe ser distinta de la Handling Unit fuente.")

        if correlation_id is not None:
            if not isinstance(correlation_id, str) or not correlation_id.strip():
                raise ValidationError("correlation_id debe ser una cadena de texto no vacía.")

        # 3. Row locks en orden ascendente de IDs de paquetes (para evitar ABBA deadlocks)
        pkg_ids = sorted([self.id, destination_package_id])
        self.env.cr.execute(
            "SELECT id FROM stock_package WHERE id IN (%s, %s) ORDER BY id FOR UPDATE",
            pkg_ids,
        )
        locked_pkg_rows = self.env.cr.fetchall()
        if len(locked_pkg_rows) != 2:
            raise ValidationError("Una o ambas Handling Units no existen o ya no están disponibles.")

        # Row lock sobre el quant
        self.env.cr.execute(
            "SELECT id FROM stock_quant WHERE id = %s FOR UPDATE",
            [quant_id],
        )
        if not self.env.cr.fetchone():
            raise ValidationError("El quant especificado no existe.")

        # 4. Invalidación de caché tras la adquisición de locks
        dest_package = self.env["stock.package"].browse(destination_package_id)
        for pkg in (self, dest_package):
            pkg.invalidate_recordset([
                "hu_state",
                "company_id",
                "location_id",
                "quant_ids",
                "contained_quant_ids",
                "package_type_id",
                "parent_package_id",
                "child_package_ids",
            ])

        quant = self.env["stock.quant"].browse(quant_id)
        quant.invalidate_recordset([
            "quantity",
            "reserved_quantity",
            "available_quantity",
            "package_id",
            "location_id",
            "company_id",
            "product_id",
            "lot_id",
            "owner_id",
        ])

        # 5. Control de acceso post-lock en el entorno del usuario original
        self.check_access("read")
        dest_package.check_access("read")
        quant.check_access("read")

        # 6. Scope guard: rechazar paquetes anidados (HU-004C opera sólo sobre HUs top-level planas)
        if self.parent_package_id or self.child_package_ids or dest_package.parent_package_id or dest_package.child_package_ids:
            raise ValidationError("HU-004C opera únicamente sobre Handling Units planas (top-level sin anidamiento).")

        # 7. Lifecycle & Content guards de la HU fuente y destino
        if self.hu_state != "OPEN":
            raise ValidationError(
                f"No se puede dividir una Handling Unit fuente en estado '{self.hu_state or 'SIN ESTADO'}'. Solo se permite en estado 'OPEN'."
            )

        if not self.contained_quant_ids:
            raise ValidationError("La Handling Unit fuente no posee contenido para dividir.")

        if dest_package.hu_state not in (False, "EMPTY"):
            raise ValidationError(
                f"La Handling Unit destino debe estar vacía o sin inicializar (estado actual: '{dest_package.hu_state}')."
            )

        if dest_package.contained_quant_ids:
            raise ValidationError("La Handling Unit destino ya contiene inventario físico.")

        # 8. Guard de pertenencia del quant a la HU fuente
        if quant.package_id != self:
            raise ValidationError("El quant especificado no pertenece directamente a esta Handling Unit.")

        product = quant.product_id
        uom = product.uom_id

        # 9. Algoritmo de retención de la fuente multi-UoM
        if uom.compare(quantity, quant.quantity) < 0:
            # La fuente retiene parte del mismo quant
            pass
        elif uom.compare(quantity, quant.quantity) == 0:
            # Se transfiere el quant completo; debe existir al menos otro quant directo positivo
            other_quants = self.contained_quant_ids.filtered(lambda q: q.id != quant.id)
            has_other_positive_quant = any(
                q.product_id.uom_id.compare(q.quantity, 0.0) > 0 for q in other_quants
            )
            if not has_other_positive_quant:
                raise ValidationError("La operación de split no puede vaciar completamente la Handling Unit fuente.")
        else:
            raise ValidationError("La cantidad a transferir excede la cantidad total del quant.")

        # 10. Guards de compañía y multi-company
        if not quant.company_id:
            raise ValidationError("El quant debe tener una compañía asignada.")

        if quant.company_id not in self.env.user.company_ids:
            raise AccessError("No tiene acceso a la compañía del inventario origen.")

        if not self.company_id:
            raise ValidationError("La Handling Unit fuente posee contenido pero su compañía no está resuelta.")

        if self.company_id != quant.company_id:
            raise ValidationError(
                f"La compañía de la Handling Unit fuente ({self.company_id.name}) no coincide con la del inventario ({quant.company_id.name})."
            )

        if self.company_id not in self.env.user.company_ids:
            raise AccessError("No tiene acceso a la compañía de la Handling Unit fuente.")

        if dest_package.company_id and dest_package.company_id != quant.company_id:
            raise ValidationError(
                f"La compañía de la Handling Unit destino ({dest_package.company_id.name}) no coincide con la del inventario ({quant.company_id.name})."
            )

        if dest_package.company_id and dest_package.company_id not in self.env.user.company_ids:
            raise AccessError("No tiene acceso a la compañía de la Handling Unit destino.")

        # 11. Guards de ubicación
        location = quant.location_id
        if not location or location.usage != "internal":
            raise ValidationError("La ubicación física del inventario debe ser de tipo 'Interna' (usage='internal').")

        if location.company_id and location.company_id != quant.company_id:
            raise ValidationError(
                f"La compañía de la ubicación ({location.company_id.name}) no coincide con la del inventario ({quant.company_id.name})."
            )

        # 12. Guards operacionales de cantidad, reservas y trazabilidad
        if uom.compare(quantity, 0.0) <= 0:
            raise ValidationError("La cantidad a transferir debe ser estrictamente positiva según la precisión de la UoM.")

        if not uom.is_zero(quant.reserved_quantity):
            raise ValidationError("El quant posee reservas activas. No se puede transferir inventario reservado.")

        if uom.compare(quantity, quant.available_quantity) > 0:
            raise ValidationError("La cantidad a transferir excede la cantidad disponible del quant.")

        if product.tracking in ("lot", "serial") and not quant.lot_id:
            raise ValidationError(f"El producto '{product.name}' requiere número de lote/serie pero el quant no tiene lote asignado.")

        if product.tracking == "serial" and uom.compare(quantity, 1.0) != 0:
            raise ValidationError(f"Los productos trazados por serie ('{product.name}') solo pueden transferirse de a 1 unidad.")

        # 13. Guards de bloqueos de inventario (wms.inventory.block)
        block_model = self.env["wms.inventory.block"]
        common_block_scope = {
            "company_id": quant.company_id,
            "product_id": product,
            "location_id": location,
            "lot_id": quant.lot_id or False,
            "owner_id": quant.owner_id or False,
        }

        if block_model.is_blocked(**common_block_scope, package_id=self):
            raise ValidationError("La operación está bloqueada por una regla activa de bloqueo de inventario en el origen.")

        if block_model.is_blocked(**common_block_scope, package_id=dest_package):
            raise ValidationError("La operación está bloqueada por una regla activa de bloqueo de inventario en el destino.")

        # 14. Guards de tipo de paquete y PLM (wms.product.logistics) sobre el destino
        if dest_package.package_type_id:
            self.env.cr.execute(
                "SELECT company_id FROM stock_package_type WHERE id = %s",
                [dest_package.package_type_id.id],
            )
            type_row = self.env.cr.fetchone()
            if type_row and type_row[0] and type_row[0] != quant.company_id.id:
                raise ValidationError("La compañía del tipo de paquete destino no coincide con la del inventario.")

        logistics = self.env["wms.product.logistics"].search([
            ("product_tmpl_id", "=", product.product_tmpl_id.id),
            "|",
            ("company_id", "=", quant.company_id.id),
            ("company_id", "=", False),
        ], limit=1)
        if logistics:
            self.env.cr.execute(
                "SELECT stock_package_type_id FROM stock_package_type_wms_product_logistics_rel WHERE wms_product_logistics_id = %s",
                [logistics.id],
            )
            allowed_type_ids = [row[0] for row in self.env.cr.fetchall()]
            if allowed_type_ids:
                dest_type_id = dest_package.package_type_id.id
                if not dest_type_id:
                    raise ValidationError(
                        f"El producto '{product.display_name}' exige un tipo de HU permitido, pero el paquete destino no tiene tipo asignado."
                    )
                if dest_type_id not in allowed_type_ids:
                    raise ValidationError(
                        f"El tipo de paquete asignado a la HU destino no está permitido para el producto '{product.display_name}'."
                    )

        # 15. Captura inmutable de metadatos antes de la mutación física
        source_pkg_id = self.id
        source_pkg_ref = self.name
        dest_pkg_id = dest_package.id
        dest_pkg_ref = dest_package.name
        product_id = product.id
        lot_id = quant.lot_id.id if quant.lot_id else False
        owner_id = quant.owner_id.id if quant.owner_id else False
        location_id = location.id
        company_id = quant.company_id.id
        uom_id = uom.id
        warehouse_id = location.warehouse_id.id if hasattr(location, "warehouse_id") and location.warehouse_id else False

        # 16. Mutación física vía narrow sudo sobre stock.move
        quant_sudo = quant.sudo()
        source_sudo = self.sudo()
        destination_sudo = dest_package.sudo()

        move_vals = quant_sudo.with_context(
            inventory_name="WMS Physical Split"
        )._get_inventory_move_values(
            quantity,
            location,
            location,
            package_id=source_sudo,
            package_dest_id=destination_sudo,
        )

        move = self.env["stock.move"].sudo().create(move_vals)
        move._action_done()

        destination_sudo.hu_state = "OPEN"

        # 17. Persistencia atómica de 2 Eventos + 1 Outbox en el entorno del usuario original
        event_vals_list = [
            {
                "company_id": company_id,
                "event_type": "UNPACK",
                "product_id": product_id,
                "lot_id": lot_id,
                "package_id": source_pkg_id,
                "owner_id": owner_id,
                "source_location_id": location_id,
                "dest_location_id": location_id,
                "quantity": quantity,
                "warehouse_id": warehouse_id,
            },
            {
                "company_id": company_id,
                "event_type": "PACK",
                "product_id": product_id,
                "lot_id": lot_id,
                "package_id": dest_pkg_id,
                "owner_id": owner_id,
                "source_location_id": location_id,
                "dest_location_id": location_id,
                "quantity": quantity,
                "warehouse_id": warehouse_id,
            },
        ]

        outbox_payload = {
            "source_package_id": source_pkg_id,
            "source_package_ref": source_pkg_ref,
            "destination_package_id": dest_pkg_id,
            "destination_package_ref": dest_pkg_ref,
            "product_id": product_id,
            "lot_id": lot_id,
            "owner_id": owner_id,
            "location_id": location_id,
            "quantity": quantity,
            "uom_id": uom_id,
        }

        outbox_vals_list = [
            {
                "company_id": company_id,
                "event_name": "inventory.hu.split",
                "schema_version": 1,
                "payload": outbox_payload,
            }
        ]

        events, outbox = self.env["wms.inventory.event"]._append_events_with_outbox(
            event_vals_list=event_vals_list,
            messages=outbox_vals_list,
            correlation_id=correlation_id.strip() if correlation_id else None,
        )

        return {
            "source_package_id": source_pkg_id,
            "destination_package_id": dest_pkg_id,
            "correlation_id": events[:1].correlation_id,
        }
