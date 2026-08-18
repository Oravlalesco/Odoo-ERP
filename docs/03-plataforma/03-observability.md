# Observability — Monitoreo de Plataforma y Negocio

> Dos niveles de observabilidad: métricas técnicas de infraestructura y métricas de negocio operacional del almacén.

---

## Contexto

**Observability** (Observabilidad) es la capacidad de entender el estado interno de un sistema a partir de sus salidas externas: métricas, logs y traces. En un WMS industrial, necesitamos observabilidad en dos niveles simultáneamente.

---

## Nivel 1: Plataforma (Técnico)

Métricas de infraestructura que el equipo de operaciones IT monitorea:

| Métrica | En inglés | Significado |
|---|---|---|
| **CPU** | CPU | Uso de procesador por pod/nodo |
| **RAM** | RAM | Uso de memoria |
| **Pods** | Pods | Estado y cantidad de pods activos |
| **Conexiones DB** | DB Connections | Conexiones activas a PostgreSQL |
| **Queries** | Queries | Queries lentas, frecuencia, duración |
| **Locks** | Locks | Bloqueos activos en la base de datos |
| **Deadlocks** | Deadlocks | Bloqueos mutuos (dos transacciones esperándose mutuamente) |
| **RabbitMQ** | RabbitMQ | Profundidad de colas, consumidores activos |
| **Latencia** | Latency | Tiempo de respuesta de los endpoints |
| **Errores** | Errors | Tasa de errores HTTP (5xx, 4xx) |

---

## Nivel 2: Negocio (Operacional)

Métricas que el equipo de operaciones del almacén monitorea:

| Métrica | En inglés | Significado |
|---|---|---|
| **Pedidos esperando** | Orders Waiting | Pedidos liberados sin work generado |
| **Trabajo listo** | Work Ready | Works en cola esperando asignación |
| **Antigüedad de trabajo** | Work Aging | Tiempo máximo que un work lleva esperando |
| **Profundidad de cola** | Queue Depth | Cantidad de items por cola |
| **Picks/hora** | Picks/Hour | Velocidad de recolección |
| **Putaway/hora** | Putaway/Hour | Velocidad de almacenamiento |
| **Progreso de wave** | Wave Progress | Porcentaje de completación de la wave activa |
| **Utilización de docks** | Dock Utilization | Porcentaje de muelles en uso |
| **Precisión de inventario** | Inventory Accuracy | Porcentaje de ubicaciones con inventario correcto |
| **Short picks** | Short Picks | Cantidad de picks fallidos por falta de stock |
| **Backlog de reposición** | Replenishment Backlog | Pick faces pendientes de reposición |

Estas métricas alimentan tanto el [Control Tower](../02-operaciones/03-control-tower.md) como dashboards de gestión.

---

*Documento derivado de la sección 40 del [Plan Maestro](../plan.md).*
