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
| **Bandeja de salida** | Outbox | Eventos generados por el WMS que se envían a sistemas externos |
| **Idempotencia** | Idempotency | Garantía de que procesar el mismo mensaje dos veces no genera efecto duplicado |
| **ID de correlación** | Correlation ID | Identificador único que permite rastrear un flujo completo a través de múltiples sistemas |
| **Reintento** | Retry | Lógica de reintento automático para mensajes que fallan |
| **Cola de error** | DLQ (Dead Letter Queue) | Cola donde se envían mensajes que no pudieron procesarse tras N reintentos |
| **Versión de esquema** | Schema Version | Versionamiento de los contratos para permitir evolución sin romper clientes |

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
