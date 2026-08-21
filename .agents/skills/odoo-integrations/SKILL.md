---
name: odoo-integrations
description: >-
  Usar este skill cuando el usuario pida implementar integraciones con sistemas
  externos (ERP, TMS, OMS), crear APIs REST/JSON-RPC, implementar el patrón
  inbox/outbox, configurar RabbitMQ, o desarrollar controllers HTTP para el WMS.
  Incluye la arquitectura de integración del proyecto (ADR-004, ADR-010) y los
  patrones de mensajería asíncrona.
---

# Integraciones Externas — Odoo 19

Guía para diseñar e implementar integraciones con sistemas externos mediante APIs HTTP y mensajería asíncrona.

> **ADR-004**: Integraciones externas son asíncronas por defecto.
> **ADR-010**: Todos los comandos recibidos externamente son idempotentes.

---

## 🛑 Regla de Madurez Arquitectónica (INV-AGENT-008)

Los componentes de integración del proyecto se dividen en cuatro estados de madurez:

| Estado | Significado | Regla de Uso |
|---|---|---|
| **IMPLEMENTED** | Existe en `develop` y tiene tests | Reutilizable según su firma pública |
| **PLANNED** | Aprobado en ADR, asignado a un slice futuro | NO instanciar hasta que su Task Contract lo implemente |
| **DEFERRED** | Diseñado pero pospuesto (ej. workers RabbitMQ) | NO implementar especulativamente |
| **EXAMPLE ONLY** | Pseudocódigo ilustrativo de esta skill | NO copiar como código de producción |

> **⚠️ Regla**: Los ejemplos de Inbox, Outbox, RabbitMQ, DLQ y manual commits (`cr.commit()`) en esta skill son **patrones objetivo**.
> Está estrictamente prohibido crear tablas de integración o workers anticipados sin un Task Contract explícito.

---

## Matriz de Decisión: Síncrono vs Asíncrono

| Criterio | Integración Síncrona (HTTP REST/JSON-RPC) | Integración Asíncrona (Inbox/Outbox/Colas) |
|---|---|---|
| **Propósito** | El cliente necesita el resultado inmediatamente para continuar | El efecto secundario puede desacoplarse sin bloquear la operación |
| **Ejemplos** | Consulta de inventario en tiempo real, validación de barcode, lookup de orden | Confirmación de recepción a ERP externo, publicación de eventos WMS, sincronización masiva |
| **Impacto en Transacción** | La transacción del llamador espera la respuesta de red | La transacción local es corta (<200ms); el envío/procesamiento ocurre en background |
| **Tolerancia a Caídas** | Si el sistema externo no responde, la llamada falla | Si el sistema externo cae, el mensaje queda en outbox para retry automático |
| **Regla del Proyecto** | Usar solo cuando la respuesta inmediata es estrictamente requerida | **Patrón por defecto** para comunicación entre sistemas (ADR-004) |

---

## 1. [EXAMPLE ONLY] Controladores HTTP en Odoo 19

En Odoo 19, las consultas HTTP tipo GET que devuelven JSON usan `type='http'` y `request.make_json_response()`. Las llamadas RPC tipo comando POST usan `type='jsonrpc'`.

```python
# controllers/wms_api.py (EJEMPLO CONCEPTUAL)
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WmsApiController(http.Controller):
    """API REST / JSON-RPC del WMS — /api/wms/v1."""

    # Consulta HTTP GET con respuesta JSON
    @http.route('/api/wms/v1/inventory', type='http', auth='bearer',
                methods=['GET'], csrf=False)
    def get_inventory(self, product_code=None, warehouse_code=None, **kwargs):
        """Consulta de inventario disponible para sistemas externos."""
        domain = [('quantity', '>', 0)]
        if product_code:
            domain.append(('product_id.default_code', '=', product_code))
        if warehouse_code:
            domain.append(('warehouse_id.code', '=', warehouse_code))

        quants = request.env['stock.quant'].search(domain)
        data = [{
            'product_code': q.product_id.default_code,
            'product_name': q.product_id.name,
            'location': q.location_id.complete_name,
            'quantity': q.quantity,
            'reserved': q.reserved_quantity,
        } for q in quants]
        return request.make_json_response(data)

    # Comando RPC POST idempotente
    @http.route('/api/wms/v1/inbound-orders', type='jsonrpc', auth='bearer',
                methods=['POST'], csrf=False)
    def create_inbound_order(self, **kwargs):
        """Recepción de orden con validación obligatoria de idempotencia."""
        idempotency_key = request.httprequest.headers.get('X-Idempotency-Key')
        if not idempotency_key:
            return {'error': 'El encabezado X-Idempotency-Key es obligatorio.'}
        # Procesamiento bajo Task Contract específico...
        return {'status': 'ok'}
```

### Autenticación HTTP en Odoo 19

| Valor | Significado | Cuándo usar |
|---|---|---|
| `bearer` | Token Bearer en header `Authorization` | APIs externas consumidas por ERP/TMS/OMS |
| `user` | Sesión de usuario Odoo (cookie) | Backoffice web |
| `public` | Sin autenticación (usuario público) | Portales públicos |
| `none` | Sin autenticación ni entorno de usuario | Handlers de infraestructura básica |

---

## 2. [TARGET PATTERN] Patrón Inbox (Mensajes Entrantes)

*Patrón conceptual para cuando el slice de recepción asíncrona sea planificado (sin defaults prematuros).*

```python
# ⚠️ EJEMPLO CONCEPTUAL — NO CREAR SIN TASK CONTRACT
class WmsInbox(models.Model):
    """Cola de mensajes entrantes de sistemas externos."""
    _name = 'wms.inbox'
    _description = 'Bandeja de Entrada WMS'
    _order = 'received_at asc'

    message_id = fields.Char(string='ID del Mensaje', required=True, index=True)
    message_type = fields.Selection([
        ('INBOUND_ORDER', 'Orden de Entrada'),
        ('OUTBOUND_ORDER', 'Orden de Salida'),
    ], string='Tipo de Mensaje', required=True)
    payload = fields.Text(string='Carga Útil (JSON)', required=True)
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('processing', 'En Proceso'),
        ('done', 'Procesado'),
        ('error', 'Error'),
        ('dlq', 'Error Definitivo'),
    ], string='Estado', required=True)
    received_at = fields.Datetime(string='Fecha y Hora de Recepción', required=True)

    _message_id_unique = models.Constraint(
        'UNIQUE(message_id)',
        'El ID del mensaje debe ser único para garantizar idempotencia.')
```

---

## 3. [TARGET PATTERN] Patrón Outbox (Eventos de Salida)

*El Outbox transaccional completo corresponde al slice INV-010.*

**ADR-019**: El registro en outbox se persiste atómicamente en la misma transacción que el evento operacional y el cambio de stock.

```python
# ⚠️ EJEMPLO CONCEPTUAL — NO CREAR SIN TASK CONTRACT
class WmsOutbox(models.Model):
    """Cola de eventos de salida hacia sistemas externos."""
    _name = 'wms.outbox'
    _description = 'Bandeja de Salida WMS'
    _order = 'created_at asc'

    event_type = fields.Selection([
        ('RECEIPT_CONFIRMED', 'Recepción Confirmada'),
        ('PICK_CONFIRMED', 'Recolección Confirmada'),
    ], string='Tipo de Evento', required=True)
    payload = fields.Text(string='Carga Útil (JSON)', required=True)
    correlation_id = fields.Char(string='ID de Correlación', index=True, required=True)
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('sent', 'Enviado'),
        ('dlq', 'Error Definitivo'),
    ], string='Estado', required=True)
    created_at = fields.Datetime(string='Fecha y Hora de Creación', required=True)
```

---

## 4. [TARGET ARCHITECTURE] Propiedades de Entrega y Confiabilidad

Cuando un Task Contract habilite mensajería asíncrona, el diseño técnico debe contemplar las siguientes propiedades sin crear código especulativo previo:

1. **Semántica de Entrega At-Least-Once**:
   - Cada mensaje debe persistirse antes de confirmarse.
   - El consumidor debe ser estrictamente idempotente para tolerar entregas duplicadas.
2. **Política de Reintentos y Backoff**:
   - Reintentos automáticos ante errores transitorios de red o caídas temporales del destino.
   - Límite máximo de reintentos (ej. 3 a 5 intentos con backoff exponencial) para evitar saturación.
3. **Dead Letter Queue (DLQ / Error Definitivo)**:
   - Tras agotar los reintentos, el mensaje pasa a estado terminal DLQ.
   - Los mensajes venenosos (poison messages / payload corrupto) se aíslan sin bloquear el procesamiento de mensajes posteriores.
4. **Trazabilidad y Observabilidad**:
   - Propagación obligatoria de `correlation_id` para vincular logs a través de sistemas distribuidos (no confundiéndolo con la clave de idempotencia).
   - Capacidad de inspección humana y reejecución manual (replay) desde el backoffice tras corregir datos erróneos.

---

## Headers de Integración

| Header | Ámbito | Propósito |
|---|---|---|
| `X-Idempotency-Key` | Obligatorio en POST/PUT/DELETE | Garantiza idempotencia estricta (ADR-010) |
| `X-Correlation-ID` | Opcional / Recomendado (según contrato) | Trazabilidad del flujo distribuido entre sistemas |
| `Authorization` | Obligatorio | Bearer token de autenticación |
| `Content-Type` | Obligatorio | `application/json` |

---

## Checklist de Verificación de Integraciones

1. ¿Los endpoints POST/PUT/DELETE exigen y validan `X-Idempotency-Key`?
2. ¿Las consultas GET usan `type='http'` con `make_json_response()` y los RPC POST usan `type='jsonrpc'`?
3. ¿Se aplicó la matriz síncrono vs asíncrono para no bloquear transacciones operacionales con llamadas externas?
4. ¿Se evitó crear modelos de Inbox/Outbox o RabbitMQ especulativos sin Task Contract (INV-AGENT-008)?
5. ¿No se introdujeron `cr.commit()` o `cr.rollback()` manuales en código transaccional ordinario?
6. ¿Todos los strings, labels de Selection y comentarios están 100% en español (INV-AGENT-001)?
