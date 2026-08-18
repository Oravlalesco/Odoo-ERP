# Disponibilidad — Tolerancia a Fallos, Concurrencia e Idempotencia

> El sistema debe tolerar crashes de pods, reintentos, duplicados y desconexiones sin provocar picks duplicados, reservas duplicadas o embarques duplicados.

---

## Contexto

En un almacén 24/7 con 250 operadores, los fallos no son excepciones — son certezas estadísticas. Un pod se reiniciará, un operador perderá señal WiFi, un worker procesará el mismo mensaje dos veces. El sistema debe estar diseñado para tolerar todo esto **sin corromper el inventario**.

---

## Fallos que el Sistema Debe Tolerar

| Fallo | En inglés | Descripción |
|---|---|---|
| **Crash de pod** | Pod Crash | Un pod se reinicia inesperadamente |
| **Crash de worker** | Worker Crash | Un proceso de background se detiene |
| **Reintento** | Retry | Un mensaje se procesa más de una vez |
| **Evento duplicado** | Duplicate Event | El mismo evento llega dos veces desde un sistema externo |
| **Interrupción de red** | Network Interruption | Pérdida temporal de conectividad |
| **Mantenimiento de nodo** | Node Maintenance | Un servidor físico se apaga para mantenimiento |

---

## Consecuencias que NO Deben Ocurrir

| Consecuencia | En inglés | Cómo se previene |
|---|---|---|
| **Pick duplicado** | Duplicate Pick | Locking de work con `FOR UPDATE SKIP LOCKED` |
| **Embarque duplicado** | Duplicate Shipment | Idempotencia en el cierre de embarque |
| **Reserva duplicada** | Duplicate Reservation | Transacciones atómicas sobre `stock.quant` |

---

## Idempotencia

### ¿Qué es Idempotencia?

**Idempotencia** (*Idempotency*) significa que ejecutar la misma operación dos o más veces produce exactamente el mismo resultado que ejecutarla una sola vez. Es la protección fundamental contra duplicados.

### ¿Dónde se aplica?

| Componente | Implementación |
|---|---|
| **API externa** | Cada request tiene un `idempotency_key`; si se recibe dos veces, la segunda se descarta |
| **Work assignment** | `FOR UPDATE SKIP LOCKED` previene doble asignación |
| **Inventory events** | Cada evento tiene un `event_id` único; duplicados se detectan y descartan |
| **Integration inbox** | Cada mensaje tiene un `message_id`; procesamiento es idempotente |

### Patrón de Implementación

```text
1. Recibir comando con idempotency_key
2. Buscar en tabla de procesados: ¿ya existe este key?
   → Sí: retornar respuesta original (no reprocesar)
   → No: ejecutar comando, guardar resultado con key
3. Retornar resultado
```

---

## Concurrencia a Gran Escala

### El Desafío

```text
250 RF devices concurrentes

50 → Picking       (solicitan work cada 30-60 segundos)
35 → Putaway       (solicitan work cada 60-120 segundos)
20 → Replenishment (solicitan work cada 120 segundos)
10 → Counts        (solicitan work cada 180 segundos)
40 → Packing       (confirman packs cada 30-60 segundos)
...
```

Esto genera aproximadamente **5-10 transacciones por segundo** contra las tablas críticas del WMS.

### La Solución: PostgreSQL como Garante

| Mecanismo PostgreSQL | Propósito |
|---|---|
| **ACID transactions** | Garantizar consistencia de cada operación |
| **`FOR UPDATE`** | Bloquear filas durante transacción |
| **`SKIP LOCKED`** | No esperar por filas ya bloqueadas |
| **Serializable isolation** | Para operaciones que requieren consistencia total |
| **Advisory locks** | Para secciones críticas que no involucran filas directamente |

### Principio Arquitectónico

> **PostgreSQL es el dueño de la consistencia transaccional. Redis no puede ser propietario del estado del inventario.**

Redis se usa para cache, sesiones y datos volátiles. Pero la fuente de verdad de inventario, work y reservas **siempre es PostgreSQL**.

---

## Recuperación ante Fallos

| Escenario | Comportamiento |
|---|---|
| Pod RF se reinicia | Operador reconecta, el work que tenía asignado sigue en estado `assigned` y se le devuelve |
| Worker crash durante wave | La transacción no se commitió → se revierte automáticamente → otro worker retoma |
| Red cae durante pick | La confirmación no llegó → el work sigue en `in_progress` → operador puede reintentar |
| Nodo se apaga | K8s re-schedula los pods en otros nodos → PDB garantiza disponibilidad mínima |

---

*Documento derivado de la sección 44 del [Plan Maestro](../plan.md).*
