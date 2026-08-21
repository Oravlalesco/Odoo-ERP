# Inventory Domain — Dominio de Inventario (v1.1)

> El inventario es la fuente de verdad del WMS. Odoo `stock.quant` sigue siendo el registro maestro. Los estados operacionales WMS **no se agregan al quant** sino que se implementan mediante ubicaciones especializadas, políticas WMS y modelos independientes.

---

## Contexto

El inventario es el activo más protegido del sistema. Cada decisión que toma el WMS — desde dónde almacenar hasta qué recolectar — depende de datos de inventario precisos, actualizados y confiables. Un error en inventario se propaga a todos los procesos downstream.

---

## Propósito

1. Mantener una **fuente de verdad única** del inventario, basada en los modelos transaccionales de Odoo
2. Implementar estados operacionales WMS **sin modificar la identidad lógica del quant**
3. Proveer tres capas de registro distintas: **Operational Event Journal**, **Audit Log** e **Integration Outbox**

---

## Diseño Funcional

### Fuente de Verdad: Modelos de Odoo

La fuente de verdad del inventario **continuará siendo Odoo**. No crearemos una segunda base de inventario.

| Modelo Odoo | En inglés | Qué representa |
|---|---|---|
| `stock.move` | Stock Move | Intención de mover inventario: un registro que dice "X unidades de producto Y deben ir de A a B" |
| `stock.move.line` | Stock Move Line | Detalle del move: lote específico, paquete, cantidad real |
| `stock.quant` | Stock Quant | **Inventario real**: cantidad de un producto en una ubicación específica, con lote y paquete. Es la foto actual del stock |

### Lo que Odoo 19 `stock.quant` YA posee

> [!IMPORTANT]
> La documentación v1.0 proponía agregar campos que **ya existen** en Odoo 19. Esto se corrige aquí.

| Campo | Ya existe | Detalle |
|---|---|---|
| `owner_id` | ✅ **Sí** | Propietario del inventario — soporta 3PL de fábrica |
| `reserved_quantity` | ✅ **Sí** | Cantidad reservada por moves |
| `available_quantity` | ✅ **Sí** | Computed: `quantity - reserved_quantity` |
| `package_id` | ✅ **Sí** | Paquete / HU donde está el inventario |
| `lot_id` | ✅ **Sí** | Lote o número de serie |
| `warehouse_id` | ✅ **Sí** | Bodega |
| `storage_category_id` | ✅ **Sí** | Categoría de almacenamiento |
| `in_date` | ✅ **Sí** | Fecha de ingreso (usado por FIFO/FEFO) |

---

## ⚠️ ADVERTENCIA P0: No modificar la identidad lógica del quant

### El Problema

Odoo consolida quants mediante `_merge_quants()` agrupando por:

```sql
GROUP BY product_id, company_id, location_id, lot_id, package_id, owner_id
```

Si agregáramos `inventory_status` o `quality_status` directamente como campos del quant **sin** modificar toda la lógica interna de gathering, merging, reservations y movimientos:

```text
Quant A: product=SKU-1, location=A03, status=AVAILABLE,   qty=100
Quant B: product=SKU-1, location=A03, status=QUARANTINE,  qty=100
```

Odoo los consideraría el **mismo quant lógico** y podría fusionarlos en uno solo con `qty=200`. Esto corrompería el inventario de forma silenciosa y catastrófica.

### La Solución: Estados WMS sin tocar el quant

> **ADR-011**: No ampliar la identidad lógica de `stock.quant` sin análisis de impacto completo.
>
> **ADR-012**: Inventory Status no vive inicialmente en `stock.quant`.

En lugar de agregar dimensiones al quant, implementamos estados operacionales así:

| Estado WMS | Implementación | Cómo funciona |
|---|---|---|
| **Quality Hold** | Location `usage='internal'` + `wms_location_role='QUALITY_HOLD'` | Odoo sigue tratándola como location interna; el WMS la excluye de allocation |
| **Quarantine** | Location `usage='internal'` + `wms_location_role='QUARANTINE'` | Misma mecánica, allocation la ignora |
| **Damaged** | Location `usage='internal'` + `wms_location_role='DAMAGE'` | Misma mecánica |
| **Available** | Inventario en location con `wms_location_role='STORAGE'` | El estado por defecto |
| **Reserved** | `stock.quant.reserved_quantity` | **Ya lo maneja Odoo** |
| **Ownership** | `stock.quant.owner_id` | **Ya lo maneja Odoo** |
| **HU Context** | `stock.quant.package_id` → `stock.package` | **Ya lo maneja Odoo** |
| **Operational Block** | `wms.inventory.block` (modelo nuevo) | Bloqueo temporal por conteo, investigación, etc. |
| **Reservation Context** | `wms.allocation` (modelo nuevo) | Para qué wave/orden se reservó — NO en el quant |

> **ADR-026 (v1.2)**: `stock.location.usage` conserva la semántica Odoo. `wms_location_role` aporta la semántica WMS.
>
> Odoo verifica internamente `location.usage == 'internal'` para replenishment, quant gathering y otras operaciones. Crear valores nuevos de `usage` rompería esa lógica.
>
> Roles WMS: `STORAGE`, `PICK_FACE`, `QUALITY_HOLD`, `QUARANTINE`, `DAMAGE`, `RECEIVING`, `STAGING`, `PACKING`, `CONSOLIDATION`, `DOCK`, `CROSS_DOCK`

Este enfoque **usa la mecánica de Odoo** (mover inventario a ubicaciones especializadas) en vez de luchar contra ella.

### Ejemplo: Quality Hold

```text
ANTES (status implícito por ubicación):
  stock.quant: SKU-A, Location=A03-R02-L04, Qty=120
  → Disponible (está en ubicación de almacenamiento)

Quality hold trigger:
  stock.move: A03-R02-L04 → WH/QUALITY-HOLD

DESPUÉS:
  stock.quant: SKU-A, Location=WH/QUALITY-HOLD, Qty=120
  → Bloqueado por calidad (está en ubicación de hold)
  → No asignable para picking (allocation ignora QUALITY-HOLD locations)

Quality release:
  stock.move: WH/QUALITY-HOLD → A03-R02-L04
  → De vuelta a disponible
```

### Bloqueo Operacional (`wms.inventory.block`) — INV-002

Para bloqueos lógicos que no implican movimiento físico (ej: inventario bloqueado durante conteo, investigación de calidad o retención aduanera):

> [!NOTE]
> `stock.quant` es una representación técnica que Odoo puede fusionar, crear y eliminar durante la operativa. Un bloqueo operacional en WMS referencia **dimensiones lógicas** (`location_id`, `product_id`, `lot_id`, `package_id`, `owner_id`), nunca `quant_id`.

#### 1. Campos Funcionales (Exactamente 12)
| Campo | Tipo | Significado | Contrato |
|---|---|---|---|
| `company_id` | Many2one (`res.company`) | Compañía propietaria del bloqueo | Requerido, default compañía actual, restrict, index |
| `block_scope` | Selection | Alcance del bloqueo | `LOCATION`, `PRODUCT_LOCATION`, `LOT`, `PACKAGE`, `OWNER_LOCATION` |
| `product_id` | Many2one (`product.product`) | Producto afectado | Opcional, restrict, check_company=True, index |
| `location_id` | Many2one (`stock.location`) | Ubicación afectada | Opcional, restrict, check_company=True, index |
| `lot_id` | Many2one (`stock.lot`) | Lote afectado | Opcional, restrict, check_company=True, index |
| `package_id` | Many2one (`stock.package`) | Paquete / HU afectado | Opcional, restrict, check_company=True, index |
| `owner_id` | Many2one (`res.partner`) | Propietario (3PL) afectado | Opcional, restrict, index |
| `block_type` | Selection | Tipo de bloqueo operacional | `CYCLE_COUNT`, `INVESTIGATION`, `HOLD`, `CUSTOMS` |
| `reason` | Text | Motivo documentado del bloqueo | Requerido |
| `blocked_by` | Many2one (`res.users`) | Usuario que originó el bloqueo | Requerido, readonly, server-owned, restrict, index |
| `blocked_at` | Datetime | Fecha/hora del bloqueo | Requerido, readonly, server-owned, index |
| `released_at` | Datetime | Fecha/hora de liberación | Readonly, index (`False` = activo) |

#### 2. Matriz de Scopes y Dimensiones Requeridas (DB CHECK)
- `LOCATION`: Exige `location_id`; las demás dimensiones deben ser nulas.
- `PRODUCT_LOCATION`: Exige `product_id` y `location_id`; las demás dimensiones deben ser nulas.
- `LOT`: Exige `product_id` y `lot_id` (con invariante `product_id == lot_id.product_id`); las demás nulas.
- `PACKAGE`: Exige `package_id`; las demás dimensiones deben ser nulas.
- `OWNER_LOCATION`: Exige `owner_id` y `location_id`; las demás dimensiones deben ser nulas.

#### 3. Inmutabilidad y Ciclo de Vida
- **Creación**: `create()` establece automáticamente `blocked_by=env.user`, `blocked_at=now()` y `released_at=False`.
- **Inmutabilidad**: Edición directa (`write()`) y eliminación (`unlink()`) están estrictamente prohibidas (`UserError`).
- **Liberación**: Se ejecuta únicamente mediante `action_release()`, autorizada para Supervisor WMS o System Admin, registrando `released_at = now()` con constraint `released_at >= blocked_at`.
- **Multi-compañía**: Controlado por `check_company=True` en dimensiones físicas y regla global `[('company_id', 'in', company_ids)]`.

#### 4. API de Matching de Bloqueos Operacionales (INV-003)
- **Consulta de Coincidencia Determinista**:
  - `_get_matching_domain(company_id, product_id, location_id, lot_id=False, package_id=False, owner_id=False)`: Construye el domain ORM determinista mediante `odoo.fields.Domain`.
  - `get_matching_blocks(...)`: Búsqueda ORM en una sola consulta de todos los bloqueos activos aplicables.
  - `is_blocked(...)`: Verificación booleana con `search_count(domain, limit=1)`.
- **Semántica Jerárquica**:
  - `LOCATION`: Bloqueo en ubicación padre afecta a todas las ubicaciones descendientes (`location_id parent_of candidate.location_id`).
  - `PACKAGE`: Bloqueo en paquete padre afecta a paquetes contenidos (`package_id parent_of candidate.package_id`).
  - `LOT`: Bloqueo de lote independiente de ubicación.
  - `PRODUCT_LOCATION` y `OWNER_LOCATION`: Jerarquía de ubicación combinada con producto o propietario exacto.
- **Frontera Arquitectónica**:
  - Consulta de solo lectura sin mutaciones ni caches externas.
  - No altera `_get_available_quantity()` nativo de Odoo ni lógica de reservas.

#### 5. Guardia de Disponibilidad Operacional WMS (INV-004)
- **Cálculo por Candidato Exacto**:
  - `get_unblocked_available_quantity(company_id, product_id, location_id, lot_id=False, package_id=False, owner_id=False)`: Evalúa disponibilidad física neta de bloqueos para un candidato lógico exacto.
  - **Filtro de Bloqueo (Short-Circuit)**: Si `is_blocked(...) == True`, retorna inmediatamente `0.0` sin consultar `stock.quant`.
  - **Coherencia Compañía-Ubicación**: Valida que `location_id.company_id` pertenezca a `company_id` o sea compartida (`False`), lanzando `AccessError` en caso de discrepancia.
  - **Disponibilidad Nativa Estricta**: Si no hay bloqueos activos, consulta `stock.quant._get_available_quantity(..., strict=True, allow_negative=False)`. `strict=True` previene agregaciones no deseadas de ubicaciones hijas sobre el candidato padre.
- **Separación de Capas**:
  - `stock.quant` mantiene la verdad física y de reservas nativas de Odoo.
  - La disponibilidad WMS aplica la política de bloqueos operacionales sobre la consulta.

#### 6. Matching Batch de Bloqueos Operacionales (INV-005)
- **Evaluación en Lote Anti-N+1**:
  - `get_blocked_quants(company_id, quants)`: Identifica cuáles quants de un recordset transitorio `stock.quant` están afectados por bloqueos activos.
  - **Fase 1 (Fetch Batch)**: Ejecuta exactamente **1 búsqueda ORM amplia** sobre `wms.inventory.block` combinando los scopes requeridos con `Domain.OR`.
  - **Fase 2 (Exact Matching en Memoria)**: Evalúa las restricciones dimensionales exactas en memoria (Python) mediante `parent_path.startswith(...)` y tuplas de producto/lote/propietario, garantizando paridad semántica con `is_blocked()` y previniendo falsos positivos por producto cruzado (*cross-product false positives*).
- **Invariantes Arquitectónicos**:
  - **Cero Persistencia**: `wms.inventory.block` no almacena `quant_id` ni crea tablas intermedias; `stock.quant` se usa transitoriamente como candidato de consulta.
  - **Seguridad**: Aplica `check_access("read")` antes de procesar el lote y valida coherencia de compañía en cada quant (`location_id.company_id`).

#### 7. Disponibilidad Agregada Block-Aware (INV-006)
- **Cálculo en Subárbol (`strict=False`)**:
  - `get_aggregate_unblocked_available_quantity(company_id, product_id, location_id, lot_id=False, package_id=False, owner_id=False)`: Calcula la disponibilidad agregada en el subárbol de una ubicación raíz aplicando el filtro de bloqueos operacionales.
  - **Descubrimiento y Scoping de Quants**: Consulta nativa `_gather(product_id, location_id, ..., strict=False)` restringida mediante contexto `allowed_company_ids=[company_id.id]`.
  - **Filtrado Batch**: Aplica `get_blocked_quants(company_id, candidate_quants)` en una sola llamada y excluye los quants bloqueados.
  - **Aritmética Nativa de Odoo 19**:
    - *Untracked*: `sum(quantity) - sum(reserved_quantity)` con validación de tolerancia `uom_id.compare(total, 0.0) >= 0`.
    - *Tracked*: Agrupación por lote/untracked, sumando únicamente grupos positivos (`uom_id.compare > 0`).
  - **Invariante de Monotonicidad**: `result = min(native_scoped_available, unblocked_available)`. Bloquear un quant (incluyendo saldos negativos) jamás puede incrementar la disponibilidad agregada sobre la cantidad nativa de partida.
  - **Frontera de Dominio**: No calcula elegibilidad de roles semánticos (`wms_location_role`), ni muta inventario ni interviene en reservas (`_action_assign()`); sirve de base para el futuro motor de asignación/allocation.

---

## Tres Capas de Registro (v1.1)

> [!IMPORTANT]
> La v1.0 mezclaba tres conceptos distintos bajo "Inventory Ledger". La v1.1 los separa explícitamente porque tienen requisitos transaccionales diferentes.

### 1. Operational Event Journal (`wms.inventory.event`)

**Propósito**: Trazabilidad operacional de cada acción sobre inventario **ejecutada por el WMS**.

> **Alcance v1.2**: El journal es completo para operaciones WMS (RF, allocation, wave, replenishment). Operaciones estándar Odoo (backoffice adjustments, imports, manufacturing) pueden no generar eventos. No afirmamos reconstructibilidad total del inventario hasta demostrar cobertura de todas las mutaciones de stock.

**Requisito transaccional**: Se persiste **atómicamente** dentro de la misma transacción que modifica el inventario:

```text
BEGIN
  stock.move.line → confirmar pick
  stock.quant → reducir cantidad
  wms.inventory.event → registrar evento PICK     ← misma transacción
  wms.outbox → encolar notificación               ← misma transacción
COMMIT
```

> **ADR-019**: Operational Event + Outbox se persisten atómicamente con la transacción de stock.

Si `stock.quant` cambia pero `wms.inventory.event` no se crea, el journal deja de ser reconstruible.

### Ejemplo de Timeline

```text
12:04  RECEIVE       Supplier → RECEIVING
12:07  MOVE          RECEIVING → QUALITY-HOLD
12:18  RELEASE       QUALITY-HOLD → A03
12:22  PUTAWAY       A03 → A03-R02-L04
16:42  PICK          A03-R02-L04 → CART-12
16:50  PACK          CART-12 → BOX-993
17:03  STAGE         BOX-993 → DOCK-04
17:20  LOAD          DOCK-04 → TRUCK-21
```

### Estructura del Evento

| Campo | Significado |
|---|---|
| `timestamp` | Momento exacto con resolución de milisegundos |
| `event_type` | Tipo de evento (RECEIVE, PICK, etc.) |
| `product_id` | Producto afectado |
| `lot_id` | Lote o serial |
| `hu_id` | Unidad de manejo |
| `source_location` | Ubicación de origen |
| `dest_location` | Ubicación de destino |
| `quantity` | Cantidad |
| `operator_id` | Operador que ejecutó la acción |
| `device_id` | Dispositivo RF |
| `work_id` | Trabajo asociado |
| `correlation_id` | ID de correlación |
| `warehouse_id` | Bodega |

### 2. Audit Log (`wms.audit.log`)

**Propósito**: Registro inmutable de quién hizo qué, cuándo, desde dónde. Orientado a cumplimiento y seguridad.

Detalle en [Auditoría](../03-plataforma/05-auditoria.md).

### 3. Integration Outbox (`wms.outbox`)

**Propósito**: Eventos que deben notificarse a sistemas externos (ERP, TMS, BI). Se persiste atómicamente con la acción, se consume asincrónicamente por integration workers.

Detalle en [Integración](../03-plataforma/01-integracion.md).

---

## Relación con Odoo

### Modelos Reutilizados

| Modelo | Qué reutilizamos |
|---|---|
| `stock.quant` | Inventario real — fuente de verdad (sin modificar identidad) |
| `stock.move` | Movimientos transaccionales de inventario |
| `stock.move.line` | Detalle de movimientos (lote, paquete, qty) |
| `stock.lot` | Lotes y números de serie |

### Modelos Extendidos

| Modelo | Extensión |
|---|---|
| `stock.location` | Nuevos tipos de ubicación: `QUALITY_HOLD`, `QUARANTINE`, `DAMAGE` |
| `stock.lot` | Campo `quality_status` a nivel de lote (no de quant) |

### Modelos Nuevos

| Modelo | Propósito |
|---|---|
| `wms.inventory.event` | Journal operacional de eventos de inventario |
| `wms.inventory.block` | Bloqueos operacionales sin movimiento físico |
| `wms.audit.log` | Log de auditoría inmutable |
| `wms.outbox` | Outbox de integración (transaccional) |

---

## Concurrencia y Protección

El inventario es el dominio más expuesto a problemas de concurrencia. Múltiples operadores pueden estar intentando:

- Reservar el mismo stock para diferentes pedidos
- Confirmar picks que reducen la misma cantidad
- Ajustar inventario mientras se ejecuta un conteo

Las operaciones críticas sobre inventario usarán **locking explícito** en PostgreSQL (`SELECT ... FOR UPDATE`) para garantizar consistencia. Ver [Transaction Architecture](../03-plataforma/00-transaction-architecture.md) y [Disponibilidad](../03-plataforma/06-disponibilidad.md).

---

## Dependencias

```mermaid
graph LR
    WM["01 Warehouse Master"] --> INV["02 Inventory"]
    HU["03 Handling Units"] --> INV
    INV --> WE["04 Work Execution"]
    INV --> AL["10 Allocation"]
    INV --> IC["14 Inventory Control"]
    INV --> CT["16 Control Tower"]
```

---

## Referencias

- Odoo 19 — Stock module (Community LGPL)
- [Capability Matrix](00-odoo19-capability-matrix.md) — campos existentes en `stock.quant`

---

*Documento corregido en v1.1. Cambios principales: eliminada propuesta de agregar `inventory_status`/`quality_status`/`owner_id` al quant (ADR-011/012), separados Event Journal / Audit Log / Outbox (ADR-019), documentados campos que ya existen en Odoo 19.*
