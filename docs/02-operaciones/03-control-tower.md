# Control Tower — Monitor Operacional en Tiempo Real

> Dashboard ejecutivo que muestra el estado completo del almacén: inbound, picking, packing, staging, shipping — con métricas en vivo y alertas de cuellos de botella.

---

## Contexto

Un almacén industrial necesita visibilidad en tiempo real de lo que está ocurriendo. Sin un **Control Tower** (Torre de Control), los supervisores no pueden detectar cuellos de botella, retrasos o problemas hasta que es demasiado tarde.

---

## Ejemplo de Dashboard

```text
WAREHOUSE SCL01                    17:14  2026-08-17

Inbound                    Receiving                  Putaway
13 trucks                  2,430 HU pending           840 HU
4 delayed ⚠️               Avg wait: 23 min           Oldest: 47 min ⚠️

Picking                    Packing                    Staging
Wave 105                   320 orders waiting         120 pallets
Progress: 87%              Avg time: 4.2 min          3 trucks loading

Shipping                   Resources                  Alerts
3 trucks loading           42 operators active        2 short picks
2 trucks waiting           8 on break                 1 dock full
Next cutoff: 18:00         3 forklifts idle           Wave 106 behind ⚠️
```

---

## Métricas Clave

### Por Área

| Área | Métricas |
|---|---|
| **Inbound** | Camiones esperando, camiones en dock, HUs pendientes de recepción |
| **Receiving** | HUs recibidas/hora, tiempo promedio de descarga |
| **Putaway** | HUs pendientes, antigüedad de la más vieja, throughput/hora |
| **Picking** | Progreso de wave activa, picks/hora, short picks |
| **Packing** | Pedidos esperando empaque, tiempo promedio, estaciones activas |
| **Staging** | Pallets en staging, organización por ruta/carrier |
| **Shipping** | Camiones cargando, camiones esperando, próximo cutoff |
| **Resources** | Operadores activos/break/idle, equipos disponibles |

### Alertas

El Control Tower genera alertas automáticas cuando:

| Condición | Alerta |
|---|---|
| Wave con progreso < 80% a 1h del cutoff | ⚠️ Wave behind schedule |
| Queue depth > umbral | ⚠️ Queue backlog |
| Work aging > 60 min | ⚠️ Stale work |
| Short picks > umbral | ⚠️ Inventory accuracy issue |
| Dock sin actividad > 30 min | ⚠️ Dock idle |

---

*Documento derivado de la sección 41 del [Plan Maestro](../plan.md).*
