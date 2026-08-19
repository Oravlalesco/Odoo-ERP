---
name: wms-transaction-patterns
description: >-
  Usar este skill cuando se desarrolle lógica de negocio que modifique inventario
  (stock.quant), reservas, asignación de trabajo (wms.work), o cualquier operación
  WMS concurrente. Incluye patrones de locking, idempotencia, lease protocol,
  outbox pattern y los performance budgets del proyecto. Obligatorio consultar
  antes de escribir código que toque tablas transaccionales del WMS.
---

# Patrones Transaccionales WMS

Contratos transaccionales que **todo el código WMS debe respetar**. Referencia: [Transaction Architecture](../../docs/03-plataforma/00-transaction-architecture.md).

---

## Principio Fundamental

> **Cada operación WMS que modifica estado debe ser una transacción corta, autocontenida e idempotente.**

| Característica | Significado |
|---|---|
| **Corta** | < 200ms típico, < 500ms máximo |
| **Autocontenida** | No depende de estado externo ni de transacciones previas no commiteadas |
| **Idempotente** | Ejecutarla dos veces produce el mismo resultado |

---

## Invariantes del Sistema (NO negociables)

| ID | Invariante | Consecuencia si se viola |
|---|---|---|
| **CORE-001** | Un `wms.work` en `ASSIGNED` tiene exactamente un `assigned_resource_id` | Doble asignación → doble pick |
| **CORE-002** | Un `wms.work` en `READY` no tiene `assigned_resource_id` | Work huérfano → operador fantasma |
| **CORE-003** | `wms.inventory.event` se crea atómicamente con el cambio de `stock.quant` | Event journal incompleto → trazabilidad rota |
| **CORE-004** | `wms.outbox` se crea atómicamente con la acción que genera el evento | Outbox desincronizado → integraciones inconsistentes |
| **CORE-005** | Cada `wms.allocation` tiene al menos un quant válido | Allocation sin stock → pick imposible |
| **CORE-006** | `claim_token` de `wms.work` es único | Previene race conditions en re-claim |

---

## Performance Budget por Operación

| Operación | Budget | Si se excede |
|---|---|---|
| Claim Work | 50ms | Index missing o lock contention |
| Confirm Pick | 200ms | Transacción demasiado amplia o triggers pesados |
| Confirm Put | 200ms | Transacción demasiado amplia |
| Heartbeat | 20ms | Network issue |
| Allocation (por orden) | 500ms | Query ineficiente o demasiados candidatos |
| Wave Release | 5s | Batch demasiado grande |

---

## Patrón 1: `FOR UPDATE SKIP LOCKED` (Asignación de Colas)

**ADR-008**: La asignación de trabajo a recursos usa `SELECT ... FOR UPDATE SKIP LOCKED`.

```python
def _claim_next_work(self, resource, queue):
    """
    Obtiene atómicamente el siguiente trabajo disponible.
    SKIP LOCKED garantiza que operadores concurrentes no se bloqueen.
    """
    self.env.cr.execute("""
        SELECT id
        FROM wms_work
        WHERE state = 'ready'
          AND queue_id = %s
        ORDER BY priority DESC, deadline ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    """, (queue.id,))

    row = self.env.cr.fetchone()
    if not row:
        return self.env['wms.work']

    work = self.env['wms.work'].browse(row[0])
    work.write({
        'state': 'assigned',
        'assigned_resource_id': resource.id,
        'claim_token': str(uuid.uuid4()),
        'assigned_at': fields.Datetime.now(),
        'lease_expires_at': fields.Datetime.now() + timedelta(minutes=10),
        'assignment_version': work.assignment_version + 1,
    })
    return work
```

### Cuándo usar cada tipo de lock

| Tipo de Lock | Tabla | Cuándo |
|---|---|---|
| `FOR UPDATE SKIP LOCKED` | `wms_work` | Claim de trabajo — concurrencia de 250 operadores |
| `FOR UPDATE` | `stock_quant` | Confirm pick/put — modificación de inventario |
| `FOR UPDATE SKIP LOCKED` | `stock_quant` | Allocation — múltiples allocations concurrentes |
| `FOR UPDATE` | `wms_allocation` | Confirm allocation — exclusividad de reserva |

---

## Patrón 2: Idempotencia con `INSERT ... ON CONFLICT`

**ADR-010**: Todos los comandos recibidos externamente son idempotentes.

```python
def _ensure_idempotent(self, idempotency_key):
    """
    Verifica si un comando ya fue procesado. Usa INSERT ON CONFLICT
    para evitar race conditions (ADR-010 + corrección v1.2).
    """
    self.env.cr.execute("""
        INSERT INTO wms_idempotency (key, status)
        VALUES (%s, 'PROCESSING')
        ON CONFLICT (key) DO NOTHING
        RETURNING key
    """, (idempotency_key,))

    result = self.env.cr.fetchone()
    if result:
        # Este request ganó ownership → ejecutar comando
        return 'PROCESS'
    else:
        # Otro request ya tiene la key
        self.env.cr.execute("""
            SELECT status, response
            FROM wms_idempotency
            WHERE key = %s
        """, (idempotency_key,))
        row = self.env.cr.fetchone()
        if row and row[0] == 'DONE':
            return 'ALREADY_DONE'
        return 'IN_PROGRESS'

def _mark_idempotent_done(self, idempotency_key, response):
    """Marca un comando como procesado exitosamente."""
    self.env.cr.execute("""
        UPDATE wms_idempotency
        SET status = 'DONE', response = %s
        WHERE key = %s
    """, (Json(response), idempotency_key))
```

---

## Patrón 3: Mutación de Inventario — NO Inventar el Mecanismo

**ADR-001**: `stock.quant` es la fuente de verdad. Toda modificación pasa por el ORM de Odoo.

**ADR-019**: `wms.inventory.event` y `wms.outbox` se crean dentro de la misma transacción que modifica `stock.quant`.

### ⚠️ REGLA CRÍTICA

> **NO inventar el mecanismo de mutación de inventario.**
>
> Antes de implementar cualquier operación que modifique quants (confirm pick,
> confirm put, adjustment, transfer):
>
> 1. **Inspeccionar** el flujo de Odoo 19 correspondiente en el código fuente
> 2. **Identificar** el método ORM oficial que ejecuta la mutación
> 3. **Envolver** la operación WMS alrededor de ese mecanismo
> 4. **Generar** journal/outbox solo donde exista certeza de que la mutación ocurrió

### Por qué es crítico

La identidad lógica de un quant en Odoo incluye **6 dimensiones**:

```
(product_id, company_id, location_id, lot_id, package_id, owner_id)
```

Un lock SQL que solo filtre por `product_id` y `location_id` puede:
- Bloquear **múltiples** quants (distintos lotes en la misma ubicación)
- Bloquear el quant **incorrecto**
- Dejar sin bloquear el quant que realmente se va a mutar

Además, asignar `move_line.quantity` o `move_line.picked = True` no garantiza
que el quant haya sido mutado en ese punto. La mutación real del quant ocurre
dentro de métodos internos de Odoo (`_action_done()`, `_update_available_quantity()`,
etc.) que tienen su propia lógica de merge, validación y reconciliación.

### Patrón Correcto: Envolver el Mecanismo ORM

```python
def _confirm_pick(self, work_line, scanned_qty):
    """
    Confirma un pick envolviendo el mecanismo ORM de Odoo.

    ⚠️ Este es un EJEMPLO ESTRUCTURAL. Antes de implementar:
    1. Inspeccionar stock.move._action_done() en el SHA fijado de Odoo 19
    2. Verificar qué método muta realmente el quant
    3. Determinar el punto exacto donde generar event/outbox
    """
    # 1. Preparar el move_line (registro de la operación)
    move_line = work_line.move_line_id
    move_line.quantity = scanned_qty
    if work_line.lot_id:
        move_line.lot_id = work_line.lot_id
    move_line.picked = True

    # 2. Ejecutar la mutación VÍA EL MECANISMO ORM DE ODOO
    #    El método _action_done() del stock.move es el que realmente:
    #    - Muta los quants (origin y destino)
    #    - Ejecuta _merge_quants()
    #    - Actualiza reserved_quantity
    #    - Gestiona paquetes
    #
    #    ⚠️ VERIFICAR: inspeccionar _action_done() en el commit fijado
    #    para confirmar que este es el punto correcto de mutación.
    move_line.move_id._action_done()

    # 3. SOLO DESPUÉS de que _action_done() completó sin error
    #    (la mutación del quant es un hecho), generar event y outbox
    self.env['wms.inventory.event'].create({
        'event_type': 'PICK',
        'product_id': work_line.product_id.id,
        'location_id': work_line.location_id.id,
        'location_dest_id': work_line.location_dest_id.id,
        'quantity': scanned_qty,
        'lot_id': work_line.lot_id.id or False,
        'package_id': work_line.package_id.id or False,
        'work_id': work_line.work_id.id,
        'work_line_id': work_line.id,
    })

    self.env['wms.outbox'].create({
        'event_type': 'PICK_CONFIRMED',
        'payload': {
            'work_id': work_line.work_id.id,
            'product_id': work_line.product_id.id,
            'quantity': scanned_qty,
        },
    })
    # Event + Outbox + Mutación de quant: todo en la misma transacción
```

### Checklist antes de Implementar Mutación de Inventario

| Paso | Pregunta | Si no puedes responder → |
|---|---|---|
| 1 | ¿Qué método de Odoo ejecuta la mutación del quant en este flujo? | Inspeccionar el código fuente antes de escribir |
| 2 | ¿Ese método gestiona las 6 dimensiones del quant (product, company, location, lot, package, owner)? | No usar SQL manual con filtros parciales |
| 3 | ¿El método ejecuta `_merge_quants()` y actualiza `reserved_quantity`? | No bypasear con `stock.quant.write({'quantity': ...})` |
| 4 | ¿En qué punto del flujo es seguro afirmar que la mutación ocurrió? | No generar event/outbox antes de ese punto |
| 5 | ¿El flujo funciona igual en el commit SHA fijado del proyecto (ADR-027)? | Verificar contra el commit exacto |

### Anti-patrón: SQL Manual para Mutar Quants

```python
# ❌ PROHIBIDO: Lock parcial + mutación directa
self.env.cr.execute("""
    SELECT id FROM stock_quant
    WHERE product_id = %s AND location_id = %s
    FOR UPDATE
""", (product_id, location_id))
# Faltan: lot_id, package_id, owner_id, company_id
# Puede bloquear N quants en vez de 1

# ❌ PROHIBIDO: Mutación directa del quant
quant.write({'quantity': quant.quantity - picked_qty})
# Bypasea _merge_quants(), validaciones, reserved_quantity

# ✅ CORRECTO: Usar el mecanismo ORM de Odoo
move._action_done()  # O el método que corresponda al flujo
```

---

## Patrón 4: Lease + Heartbeat

**ADR-015/016**: Work assignment usa lease + atomic claim. Transacciones cortas.

```python
def _renew_lease(self, work, claim_token):
    """
    Renueva el lease de un Work. Verifica claim_token para
    prevenir race conditions.
    """
    now = fields.Datetime.now()
    self.env.cr.execute("""
        UPDATE wms_work
        SET lease_expires_at = %s,
            last_heartbeat_at = %s
        WHERE id = %s
          AND claim_token = %s
          AND state IN ('assigned', 'in_progress')
    """, (
        now + timedelta(minutes=10),
        now,
        work.id,
        claim_token,
    ))

    if self.env.cr.rowcount == 0:
        raise UserError('Lease no renovado: trabajo reasignado o completado.')

def _expire_stale_leases(self):
    """
    Cron: detecta leases expirados y actúa según estado.
    ADR-025: IN_PROGRESS con ejecución → RECONCILIATION_REQUIRED.

    ⚠️ SQL DIRECTO DELIBERADO — ver regla "SQL Directo sobre Tablas ORM".
    Justificación: operación batch que puede afectar cientos de rows.
    ORM sería O(N) queries. El cron se ejecuta en proceso aislado.

    Consecuencias aceptadas:
    - Cache ORM: no aplica (cron en proceso propio, sin cache previa)
    - Computed fields: state no tiene dependientes stored
    - Tracking: no se generan mensajes de chatter (aceptable para cron)
    - write_date: NO se actualiza (decisión explícita — se usa
      lease_expires_at como timestamp de referencia)
    - Invalidación: se llama invalidate_recordset() después
    """
    now = fields.Datetime.now()

    # ASSIGNED sin ejecución → RECLAIMABLE → READY (seguro)
    self.env.cr.execute("""
        UPDATE wms_work
        SET state = 'ready',
            assigned_resource_id = NULL,
            claim_token = NULL,
            reclaim_count = reclaim_count + 1
        WHERE state = 'assigned'
          AND lease_expires_at < %s
    """, (now,))
    count_assigned = self.env.cr.rowcount

    # IN_PROGRESS con ejecución → RECONCILIATION_REQUIRED (requiere supervisor)
    self.env.cr.execute("""
        UPDATE wms_work
        SET state = 'reconciliation_required'
        WHERE state = 'in_progress'
          AND lease_expires_at < %s
    """, (now,))
    count_in_progress = self.env.cr.rowcount

    # Invalidar cache ORM después de SQL directo
    if count_assigned or count_in_progress:
        self.env['wms.work'].invalidate_recordset()
```

---

## Regla: SQL Directo sobre Tablas ORM

> **SQL directo que modifica tablas gestionadas por el ORM requiere
> decisión explícita y documentada sobre cada consecuencia.**

SQL directo (`cr.execute(UPDATE/INSERT/DELETE)`) puede ser apropiado en hot
paths por rendimiento, pero bypasea toda la maquinaria del ORM. Si no se
gestiona correctamente, el resultado es inconsistencia:

```text
ORM cache del worker:     state = 'in_progress'
PostgreSQL real:          state = 'reconciliation_required'
```

### Checklist obligatorio para SQL directo en tablas ORM

Antes de escribir `cr.execute(UPDATE ...)` sobre una tabla del ORM, responder
**cada** pregunta en un comentario junto al SQL:

| # | Pregunta | Consecuencia si se ignora |
|---|---|---|
| 1 | **Cache ORM**: ¿Otros procesos/threads tienen este registro en cache? | Leen estado stale → decisiones incorrectas |
| 2 | **Computed fields**: ¿Hay campos `store=True` que dependen del campo modificado? | Computed fields quedan desincronizados |
| 3 | **Tracking** (chatter): ¿El campo tiene `tracking=True`? | No se genera mensaje de tracking |
| 4 | **write_date / write_uid**: ¿Se necesita actualizar? | Auditoría y concurrency checks rotos |
| 5 | **Constraints**: ¿Hay `@api.constrains` sobre el campo? | Constraint no se ejecuta |
| 6 | **Onchange / compute triggers**: ¿Hay lógica que depende de `write()`? | Lógica derivada no se ejecuta |
| 7 | **Invalidación**: ¿Se llama `invalidate_recordset()` después? | Cache stale persistente |

### Cuándo es aceptable SQL directo

| Caso | ¿Aceptable? | Condición |
|---|---|---|
| Cron batch que afecta muchos rows | ✅ | Proceso aislado + `invalidate_recordset()` |
| `FOR UPDATE SKIP LOCKED` para claim | ✅ | Es un SELECT, no modifica por sí solo |
| Heartbeat (solo `lease_expires_at`) | ✅ | Campo sin dependientes, hot path <20ms |
| Idempotency key (`wms_idempotency`) | ✅ | Tabla WMS propia, no modelo Odoo |
| Cambiar `state` de un Work desde API | ❌ | Usar `work.write({'state': ...})` |
| Modificar `stock.quant.quantity` | ❌ | Usar mecanismo ORM (Patrón 3) |
| Actualizar campos con `tracking=True` | ❌ | Usar ORM para generar tracking |

### Template de comentario para SQL directo justificado

```python
# ⚠️ SQL DIRECTO DELIBERADO
# Justificación: <por qué no usar ORM aquí>
# Consecuencias aceptadas:
#   - Cache ORM: <cómo se maneja>
#   - Computed fields: <cuáles dependen, o "ninguno">
#   - Tracking: <se pierde / no aplica>
#   - write_date: <se actualiza manualmente / no se necesita>
#   - Invalidación: <se llama invalidate_recordset() después>
```

---

## Anti-patrones Prohibidos

| Anti-patrón | Problema | Solución correcta |
|---|---|---|
| Lock 50 rows mientras Python calcula score | Bloquea a 50 operadores | Calcular score SIN lock, luego atomic claim de 1 row |
| Transacción abierta durante scan del operador | Bloquea filas durante minutos | Transacción corta + lease |
| Lock de tabla completa | Detiene toda la operación | Lock de fila específica |
| Nested transactions | Complejidad, deadlocks potenciales | Una transacción atómica por operación |
| `safe_eval` en reglas | Ejecución de código arbitrario | DSL tipada (ADR-018) |
| Reserva doble (WMS + Odoo) | Double-booking de inventario | Allocation coordina con `reserved_quantity` de Odoo (ADR-014) |
| SQL directo sin documentar consecuencias | Cache stale, tracking perdido, computed desincronizados | Checklist obligatorio (ver arriba) |

---

## ADRs Relevantes (Resumen Rápido)

| ADR | Regla clave |
|---|---|
| ADR-001 | `stock.quant` es la fuente de verdad → toda modificación por ORM |
| ADR-006 | PostgreSQL dueño de la consistencia transaccional |
| ADR-007 | Redis NO es propietario de estado de inventario |
| ADR-008 | `FOR UPDATE SKIP LOCKED` para asignación de colas |
| ADR-010 | Todos los comandos externos son idempotentes |
| ADR-014 | Allocation coordina con `reserved_quantity` de Odoo |
| ADR-015 | Lease + atomic claim para Work assignment |
| ADR-016 | Cada transacción < 200ms |
| ADR-019 | Event + Outbox atómicos con cambio de quant |
| ADR-025 | IN_PROGRESS no puede auto-requeue tras lease expiry |

---

## Verificación antes de Merge

1. ¿La transacción dura menos de 200ms (operaciones RF)?
2. ¿Se usa `FOR UPDATE SKIP LOCKED` donde hay concurrencia?
3. ¿Los eventos y outbox se crean en la misma transacción que el cambio de quant?
4. ¿Los endpoints de integración reciben `idempotency_key`?
5. ¿No hay anti-patrones prohibidos?
6. ¿Se respetan los performance budgets?
7. ¿Todo SQL directo sobre tablas ORM tiene el checklist de consecuencias documentado?

