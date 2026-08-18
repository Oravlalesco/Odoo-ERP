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

*Documento derivado de la sección 47 del [Plan Maestro](../plan.md).*
