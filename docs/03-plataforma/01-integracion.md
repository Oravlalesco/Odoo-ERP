# Integración — API, Contratos, Síncrono vs Asíncrono

> Capa de integración que protege el ORM de accesos directos externos, con API versionada, contratos formales, inbox/outbox pattern e idempotencia.

---

## Contexto

### ¿Por qué una capa de integración?

No permitiremos que otros sistemas accedan directamente al ORM de Odoo. Las razones:

| Riesgo sin API | Consecuencia |
|---|---|
| Acceso directo al ORM | Otro sistema puede corromper el estado del inventario |
| Sin contratos | Cambios internos rompen integraciones sin previo aviso |
| Sin idempotencia | Reintentos generan duplicados |
| Sin versionamiento | Imposible evolucionar sin romper clientes |

---

## API del WMS

### Endpoint Base

```text
/api/wms/v1
```

### Contratos (Recursos Expuestos)

| Recurso | En inglés | Qué representa |
|---|---|---|
| **Orden de entrada** | InboundOrder | Instrucción de recibir mercadería |
| **Orden de salida** | OutboundOrder | Instrucción de despachar mercadería |
| **Inventario** | Inventory | Consulta de stock actual |
| **Recepción** | Receipt | Confirmación de recepción |
| **Embarque** | Shipment | Estado y confirmación de despacho |
| **Unidad de manejo** | HU | Estado y ubicación de una HU |
| **Estado** | Status | Estado de una orden o proceso |
| **Evento** | Event | Eventos para integración (webhook/outbox) |

### Infraestructura de Integración

| Componente | En inglés | Significado |
|---|---|---|
| **Bandeja de entrada** | Inbox | Cola de mensajes recibidos de sistemas externos, procesados de forma ordenada |
| **Bandeja de salida** | Outbox (`wms.outbox`) | Persistencia transaccional de eventos generados por el WMS como **base para entrega at-least-once** (INV-010A). Domain-neutral, 12 campos funcionales, UUID4 global server-owned, API `_enqueue_messages()`. |
| **Idempotencia** | Idempotency | Garantía de que procesar el mismo mensaje dos veces no genera efecto duplicado (`message_id` para outbound / `idempotency_key` para comandos inbound) |
| **ID de correlación** | Correlation ID | Identificador único (`correlation_id`) que permite rastrear un flujo o batch completo a través de múltiples transacciones y sistemas |
| **Reintento** | Retry | Lógica de reintento automático para mensajes que fallan (diferido al dispatcher asíncrono) |
| **Cola de error** | DLQ (Dead Letter Queue) | Cola donde se envían mensajes que no pudieron procesarse tras N reintentos (`status='DEAD'`, diferido al dispatcher) |
| **Versión de esquema** | Schema Version | Versionamiento estricto de los contratos (`schema_version > 0`) para permitir evolución sin romper consumidores |

> [!NOTE]
> **Frontera de Entrega y ADR-019 (v1.2)**:
> INV-010A provee el núcleo de persistencia transaccional del Outbox. La frontera atómica que une mutación física de stock + `wms.inventory.event` + `wms.outbox` en una sola transacción se implementa en **INV-010B**.
> La entrega real de mensajes (dispatcher en background, RabbitMQ, políticas de reintento y transiciones a `SENT`/`DEAD`) constituye la capa asíncrona posterior.


---

## Síncrono vs Asíncrono

### Regla Principal

| Tipo | Cuándo | Ejemplos |
|---|---|---|
| **Síncrono** | Lo que el operario necesita para continuar su trabajo **ahora** | Scan, Reserve, Pick, Put, Work assignment, HU validation |
| **Asíncrono** | Lo que puede ocurrir después sin bloquear al operario | ERP notification, TMS, Reporting, Emails, Analytics, Heavy waves, Optimization, Exports |

### ¿Por qué importa la distinción?

Un operador con RF no puede esperar 5 segundos a que el ERP confirme una notificación. Su operación se mide en **sub-segundo**. Pero el ERP puede recibir la notificación 30 segundos después sin problema.

### Implementación

| Síncrono | Asíncrono |
|---|---|
| API directa (HTTP request-response) | Cola de mensajes (RabbitMQ) |
| < 200ms response time | Procesado por workers en background |
| PostgreSQL transactions | Event-driven |

---

*Documento derivado de las secciones 36-37 del [Plan Maestro](../plan.md).*
