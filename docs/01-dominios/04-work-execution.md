# Work Execution — Motor de Trabajo y Motor de Colas (v1.2)

> El componente más importante de toda la plataforma. Transforma necesidades logísticas en unidades de trabajo ejecutables y las distribuye a través de colas a los recursos disponibles.
>
> **v1.2**: Máquina de estados consolidada. `CLAIMED` simplificado a transitorio. `RECLAIMABLE` solo para ASSIGNED sin ejecución. `IN_PROGRESS` con lease expirado → `RECONCILIATION_REQUIRED` (ADR-025). ACCEPT protocol invariant.

---

## Contexto

### ¿Qué es "trabajo dirigido" (Directed Work)?

En Odoo estándar, un operador abre una pantalla, ve una lista de pickings y elige uno. En un WMS industrial, el operador **no elige**: el sistema le **asigna** trabajo optimizado.

**Trabajo dirigido** (*Directed Work*) significa que el WMS:
1. Determina *qué* hay que hacer (Work Generation)
2. Organiza *cómo* distribuirlo (Queue Engine)
3. Decide *a quién* asignarlo (Assignment Engine)
4. Dirige *paso a paso* la ejecución (RF)

### ¿Por qué es el componente más importante?

Porque **todo flujo operacional** — inbound, putaway, picking, replenishment, counting, packing — se ejecuta a través de Work. Si el Work Engine no funciona correctamente, nada funciona.

---

## Propósito

> Transformar necesidades logísticas en unidades de trabajo ejecutables, organizarlas en colas y distribuirlas a recursos compatibles con alta concurrencia.

---

## Diseño Funcional del Work Engine

### ¿Qué es un Work?

Un **Work** (`wms.work`) es la unidad fundamental de ejecución del WMS. Contiene una o más líneas que indican al operador exactamente qué hacer:

```text
Work 10592

Priority 80

Line 10
  PICK                           ← Acción: recoger
  RECEIVING-04                   ← Desde: ubicación de recepción 04
  PALLET 10092                   ← Objeto: pallet con SSCC 10092

Line 20
  PUT                            ← Acción: colocar
  A04-R02-L03                    ← En: pasillo A04, rack 02, nivel 03
```

### Tipos de Work

| Tipo | En inglés | Significado | Ejemplo |
|---|---|---|---|
| **Recolección** | Pick | Extraer mercadería de una ubicación | Picking de pedido de cliente |
| **Colocación** | Put | Depositar mercadería en una ubicación | Putaway tras recepción |
| **Movimiento** | Move | Trasladar de una ubicación a otra | Reubicación interna |
| **Conteo** | Count | Contar inventario en una ubicación | Conteo cíclico |
| **Reposición** | Replenishment | Reponer una ubicación de picking | Pick face vacío |
| **Carga** | Load | Cargar mercadería en un transporte | Loading en dock |
| **Inspección** | Inspect | Verificar mercadería | Control de calidad |
| **Empaque** | Pack | Empacar mercadería | Estación de packing |

### Modelos Propuestos

| Modelo | En inglés | Propósito |
|---|---|---|
| `wms.work` | Work | Registro de trabajo con estado, prioridad, tipo, recurso asignado, **lease** |
| `wms.work.line` | Work Line | Cada paso del trabajo: acción (PICK/PUT), ubicación, producto, cantidad |
| `wms.work_type` | Work Type | Catálogo de tipos de trabajo (pick, put, move, count...) |
| `wms.work_class` | Work Class | Clasificación para agrupación y priorización (ej: "putaway-forklift", "pick-manual") |
| `wms.work_template` | Work Template | Plantilla configurable que define cómo generar trabajo para cada escenario |
| `wms.work_dependency` | Work Dependency | Relaciones de precedencia: "Work B no puede empezar hasta que Work A termine" |
| `wms.work_exception` | Work Exception | Registro de excepciones ocurridas durante la ejecución |

### Campos de Lease en `wms.work` (v1.1)

> **ADR-015**: Work assignment usa lease + atomic claim.
>
> **ADR-016**: Work transactions are short-lived.

Cuando un operador solicita trabajo, no mantenemos una transacción PostgreSQL abierta durante 5 minutos mientras trabaja. La asignación se hace con un **claim atómico** (transacción corta) y luego un **lease** (arrendamiento temporal) protege la asignación.

| Campo | En inglés | Significado |
|---|---|---|
| `claim_token` | Claim Token | Token único generado al momento del claim (UUID) |
| `assigned_resource_id` | Assigned Resource | Recurso (operador) asignado |
| `assigned_at` | Assigned At | Timestamp de asignación |
| `accepted_at` | Accepted At | Timestamp cuando el operador aceptó (escaneó primer item) |
| `lease_expires_at` | Lease Expires At | Cuándo expira el arrendamiento si no hay heartbeat |
| `last_heartbeat_at` | Last Heartbeat At | Último heartbeat recibido del dispositivo RF |
| `assignment_version` | Assignment Version | Versión incremental — evita race conditions en reasignación |
| `reclaim_count` | Reclaim Count | Cuántas veces se ha reclamado este work (detect problematic work) |

### Máquina de Estados del Work (v1.2)

```mermaid
stateDiagram-v2
    [*] --> Draft: Creado
    Draft --> Ready: Validado y listo
    Ready --> Assigned: Atomic claim
    Assigned --> InProgress: Operador ACCEPT + ACK
    InProgress --> InProgress: Línea completada
    InProgress --> Completed: Todas las líneas completadas
    InProgress --> Exception: Error o problema
    Exception --> InProgress: Resuelto
    Exception --> Cancelled: No resoluble
    Ready --> Cancelled: Cancelado
    Assigned --> Reclaimable: Lease expirado (sin ejecución)
    Reclaimable --> Ready: Auto-requeue
    InProgress --> ReconciliationRequired: Lease expirado (con ejecución)
    ReconciliationRequired --> Assigned: Supervisor / operador original
    Completed --> [*]
    Cancelled --> [*]
```

| Estado | En inglés | Significado |
|---|---|---|
| **Borrador** | Draft | Creado pero no validado |
| **Listo** | Ready | Validado, esperando asignación |
| **Asignado** | Assigned | Claim atómico ejecutado. Operador ve instrucciones pero aún no ejecutó |
| **En Progreso** | In Progress | El operador ACCEPTÓ y recibió ACK — puede ejecutar movimiento físico |
| **Completado** | Completed | Todas las líneas ejecutadas exitosamente |
| **Excepción** | Exception | Un problema detuvo la ejecución |
| **Reclamable** | Reclaimable | Lease expirado en ASSIGNED sin ejecución — auto-requeue seguro |
| **Reconciliación** | Reconciliation Required | Lease expirado en IN_PROGRESS — requiere supervisor (ADR-025) |
| **Cancelado** | Cancelled | Trabajo cancelado |

> **Nota v1.2**: `CLAIMED` ya no existe como estado persistente. El claim atómico (<50ms) transiciona directamente de `READY` a `ASSIGNED` en una sola transacción.

### ⚠️ Invariante de Ejecución: ACCEPT Protocol

> **Un operador no puede comenzar movimiento físico hasta haber recibido ACK de transición a IN_PROGRESS.**

```text
NEXT WORK
     ↓
ASSIGNED
     ↓
RF presenta trabajo al operador
     ↓
Operador: ACCEPT (escanea primer item o presiona F1)
     ↓
Server: commits IN_PROGRESS + renueva lease
     ↓
ACK al RF
     ↓
Recién ahora el operador puede ejecutar movimiento físico
```

Sin el ACK, existe una ventana donde el operador toma mercancía físicamente, pierde Wi-Fi, y el server auto-requeue el Work (porque sigue en ASSIGNED). Con ACCEPT:

| Estado | Offline + lease expiry | Riesgo físico |
|---|---|---|
| ASSIGNED (pre-ACCEPT) | → RECLAIMABLE → READY | ✅ Ninguno — operador aún no tocó mercancía |
| IN_PROGRESS (post-ACCEPT) | → RECONCILIATION_REQUIRED | ✅ Protegido — requiere supervisor |

### Generación de Work

El Work no se crea manualmente. Se genera automáticamente cuando un motor de planificación lo solicita:

```mermaid
graph TB
    IO["Inbound Order"] --> REC["Receipt"]
    REC --> PP["Putaway Planning"]
    PP --> W1["WORK: Pick from Receiving + Put to Storage"]

    OO["Outbound Order"] --> AL["Allocation"]
    AL --> WV["Wave"]
    WV --> W2["WORK: Pick from Storage + Put to Staging"]

    RP["Replenishment Trigger"] --> W3["WORK: Move from Reserve to Pick Face"]
    
    CC["Cycle Count Schedule"] --> W4["WORK: Count at Location"]
```

### Diferencia clave: `stock.picking` ≠ `wms.work`

| Concepto | `stock.picking` (Odoo) | `wms.work` (WMS) |
|---|---|---|
| **Nivel** | Registro logístico (Nivel A) | Ejecución física (Nivel C) |
| **Propósito** | Agrupar movimientos de inventario | Dirigir un operador paso a paso |
| **Quién lo usa** | Backoffice, ERP | Operador con RF en piso |
| **Granularidad** | Puede tener muchas líneas de distintas ubicaciones | Optimizado para un recorrido específico |
| **Estado** | Depende de confirmación manual | Controlado por el motor de ejecución |

---

## Diseño Funcional del Queue Engine — Motor de Colas

### ¿Qué es una Queue?

Una **Queue** (Cola) es una estructura que organiza trabajos pendientes y los filtra para distribuir solo a recursos compatibles. Work y Queue son conceptos **distintos**:

| Concepto | Pregunta que responde |
|---|---|
| **Work** | ¿Qué hay que hacer? |
| **Queue** | ¿Quién puede tomarlo? |

### Ejemplo

Una cola llamada `QUEUE-PUTAWAY-FORKLIFT-A` podría aceptar solamente trabajo que cumpla:

```text
Zone = A                         ← Solo zona A
Equipment = Forklift             ← Requiere montacarga
Certification = HighRack         ← Operador certificado para rack alto
Weight <= 1200kg                 ← Peso máximo del pallet
```

### Atributos de una Queue

| Atributo | En inglés | Significado |
|---|---|---|
| **Prioridad** | Priority | Orden de importancia de la cola |
| **Área de actividad** | Activity Area | Zona del almacén que atiende |
| **Perfil de recurso** | Resource Profile | Qué tipo de recurso puede atender esta cola |
| **Requerimiento de equipo** | Equipment Requirement | Qué equipamiento se necesita |
| **Tipo de trabajo** | Work Type | Qué tipos de trabajo acepta (pick, put, move...) |
| **Bodega** | Warehouse | En qué bodega opera |
| **Zona** | Zone | Zona específica |
| **Fecha límite** | Deadline | Hora máxima para completar el trabajo |
| **Cutoff** | Cutoff | Hora de corte operacional (ej: "todo lo de la wave de las 16:00") |

### Flujo Work → Queue → Resource

```mermaid
sequenceDiagram
    participant PL as Planning Engine
    participant WE as Work Engine
    participant QE as Queue Engine
    participant RE as Resource Engine
    participant OP as Operador (RF)

    PL->>WE: Generar Work
    WE->>WE: Validar Work
    WE->>QE: Encolar Work
    QE->>QE: Clasificar por prioridad/deadline
    OP->>RE: "NEXT WORK" (solicitar trabajo)
    RE->>QE: Buscar trabajo compatible
    QE->>QE: FOR UPDATE SKIP LOCKED
    QE-->>RE: Work seleccionado
    RE-->>OP: Asignar Work
    OP->>WE: Confirmar líneas
    WE->>WE: Completar Work
```

---

## Concurrencia: El Desafío Central

### El Problema

En un almacén industrial puede haber:

```text
250 dispositivos RF simultáneos

50 → Picking
35 → Putaway
20 → Replenishment
10 → Conteos
40 → Packing
...
```

Todos solicitando trabajo al mismo tiempo. Si dos operadores reciben el mismo trabajo, se produce una **doble asignación** que corrompe el inventario.

### La Solución: `FOR UPDATE SKIP LOCKED`

PostgreSQL provee un mecanismo específico para este patrón — múltiples consumidores de una cola:

```sql
SELECT id
FROM wms_work
WHERE state = 'ready'
  AND queue_id = %s
ORDER BY priority DESC, deadline ASC
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

| Cláusula | Significado |
|---|---|
| `FOR UPDATE` | Bloquea la fila seleccionada para que nadie más la tome |
| `SKIP LOCKED` | Si la fila ya está bloqueada por otra transacción, la salta y toma la siguiente |

Resultado:

```text
Operador A → Work 10    (Work 10 bloqueado)
Operador B → Work 11    (Work 10 saltado, toma Work 11)
Operador C → Work 12    (Work 10 y 11 saltados, toma Work 12)
```

**Sin espera entre operadores. Sin duplicación de asignaciones.**

### Garantías de Concurrencia

| Garantía | Cómo se logra |
|---|---|
| No hay doble asignación | `FOR UPDATE SKIP LOCKED` |
| No hay espera entre operadores | `SKIP LOCKED` salta filas bloqueadas |
| Consistencia transaccional | PostgreSQL ACID |
| Claim atómico | Transacción de claim < 50ms, luego COMMIT |

### ⚠️ Corrección v1.1: Crash Recovery

La v1.0 afirmaba que si un operador se desconecta, "la transacción se revierte y el Work vuelve a `ready`".

**Esto es INCORRECTO.**

La asignación de Work es un `COMMIT` atómico corto:

```sql
BEGIN;
UPDATE wms_work SET state='assigned', assigned_resource_id=129, 
  claim_token='uuid', assigned_at=now(), lease_expires_at=now()+'10min'
WHERE id=10592;
COMMIT;
```

Después del `COMMIT`, el Work está en estado `ASSIGNED`. Si el operador se desconecta, **no hay transacción abierta que revertir**.

### Work Lease Protocol

La recuperación ante desconexión funciona mediante **lease** (arrendamiento temporal):

```text
1. CLAIM (atomic, <50ms)
   Work: READY → CLAIMED → ASSIGNED
   lease_expires_at = now() + 10 min

2. HEARTBEAT (cada 30-60 segundos)
   RF envía heartbeat
   last_heartbeat_at = now()
   lease_expires_at = now() + 10 min  (renovación)

3. EXECUTION (operador trabaja)
   Cada scan/confirmación renueva el lease
   Work: ASSIGNED → IN_PROGRESS

4. Si RF se desconecta:
   No llegan más heartbeats
   Después de 10 min: lease_expires_at < now()
   
5. RECLAIM (cron job o supervisor)
   Detecta: lease expirado + no heartbeat

   SI state == ASSIGNED (sin ejecución):
     → RECLAIMABLE → READY (auto-requeue seguro)

   SI state == IN_PROGRESS (hay líneas ejecutadas):
     → RECONCILIATION_REQUIRED (NO auto-requeue)
   
6. RESOLUCIÓN:
   ASSIGNED sin ejecución:
     a) Auto-requeue: RECLAIMABLE → READY
   
   IN_PROGRESS con líneas ejecutadas:
     a) Supervisor revisa y reasigna: RECONCILIATION → ASSIGNED
     b) Supervisor cancela y genera Work compensatorio
     c) Operador original reconecta: reconcilia con claim_token
```

### ⚠️ Corrección v1.2: IN_PROGRESS no puede auto-reasignarse

> **ADR-025 (v1.2)**: In-progress Work cannot auto-requeue after offline lease expiry.

El operador A puede tener **físicamente la mercadería en sus manos**. Si auto-reasignamos:

```text
A offline: PICK 12 SKU-A (física, no confirmada en server)
B recibe el mismo PICK → PICK 12 SKU-A

Resultado: 24 unidades extraídas para demanda de 12
```

No se puede deshacer un movimiento físico con un `ROLLBACK`.

Por tanto:

| Estado al expirar lease | Resolución | Automático |
|---|---|---|
| **ASSIGNED** (sin líneas ejecutadas) | Auto-requeue a READY | ✅ Sí |
| **IN_PROGRESS** (con líneas ejecutadas) | RECONCILIATION_REQUIRED | ❌ No — requiere supervisor |

### Ejemplo: Operador pierde Wi-Fi (v1.2)

```text
17:14:02  Operador 129 claims Work 10592
         state=ASSIGNED, lease_expires=17:24:02

17:14:30  Heartbeat
         lease_expires=17:24:30

17:15:02  Confirm pick line 1
         state=IN_PROGRESS, lease_expires=17:25:02

17:15:15  *** Wi-Fi lost ***

17:25:02  Lease expired. No heartbeat en 10 min.
         state=RECONCILIATION_REQUIRED  ← NO auto-requeue
         (porque hay líneas ejecutadas)

17:25:03  Supervisor notificado vía Control Tower alert

17:28:00  Caso A: Operador 129 reconecta
         → reconcilia offline journal con server
         → Work continúa normalmente

17:28:00  Caso B: Operador 129 no aparece
         → Supervisor investiga físicamente
         → Confirma que pick ocurrió o revierte
         → Reasigna o compensa
```

### Simplificación de Estado CLAIMED (v1.2)

> **ARC-010**: `CLAIMED` es un estado transitorio dentro de la transacción atómica de claim.

```text
READY
   ↓ (atomic transaction)
ASSIGNED    ← con claim_token, lease, etc.
```

`CLAIMED` no se persiste como estado independiente porque la transacción es atómica (<50ms). Si la transacción falla, el Work queda en `READY`. No hay ventana donde un observador externo vería `CLAIMED`.

### Trabajo Parcialmente Completado

Si un Work en RECONCILIATION_REQUIRED tiene líneas ya completadas:

```text
Work 10592:
  Line 10: PICK from A03 → COMPLETED ✓ (confirmado en server)
  Line 20: PUT to B07 → PENDING (no confirmado)
```

El supervisor puede: reasignar solo las líneas pendientes a otro operador, o esperar reconciliación del operador original.

---

## Dependencias

```mermaid
graph LR
    WM["01 Warehouse Master"] --> WE["04 Work Execution"]
    INV["02 Inventory"] --> WE
    HU["03 Handling Units"] --> WE
    WE --> RES["05 Resources"]
    RULES["06 Rule Engine"] --> WE
    IN["07 Inbound"] --> WE
    PUT["08 Putaway"] --> WE
    IL["09 Internal Logistics"] --> WE
    OUT["10-12 Outbound/Picking"] --> WE
```

**El Work Execution Engine es el nexo central del sistema.** Recibe solicitudes de generación de trabajo de todos los dominios de planificación y distribuye el trabajo a los recursos.

---

## Referencias

- [SAP EWM — Warehouse Order](https://help.sap.com/docs/SAP_SUPPLY_CHAIN_MANAGEMENT/dc8e3ce481cc493aad2145b99e6c53eb/3d267d0c-463f-4bf5-b2b9-a72eac15dccc.html)
- [SAP — Queue Assignment](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/9832125c23154a179bfa1784cdc9577a/6ccdcb53ad377114e10000000a174cb4.html)
- [PostgreSQL — SELECT ... FOR UPDATE SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html)

---

*Documento derivado de las secciones 8-9 y 12 del [Plan Maestro](../plan.md). Corregido en v1.1: Work Lease Protocol (ADR-015/016), crash recovery, estados CLAIMED/RECLAIMABLE.*
