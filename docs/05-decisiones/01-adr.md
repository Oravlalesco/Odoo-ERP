# ADR — Architecture Decision Records

> Decisiones arquitectónicas formales que garantizan consistencia a lo largo de todo el desarrollo. Cada ADR establece una regla que todos los programadores deben seguir.

---

## Contexto

### ¿Qué es un ADR?

Un **ADR (Architecture Decision Record)** — Registro de Decisión Arquitectónica — es un documento corto que captura una decisión técnica importante, su contexto y sus consecuencias. Los ADR evitan que durante años de desarrollo, distintos programadores resuelvan el mismo problema de formas diferentes.

---

## Decisiones Registradas

### ADR-001: `stock.quant` sigue siendo la fuente de verdad del inventario

**Decisión**: No crearemos una segunda base de inventario. `stock.quant` de Odoo es y seguirá siendo el registro maestro de stock.

**Consecuencia**: Todas las operaciones que afecten inventario deben pasar por el ORM de Odoo para modificar quants.

---

### ADR-002: `stock.picking` no es Work

**Decisión**: `stock.picking` es un registro logístico (Nivel A). `wms.work` es ejecución física (Nivel C). Son entidades diferentes y no deben confundirse.

**Consecuencia**: Nunca usaremos `stock.picking` para dirigir trabajo en RF.

---

### ADR-003: WMS Work se modela explícitamente

**Decisión**: Crearemos `wms.work` y `wms.work.line` como modelos explícitos con ciclo de vida propio.

**Consecuencia**: Todo trabajo dirigido pasa por el Work Engine.

---

### ADR-004: Integraciones externas son asíncronas por defecto

**Decisión**: La comunicación con sistemas externos (ERP, TMS, OMS) es asíncrona via message broker (RabbitMQ).

**Consecuencia**: Las notificaciones a sistemas externos no bloquean la operación del operador.

---

### ADR-005: RF tiene su propia API de ejecución

**Decisión**: Los dispositivos RF se comunican a través de `/api/wms/rf/v1`, una API dedicada optimizada para baja latencia.

**Consecuencia**: La API de RF no comparte endpoints con el backoffice ni con integraciones.

---

### ADR-006: PostgreSQL es el dueño de la consistencia transaccional

**Decisión**: Todas las operaciones que involucren inventario, reservas o asignación de trabajo se resuelven con transacciones PostgreSQL.

**Consecuencia**: No se delega consistencia transaccional a Redis, RabbitMQ ni ningún otro componente.

---

### ADR-007: Redis no puede ser propietario del estado del inventario

**Decisión**: Redis se usa para cache, sesiones y datos volátiles. Nunca como fuente de verdad de inventario o estado de trabajo.

**Consecuencia**: Si Redis se cae, se pierde cache pero no datos.

---

### ADR-008: La asignación de colas usa locking de base de datos

**Decisión**: La asignación de trabajo a recursos usa `SELECT ... FOR UPDATE SKIP LOCKED` de PostgreSQL.

**Consecuencia**: No hay doble asignación de trabajo. No hay espera entre operadores concurrentes.

---

### ADR-009: Las reglas son declarativas y versionadas

**Decisión**: Todas las reglas de negocio configurables (putaway, allocation, replenishment, etc.) se definen declarativamente en el Rule Engine con versionamiento.

**Consecuencia**: Los cambios de reglas no requieren cambios de código.

---

### ADR-010: Todos los comandos recibidos externamente son idempotentes

**Decisión**: Cada comando que el WMS recibe de un sistema externo debe ser idempotente — procesarlo dos veces produce el mismo resultado que una vez.

**Consecuencia**: Se requiere `idempotency_key` en todos los endpoints de integración.

---

## ADR v1.1 — Decisiones de la Revisión Arquitectónica

### ADR-011: No ampliar la identidad lógica de `stock.quant` sin análisis de impacto

**Contexto**: Odoo consolida quants con `_merge_quants()` agrupando por `(product, company, location, lot, package, owner)`. Agregar campos a esta identidad sin modificar toda la lógica interna causa fusión incorrecta de quants con estados diferentes.

**Decisión**: No se agregarán campos como `inventory_status` o `quality_status` directamente a `stock.quant` sin un análisis completo de impacto en `_merge_quants()`, gathering, reservations y moves.

**Consecuencia**: Los estados operacionales se implementan mediante ubicaciones especializadas o modelos WMS independientes.

---

### ADR-012: Inventory Status no vive inicialmente en `stock.quant`

**Decisión**: Quality Hold, Quarantine y Damage se implementan moviendo inventario a ubicaciones especializadas (`QUALITY_HOLD`, `QUARANTINE`, `DAMAGE`). Bloqueos operacionales usan `wms.inventory.block`.

**Consecuencia**: Se usa la mecánica de Odoo (mover a locations) en vez de luchar contra ella.

---

### ADR-013: `stock.package` es la base de Handling Units

**Contexto**: En Odoo 19 el modelo es `stock.package` (clase `StockPackage`, `_name = 'stock.package'`). Ya posee jerarquía, dimensiones, peso y tipos de paquete.

**Decisión**: No crearemos un modelo `wms.handling.unit` separado. La HU ES `stock.package` extendido con campos WMS.

**Consecuencia**: Se reduce significativamente el esfuerzo de la Fase HU.

---

### ADR-014: Allocation no es una segunda reserva de inventario

**Decisión**: `wms.allocation` coordina con `stock.quant.reserved_quantity` de Odoo, no crea un sistema de reserva paralelo.

**Consecuencia**: Evita double-booking de inventario.

---

### ADR-015: Work assignment usa lease + atomic claim

**Contexto**: No podemos mantener una transacción PostgreSQL abierta mientras un operador trabaja (5-10 minutos).

**Decisión**: La asignación de Work es un COMMIT atómico corto (<50ms). La protección de la asignación se mantiene mediante lease temporal con heartbeat.

**Consecuencia**: Si un operador se desconecta y el lease expira: Work en ASSIGNED (sin ejecución) → RECLAIMABLE → READY. Work en IN_PROGRESS (con ejecución) → RECONCILIATION_REQUIRED (ver ADR-025).

---

### ADR-016: Work transactions are short-lived

**Decisión**: Cada transacción que modifica `wms.work` dura menos de 200ms. No se mantienen transacciones abiertas durante la ejecución del operador.

**Consecuencia**: Cada acción RF (scan, confirm, put) es una transacción independiente.

---

### ADR-017: RF offline solo ejecuta Work previamente asignado

**Contexto**: "Offline-capable" es complejo para un WMS. Permitir obtener nuevo Work offline crearía conflictos de asignación irresolubles.

**Decisión**: Offline solo permite continuar la ejecución de Work ya asignado. El operador no puede obtener nuevo Work sin conexión.

**Consecuencia**: Requiere un local command journal con replay idempotente al reconectar.

---

### ADR-018: Rule Engine usa DSL tipada sin `safe_eval`

**Contexto**: Un motor de reglas genérico con `safe_eval` es un riesgo de seguridad y difícil de validar/simular.

**Decisión**: Las reglas usan un Typed Policy Engine con actions explícitamente whitelisted por dominio. Nunca `set arbitrary field X = Y`.

**Consecuencia**: Las reglas son deterministas, tipadas, validables y simulables.

---

### ADR-019: Operational Event + Outbox se persisten atómicamente

**Decisión**: `wms.inventory.event` y `wms.outbox` se crean dentro de la misma transacción que modifica `stock.quant`. Si el quant cambia pero el evento no se crea, es un bug.

**Consecuencia**: El Event Journal es transaccional y completo para operaciones WMS. La reconstructibilidad global del inventario queda fuera de garantía hasta cubrir todas las fuentes de mutación (backoffice, imports, manufacturing). El Outbox garantiza at-least-once delivery.

---

### ADR-020: Addons de producción se empaquetan en imagen inmutable

**Decisión**: En producción, los addons están dentro de la imagen Docker (no montados desde PVC). Cada pod ejecuta exactamente el mismo código.

**Consecuencia**: Requiere CI/CD que construya la imagen, ejecute tests y publique a registry.

---

### ADR-021: Filestore debe soportar réplicas multi-node

**Decisión**: En producción con múltiples pods, el filestore usa almacenamiento RWX (CephFS/NFS) o se externaliza a object storage.

**Consecuencia**: No se puede usar `ReadWriteOnce` PVC para filestore en arquitectura multi-pod.

---

### ADR-022: Database schema migrations son release-gated

**Contexto**: Todos los workloads usan la misma base de datos. Un `odoo -u wms_work` modifica el schema que RF está usando.

**Decisión**: Las migraciones de schema son backward-compatible y se ejecutan como parte del release protocol, no ad-hoc.

**Consecuencia**: Requiere Database Migration / Release Protocol con compatibility checks, maintenance mode y rollback rules.

---

### ADR-023: Security, Observability y Performance son cross-cutting concerns

**Decisión**: No se dejan para fases tardías. Cada motor WMS desde su primera versión emite métricas, respeta RBAC y tiene performance budget.

**Consecuencia**: Se definen BASELINE (desde Fase 3) y HARDENING (pre-producción).

---

### ADR-024: Product Logistics Profile es parte del WMS Kernel

**Decisión**: El perfil logístico del producto (`wms.product.logistics`) se desarrolla en el Programa B (Kernel) porque Putaway, Allocation, Replenishment y Slotting lo necesitan.

**Consecuencia**: Se agrega como Fase del Kernel, antes de Inbound.

---

## ADR v1.2 — Correcciones Quirúrgicas

### ADR-025: In-progress Work cannot auto-requeue after offline lease expiry

**Contexto**: Un operador offline puede tener físicamente la mercadería en sus manos. Si auto-reasignamos el Work a otro operador, se produce un doble movimiento físico (ej: 24 unidades extraídas para demanda de 12).

**Decisión**: Works en IN_PROGRESS con líneas ejecutadas van a estado `RECONCILIATION_REQUIRED` cuando el lease expira, no a READY. Solo Works en ASSIGNED sin ejecución pueden auto-requeue.

**Consecuencia**: Se requiere intervención de supervisor o reconciliación del operador original para Works parcialmente ejecutados offline.

---

### ADR-026: `stock.location.usage` conserva la semántica Odoo

**Contexto**: Odoo verifica internamente `location.usage == 'internal'` para replenishment, quant gathering y otras operaciones. Crear valores nuevos de `usage` rompe esa lógica.

**Decisión**: Agregamos `wms_location_role` como campo selection en `stock.location`. Los roles WMS (STORAGE, PICK_FACE, QUALITY_HOLD, QUARANTINE, etc.) viven en este campo, no en `usage`.

**Consecuencia**: Todas las locations WMS mantienen `usage='internal'`. La semántica WMS se lee de `wms_location_role`.

---

### ADR-027: Odoo upstream version must be pinned by digest

**Contexto**: El tag `odoo:19.0` puede avanzar sin aviso. La Capability Matrix depende de campos y métodos específicos que pueden cambiar entre commits.

**Decisión**: El proyecto fija la versión de Odoo por image digest SHA y upstream commit, no solo por tag. La Capability Matrix debe verificarse contra el commit exacto.

**Consecuencia**: Actualizaciones de Odoo upstream requieren re-verificación de la Capability Matrix y regression testing.

---

## Cómo agregar nuevos ADR

Cada nuevo ADR debe seguir este formato:

```markdown
### ADR-NNN: [Título descriptivo]

**Contexto**: ¿Por qué se necesita esta decisión?
**Decisión**: ¿Qué se decidió?
**Consecuencia**: ¿Qué implica esta decisión para el desarrollo?
**Estado**: Propuesto / Aceptado / Deprecado
**Fecha**: YYYY-MM-DD
```

---

*Documento derivado de la sección 47 del [Plan Maestro](../plan.md). Actualizado v1.1: ADR-011 a ADR-024. v1.2: ADR-025 a ADR-027.*
