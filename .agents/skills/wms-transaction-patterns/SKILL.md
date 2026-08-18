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

## Patrón 3: Atomic Event + Outbox

**ADR-019**: `wms.inventory.event` y `wms.outbox` se crean dentro de la misma transacción que modifica `stock.quant`.

```python
def _confirm_pick(self, work_line, scanned_qty):
    """
    Confirma un pick: mueve inventario, crea evento y outbox
    en la MISMA transacción.
    """
    # 1. Modificar quant (con lock)
    self.env.cr.execute("""
        SELECT id FROM stock_quant
        WHERE product_id = %s AND location_id = %s
        FOR UPDATE
    """, (work_line.product_id.id, work_line.location_id.id))

    # 2. Ejecutar el movimiento vía ORM de Odoo
    move_line = work_line.move_line_id
    move_line.quantity = scanned_qty
    move_line.picked = True

    # 3. Crear evento de inventario (MISMA transacción)
    self.env['wms.inventory.event'].create({
        'event_type': 'PICK',
        'product_id': work_line.product_id.id,
        'location_id': work_line.location_id.id,
        'quantity': -scanned_qty,
        'work_id': work_line.work_id.id,
        'work_line_id': work_line.id,
    })

    # 4. Crear mensaje outbox (MISMA transacción)
    self.env['wms.outbox'].create({
        'event_type': 'PICK_CONFIRMED',
        'payload': {
            'work_id': work_line.work_id.id,
            'product_id': work_line.product_id.id,
            'quantity': scanned_qty,
        },
    })

    # Todo se commitea junto o nada se commitea
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

    # IN_PROGRESS con ejecución → RECONCILIATION_REQUIRED (requiere supervisor)
    self.env.cr.execute("""
        UPDATE wms_work
        SET state = 'reconciliation_required'
        WHERE state = 'in_progress'
          AND lease_expires_at < %s
    """, (now,))
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
