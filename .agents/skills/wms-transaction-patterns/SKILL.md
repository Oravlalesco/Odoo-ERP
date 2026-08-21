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

## 🛑 Directiva de Madurez Arquitectónica (INV-AGENT-008)

> **Los fragmentos de esta sección se dividen estrictamente en APIs IMPLEMENTADAS y PATRONES OBJETIVO CONCEPTUALES.**
>
> Un patrón conceptual **NO** constituye una API disponible. Antes de reutilizar cualquier fragmento:
> 1. Verificar si el modelo y método existen actualmente en `develop`.
> 2. Consultar el ADR y Task Contract vigente.
> 3. En caso de inventario, verificar el mecanismo nativo de Odoo 19 pinned.

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

## Patrón 1: Mutación de Inventario y Journal de Eventos

**ADR-001**: `stock.quant` es la fuente de verdad. Toda modificación pasa por el ORM de Odoo.

**ADR-019**: `wms.inventory.event` y `wms.outbox` se persisten dentro de la misma transacción atómica que modifica `stock.quant`.

### ⚠️ REGLA CRÍTICA
> **NO inventar el mecanismo de mutación de inventario ni asumir `create()` directo.**
>
> El modelo `wms.inventory.event` (INV-008) es **append-only inmutable**: bloquea `create()`, `write()` y `unlink()`.
> La única vía de inserción autorizada es la API privada `_append_events(vals_list, correlation_id=None)`.

### [IMPLEMENTED API] Inserción de Eventos Operacionales

```python
# ✅ API IMPLEMENTADA en develop (wms_inventory / INV-008)
event_vals = [{
    'company_id': quant.company_id.id,
    'event_type': 'PICK',
    'product_id': quant.product_id.id,
    'lot_id': quant.lot_id.id or False,
    'package_id': quant.package_id.id or False,
    'source_location_id': quant.location_id.id,
    'dest_location_id': dest_location.id,
    'quantity': picked_qty,
}]

# Persistencia server-owned atómica (asigna occurred_at, operator_id y correlation_id)
events = self.env['wms.inventory.event']._append_events(event_vals, correlation_id=tx_correlation_id)
```

### [TARGET PATTERN — NOT AN API CONTRACT] Transacción Integrada con Outbox

```python
# ⚠️ PATRÓN CONCEPTUAL OBJETIVO — La entidad wms.outbox pertenece al slice INV-010.
# No copiar ni instanciar wms.outbox hasta que su Task Contract sea implementado.

# 1. Mutar quant vía ORM Odoo nativo (_action_done o similar)
# 2. Registrar evento operacional:
#    self.env['wms.inventory.event']._append_events([...])
# 3. Registrar outbox atómico:
#    self.env['wms.outbox']._append_outbox([...])
```

---

## [TARGET PATTERN — NOT AN API CONTRACT] Patrón 2: Asignación Concurrente con `FOR UPDATE SKIP LOCKED`

**ADR-008**: La asignación de trabajo a recursos usa `SELECT ... FOR UPDATE SKIP LOCKED` para evitar contención entre operadores.

*El motor de trabajo WMS (`wms_work_engine`) será implementado bajo su respectivo Task Contract.*

```text
Flujo Conceptual de Asignación Concurrente (ADR-008):
1. Identificar la cola operacional y criterios de ordenamiento (prioridad desc, fecha límite asc).
2. Lock puntual de un único registro candidato disponible con SELECT ... FOR UPDATE SKIP LOCKED.
3. Si no hay registros disponibles, retornar recordset vacío inmediatamente (sin bloquear ni esperar).
4. Revalidar invariantes de negocio en memoria.
5. Mutar el registro asignando el recurso y generando token único según defina el Task Contract.
6. Mantener la transacción estrictamente dentro del performance budget (<50ms).
```

---

## [TARGET PATTERN — NOT AN API CONTRACT] Patrón 3: Asignación Temporal (Lease) y Latido (Heartbeat)

**ADR-015/016**: Work assignment usa lease + atomic claim. Transacciones cortas.

*El motor de trabajo WMS (`wms_work_engine`) será implementado bajo su respectivo Task Contract.*

```text
Flujo Conceptual del Protocolo de Asignación Temporal:
1. El operario envía latido periódico (heartbeat) con su token de asignación.
2. Actualización condicional atómica:
   - Verificar claim_token vigente y estado asignado/en proceso.
   - Extender lease_expires_at (ej. +10 min).
3. Si el registro no fue modificado por concurrencia o vencimiento:
   - Lanzar UserError: "La asignación temporal no pudo renovarse: el trabajo fue reasignado o completado."
4. Si el Task Contract autoriza SQL directo en hot path (<20ms):
   - Flush previo de campos relevantes antes del SQL (flush_model).
   - Identificar los IDs afectados (ej. RETURNING id / selección lockeada previa).
   - Invalidar en el recordset afectado los campos modificados: self.env['wms.work'].browse(affected_ids).invalidate_recordset(fnames=[...]).
   - Invocar modified(fnames) si existen dependencias calculadas store=True.
   - Documentar explícitamente el template de justificación SQL.
```

---

## [TARGET PATTERN — NOT AN API CONTRACT] Patrón 4: Idempotencia Concurrente con `ON CONFLICT`

**ADR-010**: Todos los comandos recibidos externamente o de RF son idempotentes.

```text
Mecanismo Conceptual de Idempotencia Concurrente:
1. La solicitud aporta una clave de idempotencia definida por el contrato (ej. X-Idempotency-Key).
2. correlation_id se utiliza para trazabilidad distribuida y NO sustituye automáticamente la clave de idempotencia (un mismo correlation_id puede abarcar múltiples operaciones o eventos).
3. Sólo pueden coincidir si el Task Contract define explícitamente esa equivalencia y su cardinalidad.
4. La entidad de persistencia posee una restricción UNIQUE sobre la clave de idempotencia.
5. Operación atómica de inserción condicional (insert-if-absent):
   - En PostgreSQL: INSERT INTO ... ON CONFLICT (key) DO NOTHING RETURNING id;
   - Si retorna ID: Esta transacción es el ganador (owner) y ejecuta el efecto.
   - Si no retorna ID: La clave ya existía (ejecutada o en proceso); NO se repite el efecto.
6. Si la operación previa ya concluyó, se devuelve el resultado persistido idéntico.
7. El schema, estados y API concretos serán determinados por su respectivo Task Contract.
```

---

## Regla: SQL Directo sobre Tablas Gestionadas por el ORM

> **SQL directo que modifica tablas gestionadas por el ORM requiere decisión explícita y justificada.**

### Cuándo Evaluar SQL Directo vs ORM

| Escenario | Vía Recomendada | Criterio de Decisión |
|---|---|---|
| Lógica de negocio, estados, flujos estándar | **ORM** | Preserva tracking, computed fields, bus notifications y constraints |
| Claim concurrente de colas | **Evaluar primero Odoo pinned** | Odoo 19 dispone de la API privada `try_lock_for_update()` con `SKIP LOCKED` sobre recordsets. No asumir que satisface por sí sola el algoritmo de selección/orden/claim. SQL directo sólo si el Task Contract exige una operación atómica que la API nativa no puede expresar y se completa el checklist. |
| Heartbeat / renovación de lease | **ORM por defecto** | Usar ORM salvo que el Task Contract autorice SQL directo por motivos demostrados de atomicidad/performance (<20ms) y se documente el checklist SQL completo. |
| Mutación de inventario (`stock.quant`) | **ORM Exclusivo** | `_merge_quants()`, locks y dependencias internas de Odoo son obligatorias. |

### Checklist y Template Obligatorio para SQL Directo

Antes de introducir cualquier `cr.execute(UPDATE/INSERT/DELETE ...)` sobre tablas ORM, es obligatorio documentar en el código el siguiente bloque de justificación:

```python
# ==============================================================================
# SQL DIRECTO DELIBERADO
# Contexto: [Explicar la operación y por qué se ejecuta en este punto]
# Justificación frente al ORM: [Ej. Performance budget < 20ms / Lock puntual]
# Flush previo: [Qué modelo/campos deben persistirse con flush_model() antes del SQL]
# IDs afectados: [Cómo se identifican: RETURNING id / selección lockeada previa]
# Cache posterior: [browse(affected_ids).invalidate_recordset(fnames=[...])]
# Dependencias stored: [browse(affected_ids).modified([...]) si aplica]
# Tracking: [Indicar si el campo tiene tracking=True y cómo se gestiona]
# write_date / write_uid: [Indicar si se actualizan manualmente en el SQL]
# Constraints: [Indicar si se validan las restricciones del modelo]
# ==============================================================================
```

---

## Anti-patrones Prohibidos

| Anti-patrón | Problema | Solución correcta |
|---|---|---|
| Lock masivo mientras Python calcula | Bloquea a N operadores | Calcular sin lock, luego atomic claim de 1 registro |
| Transacción abierta durante escaneo humano | Bloquea filas durante minutos | Transacción corta (<200ms) + lease |
| `safe_eval` en reglas | Ejecución de código arbitrario | DSL tipada (ADR-018) |
| Mutación SQL directa de `stock_quant` | Bypasea `_merge_quants()` y reservas | Usar mecanismo ORM de Odoo 19 |
| Creación pública directa en tablas append-only | Corrompe la integridad del journal | Usar API privada multi-record (`_append_events`) |
| SQL directo sin bloque de justificación o invalidación | Corrompe cache del ORM y campos calculados | Aplicar template obligatorio, `invalidate_recordset` sobre registros y `modified()` |

---

## Checklist de Verificación Transaccional

1. ¿La transacción dura menos de 200ms en operaciones de piso?
2. ¿Se usa `FOR UPDATE SKIP LOCKED` para claim concurrente de colas?
3. ¿Las mutaciones de inventario invocan la API privada `_append_events()` sin asumir `create()` público?
4. ¿No existen mutaciones SQL directas sobre `stock.quant`?
5. ¿Todo SQL directo sobre modelos ORM incluye el bloque de justificación con flush previo, IDs afectados, invalidación sobre el recordset e invocación a `modified()` si aplica?
6. ¿La idempotencia concurrente garantiza que dos requests simultáneas no ejecuten doble efecto?
