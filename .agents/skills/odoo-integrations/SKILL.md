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

Guía para implementar integraciones con sistemas externos usando el patrón inbox/outbox, API REST y mensajería asíncrona.

> **ADR-004**: Integraciones externas son asíncronas por defecto.
> **ADR-010**: Todos los comandos recibidos externamente son idempotentes.

---

## Arquitectura de Integración

```text
                 ┌─────────────────┐
                 │ Sistema Externo  │
                 │ (ERP/TMS/OMS)   │
                 └───────┬─────────┘
                         │
            ┌────────────┴────────────┐
            │                         │
     Síncrono (HTTP)          Asíncrono (RabbitMQ)
            │                         │
            ▼                         ▼
    ┌───────────────┐        ┌───────────────┐
    │  API REST     │        │    Inbox      │
    │  /api/wms/v1  │        │  (Cola)       │
    └───────┬───────┘        └───────┬───────┘
            │                        │
            ▼                        ▼
    ┌─────────────────────────────────────┐
    │         Capa de Integración WMS     │
    │  - Validación de contratos          │
    │  - Idempotencia                     │
    │  - Correlation ID                   │
    └───────────────┬─────────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────────┐
    │         ORM de Odoo                 │
    │    (stock.quant, wms.work, etc.)    │
    └───────────────┬─────────────────────┘
                    │
                    ▼
    ┌───────────────────────┐
    │       Outbox          │
    │  (Eventos de salida)  │
    └───────────────────────┘
```

### Síncrono vs Asíncrono

| Tipo | Cuándo | Latencia | Ejemplos |
|---|---|---|---|
| **Síncrono** | El operario necesita respuesta **ahora** | < 200ms | Scan, reserve, pick, put, consulta de stock |
| **Asíncrono** | Puede ocurrir después sin bloquear | Segundos a minutos | Notificación ERP, TMS, reporting, exports, waves pesadas |

---

## 1. Controllers HTTP (API REST)

### Estructura del Controller

```python
# controllers/__init__.py
from . import wms_api

# controllers/wms_api.py
import json
import logging
from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class WmsApiController(http.Controller):
    """API REST del WMS — /api/wms/v1."""

    # =========================================================================
    # Inventario (consulta)
    # =========================================================================

    @http.route('/api/wms/v1/inventory', type='jsonrpc', auth='bearer',
                methods=['GET'], csrf=False)
    def get_inventory(self, product_code=None, warehouse_code=None,
                      location_barcode=None, **kwargs):
        """
        Consulta de inventario disponible.

        Args:
            product_code: Código del producto (opcional)
            warehouse_code: Código de bodega (opcional)
            location_barcode: Barcode de ubicación (opcional)

        Returns:
            Lista de quants con cantidades disponibles.
        """
        domain = [('quantity', '>', 0)]
        if product_code:
            domain.append(('product_id.default_code', '=', product_code))
        if warehouse_code:
            domain.append(('warehouse_id.code', '=', warehouse_code))
        if location_barcode:
            domain.append(('location_id.barcode', '=', location_barcode))

        quants = request.env['stock.quant'].search(domain)
        return [{
            'product_code': q.product_id.default_code,
            'product_name': q.product_id.name,
            'location': q.location_id.complete_name,
            'lot': q.lot_id.name or None,
            'quantity': q.quantity,
            'reserved': q.reserved_quantity,
            'available': q.available_quantity,
        } for q in quants]

    # =========================================================================
    # Órdenes de entrada (recepción)
    # =========================================================================

    @http.route('/api/wms/v1/inbound-orders', type='jsonrpc', auth='bearer',
                methods=['POST'], csrf=False)
    def create_inbound_order(self, **kwargs):
        """
        Recibe una orden de entrada desde un sistema externo.
        El header X-Idempotency-Key es obligatorio (ADR-010).
        """
        idempotency_key = request.httprequest.headers.get(
            'X-Idempotency-Key')
        if not idempotency_key:
            return {'error': 'X-Idempotency-Key header is required'}, 400

        correlation_id = request.httprequest.headers.get(
            'X-Correlation-ID', idempotency_key)

        # Verificar idempotencia
        result = request.env['wms.idempotency']._check_key(idempotency_key)
        if result == 'ALREADY_DONE':
            return request.env['wms.idempotency']._get_response(
                idempotency_key)

        # Procesar la orden...
        try:
            order = request.env['wms.asn'].create({
                'correlation_id': correlation_id,
                # ... campos de la orden ...
            })
            response = {'id': order.id, 'reference': order.name}
            request.env['wms.idempotency']._mark_done(
                idempotency_key, response)
            return response
        except Exception as e:
            _logger.error('Error creando inbound order: %s', e)
            raise
```

### Autenticación

Odoo 19 soporta los siguientes tipos de autenticación en `http.route`:

| Valor | Significado |
|---|---|
| `user` | Sesión de usuario Odoo (cookie) — para backoffice |
| `bearer` | Token Bearer en header `Authorization` — para APIs externas |
| `public` | Sin autenticación, usuario público |
| `none` | Sin autenticación ni usuario |

Para APIs del WMS consumidas por sistemas externos, usar `auth='bearer'`:

```python
@http.route('/api/wms/v1/status', type='jsonrpc', auth='bearer',
            methods=['GET'], csrf=False)
def get_status(self):
    """Endpoint con autenticación Bearer token."""
    return {'status': 'ok', 'version': '1.0'}
```

---

## 2. Patrón Inbox (Mensajes Entrantes)

El inbox procesa mensajes de sistemas externos de forma ordenada y confiable.

### Modelo `wms.inbox`

```python
class WmsInbox(models.Model):
    """Cola de mensajes entrantes de sistemas externos."""
    _name = 'wms.inbox'
    _description = 'Bandeja de entrada WMS'
    _order = 'received_at asc'

    message_id = fields.Char(
        string='ID del mensaje', required=True, index=True)
    message_type = fields.Selection([
        ('INBOUND_ORDER', 'Orden de entrada'),
        ('OUTBOUND_ORDER', 'Orden de salida'),
        ('INVENTORY_ADJUSTMENT', 'Ajuste de inventario'),
        ('CANCEL_ORDER', 'Cancelación de orden'),
    ], string='Tipo', required=True)
    payload = fields.Text(string='Payload (JSON)', required=True)
    correlation_id = fields.Char(
        string='ID de correlación', index=True)
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('processing', 'Procesando'),
        ('done', 'Procesado'),
        ('error', 'Error'),
        ('dlq', 'Dead Letter'),
    ], string='Estado', default='pending')
    retry_count = fields.Integer(string='Reintentos', default=0)
    max_retries = fields.Integer(string='Máximo reintentos', default=3)
    error_message = fields.Text(string='Mensaje de error')
    received_at = fields.Datetime(
        string='Recibido', default=fields.Datetime.now)
    processed_at = fields.Datetime(string='Procesado')

    # Odoo 19: models.Constraint reemplaza _sql_constraints
    _message_id_unique = models.Constraint(
        'UNIQUE(message_id)',
        'El ID del mensaje debe ser único (idempotencia).')
```

### Procesador de Inbox (Cron)

```python
def _process_inbox(self):
    """
    Cron: procesa mensajes pendientes del inbox.
    Cada mensaje se procesa en su propia transacción.
    """
    messages = self.search([
        ('state', '=', 'pending'),
    ], order='received_at asc', limit=100)

    for msg in messages:
        try:
            msg.state = 'processing'
            self.env.cr.commit()

            handler = self._get_handler(msg.message_type)
            handler(msg)

            msg.write({
                'state': 'done',
                'processed_at': fields.Datetime.now(),
            })
            self.env.cr.commit()

        except Exception as e:
            self.env.cr.rollback()
            msg.retry_count += 1
            if msg.retry_count >= msg.max_retries:
                msg.state = 'dlq'
                msg.error_message = str(e)
                _logger.error(
                    'Mensaje %s enviado a DLQ: %s',
                    msg.message_id, e)
            else:
                msg.state = 'pending'
                msg.error_message = str(e)
            self.env.cr.commit()
```

---

## 3. Patrón Outbox (Eventos de Salida)

**ADR-019**: El outbox se crea atómicamente con la acción que genera el evento.

### Modelo `wms.outbox`

```python
class WmsOutbox(models.Model):
    """Cola de eventos de salida hacia sistemas externos."""
    _name = 'wms.outbox'
    _description = 'Bandeja de salida WMS'
    _order = 'created_at asc'

    event_type = fields.Selection([
        ('RECEIPT_CONFIRMED', 'Recepción confirmada'),
        ('PICK_CONFIRMED', 'Pick confirmado'),
        ('SHIPMENT_READY', 'Envío listo'),
        ('INVENTORY_ADJUSTED', 'Inventario ajustado'),
        ('EXCEPTION_RAISED', 'Excepción generada'),
    ], string='Tipo de evento', required=True)
    payload = fields.Text(string='Payload (JSON)', required=True)
    correlation_id = fields.Char(string='ID de correlación', index=True)
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('sent', 'Enviado'),
        ('error', 'Error'),
        ('dlq', 'Dead Letter'),
    ], string='Estado', default='pending')
    retry_count = fields.Integer(string='Reintentos', default=0)
    created_at = fields.Datetime(
        string='Creado', default=fields.Datetime.now)
    sent_at = fields.Datetime(string='Enviado')
    target_system = fields.Char(string='Sistema destino')

    # Odoo 19: models.Constraint reemplaza _sql_constraints
    _event_unique = models.Constraint(
        'UNIQUE(event_type, correlation_id, created_at)',
        'Evento duplicado detectado.')
```

### Procesador de Outbox (Cron)

```python
def _process_outbox(self):
    """
    Cron: envía eventos pendientes a sistemas externos.
    Garantiza at-least-once delivery.
    """
    messages = self.search([
        ('state', '=', 'pending'),
    ], order='created_at asc', limit=50)

    for msg in messages:
        try:
            self._send_to_broker(msg)
            msg.write({
                'state': 'sent',
                'sent_at': fields.Datetime.now(),
            })
            self.env.cr.commit()
        except Exception as e:
            self.env.cr.rollback()
            msg.retry_count += 1
            if msg.retry_count >= 5:
                msg.state = 'dlq'
            msg.error_message = str(e)
            self.env.cr.commit()
```

---

## 4. Configuración de RabbitMQ

### Conexión desde Odoo

```python
import pika
import json

class WmsMessageBroker(models.AbstractModel):
    """Servicio de conexión a RabbitMQ."""
    _name = 'wms.message.broker'
    _description = 'Broker de mensajes WMS'

    def _get_connection(self):
        """Obtiene conexión a RabbitMQ desde parámetros del sistema."""
        params = self.env['ir.config_parameter'].sudo()
        credentials = pika.PlainCredentials(
            params.get_param('wms.rabbitmq_user', 'guest'),
            params.get_param('wms.rabbitmq_password', 'guest'),
        )
        return pika.BlockingConnection(
            pika.ConnectionParameters(
                host=params.get_param('wms.rabbitmq_host', 'localhost'),
                port=int(params.get_param('wms.rabbitmq_port', '5672')),
                credentials=credentials,
            )
        )

    def publish(self, exchange, routing_key, message):
        """Publica un mensaje en RabbitMQ."""
        connection = self._get_connection()
        try:
            channel = connection.channel()
            channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistente
                    content_type='application/json',
                ),
            )
        finally:
            connection.close()
```

### Exchanges y Queues Recomendados

| Exchange | Tipo | Routing Key | Queue | Propósito |
|---|---|---|---|---|
| `wms.events` | topic | `wms.receipt.*` | `erp.receipt.notifications` | Notificar recepciones al ERP |
| `wms.events` | topic | `wms.shipment.*` | `tms.shipment.updates` | Actualizar TMS con envíos |
| `wms.events` | topic | `wms.inventory.*` | `erp.inventory.sync` | Sincronizar inventario |
| `wms.commands` | direct | `wms.inbound` | `wms.inbox.inbound` | Órdenes de entrada |
| `wms.commands` | direct | `wms.outbound` | `wms.inbox.outbound` | Órdenes de salida |

---

## 5. Headers Obligatorios de API

| Header | Obligatorio | Propósito |
|---|---|---|
| `X-Idempotency-Key` | ✅ POST/PUT/DELETE | Garantiza idempotencia (ADR-010) |
| `X-Correlation-ID` | Recomendado | Rastreo de flujo completo entre sistemas |
| `Content-Type` | ✅ | `application/json` |
| `Authorization` | ✅ | Bearer token o API key |

---

## Consistency Checks Periódicos

| ID | Check | Frecuencia | Acción si falla |
|---|---|---|---|
| CHK-003 | Outbox con mensajes sin procesar > 5 min | Cada 1 min | Alerta + retry |
| CHK-005 | Inbox con mensajes en error > 3 retries | Cada 5 min | Mover a DLQ + alerta |

---

## Verificación

1. ¿Los endpoints POST/PUT/DELETE requieren `X-Idempotency-Key`?
2. ¿El outbox se crea en la misma transacción que el cambio de datos?
3. ¿El inbox tiene manejo de reintentos y DLQ?
4. ¿Las conexiones a RabbitMQ usan credenciales de `ir.config_parameter`?
5. ¿Los controllers usan `auth='user'` o `auth='api_key'`?
6. ¿Se loggea `correlation_id` en todas las operaciones?
