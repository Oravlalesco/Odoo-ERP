# Kubernetes — Arquitectura de Despliegue, Separación de Runtime y Escalabilidad

> Arquitectura de despliegue sobre Kubernetes on-premise que separa workloads por responsabilidad, permite escalar independientemente cada capa y asegura que un pico de RF no compita con reporting administrativo.

---

## Contexto

### ¿Por qué Kubernetes?

Un almacén con 250 operadores RF generando transacciones cada 3-5 segundos necesita una infraestructura que:

- **Escale** horizontalmente cuando la carga aumenta
- **Aísle** workloads para que un proceso no degrade a otro
- **Se recupere** automáticamente de fallos de pods o nodos
- **Permita** actualizaciones sin detener la operación

**Kubernetes** (K8s) es un **orquestador de contenedores**: gestiona el ciclo de vida de aplicaciones empaquetadas en contenedores Docker, distribuyéndolas en un cluster de servidores.

---

## Arquitectura de Despliegue

```text
                        LOAD BALANCER
                        (Balanceador de carga: distribuye tráfico entrante)
                              │
                           INGRESS
                           (Punto de entrada K8s: routea URLs a servicios)
                              │
       ┌──────────────────────┼─────────────────────┐
       │                      │                     │
       ▼                      ▼                     ▼
 ODOO BACKOFFICE          WMS RF/API          INTEGRATION API
 Deployment              Deployment             Deployment
 (Interfaz admin)        (Operadores RF)       (Sistemas externos)
       │                      │                     │
       └──────────────────────┼─────────────────────┘
                              │
                       PostgreSQL HA
                       (Base de datos en alta disponibilidad)
                              │
               ┌──────────────┼───────────────┐
               │              │               │
             Redis        RabbitMQ        Object/File
             (Cache)      (Message Broker)  Storage
                          (Broker de msj)   (Almacenamiento)
                              │
                      ┌───────┴────────┐
                      │                │
                 Async Workers    Integration
                 (Proc. async)     Workers
                                  (Proc. integración)
```

### Glosario de Componentes de Infraestructura

| Componente | En inglés | Significado |
|---|---|---|
| **Load Balancer** | Balanceador de Carga | Distribuye el tráfico de red entrante entre múltiples servidores para no sobrecargar ninguno |
| **Ingress** | Ingress | Componente de K8s que routea peticiones HTTP/HTTPS a los servicios internos según la URL |
| **Deployment** | Deployment | Definición de K8s que describe cuántas réplicas de un servicio deben estar corriendo |
| **Pod** | Pod | Unidad mínima de ejecución en K8s: uno o más contenedores corriendo juntos |
| **PostgreSQL HA** | PostgreSQL Alta Disponibilidad | Base de datos con réplicas para tolerancia a fallos |
| **Redis** | Redis | Base de datos en memoria usada para cache (datos de acceso rápido y temporal) |
| **RabbitMQ** | RabbitMQ | Message Broker: intermediario que recibe y entrega mensajes entre servicios de forma confiable |
| **Object Storage** | Almacenamiento de Objetos | Almacenamiento de archivos grandes (documentos, etiquetas, imágenes) |
| **Async Workers** | Workers Asíncronos | Procesos que ejecutan tareas en background (waves, reportes, exports) |
| **Integration Workers** | Workers de Integración | Procesos que manejan comunicación con sistemas externos |

---

## Separación de Runtime

### El Concepto

No estamos proponiendo seis bases de código diferentes. Es **una sola aplicación WMS** empaquetada en **una sola imagen Docker**, pero desplegada como múltiples workloads con distintas responsabilidades:

```text
           WMS SOURCE CODE (código fuente único)
                │
         Container Image (imagen Docker única)
                │
 ┌─────────────┼──────────────┐
 ↓             ↓              ↓
RF Pods    Worker Pods   Backoffice Pods
```

### Workloads Definidos

| Workload | Responsabilidad | Escalabilidad | SLA Response Time |
|---|---|---|---|
| `odoo-backoffice` | Interfaz administrativa web | 2-4 pods | < 2s |
| `wms-rf` | API para dispositivos RF de operadores | 4-16 pods (HPA) | < 200ms |
| `wms-api` | API REST para integraciones externas | 2-8 pods | < 500ms |
| `wms-worker` | Procesamiento asíncrono (waves, reports) | 2-8 pods | N/A (batch) |
| `wms-integration` | Procesamiento de mensajes de/hacia sistemas externos | 2-4 pods | N/A (async) |
| `wms-scheduler` | Tareas programadas (replenishment, conteos) | 1 pod | N/A (cron) |

### ¿Por qué separar?

| Problema sin separación | Solución con separación |
|---|---|
| Un reporte pesado de un gerente consume CPU y los RF se ponen lentos | Backoffice y RF corren en pods separados con recursos independientes |
| Un pico de waves satura el servidor y los operadores no pueden trabajar | Workers de waves tienen sus propios pods, no compiten con RF |
| Una integración externa genera carga excesiva | Integration API tiene su propio deployment con rate limiting |
| Una actualización del backend tumba los RF | Se puede actualizar backoffice sin tocar RF (rolling update) |

---

## Escalabilidad Horizontal

### HPA — Horizontal Pod Autoscaler

**HPA (Horizontal Pod Autoscaler)** — Escalador Horizontal Automático de Pods — es un componente de Kubernetes que automáticamente aumenta o disminuye el número de pods de un servicio según la carga.

```text
Tráfico RF normal:    4 pods wms-rf
Peak picking hora:    12 pods wms-rf  (HPA escala automáticamente)
Noche baja actividad: 2 pods wms-rf  (HPA reduce automáticamente)
```

### Métricas de Escalado

| Workload | Métrica de escalado | Threshold |
|---|---|---|
| `wms-rf` | CPU utilization + request latency | CPU > 70% o p95 > 150ms |
| `wms-api` | CPU utilization | CPU > 70% |
| `wms-worker` | Queue depth (profundidad de cola) | > 100 messages |
| `wms-integration` | Queue depth | > 50 messages |

### Probes — Sondas de Salud

Kubernetes usa **probes** (sondas) para determinar si un pod está saludable:

| Probe | En inglés | Significado |
|---|---|---|
| **Liveness Probe** | Sonda de Vida | ¿El proceso está vivo? Si falla, K8s reinicia el pod |
| **Readiness Probe** | Sonda de Preparación | ¿El pod está listo para recibir tráfico? Si falla, K8s deja de enviarle requests |
| **Startup Probe** | Sonda de Arranque | ¿El pod terminó de inicializarse? Para evitar que liveness lo mate durante startup |

### PDB — Pod Disruption Budget

**PDB (Pod Disruption Budget)** — Presupuesto de Interrupción de Pods — limita cuántos pods de un servicio pueden estar fuera de servicio simultáneamente durante mantenimientos programados.

```text
wms-rf PDB:
  minAvailable: 3              ← Siempre deben haber mínimo 3 pods RF activos
  
Resultado:
  K8s no puede drenar más de (N-3) pods RF a la vez durante un mantenimiento
```

---

## Componentes del Baseline de Producción

Estos no son "mejoras posteriores" — son parte del diseño base:

| Componente | En inglés | Propósito |
|---|---|---|
| **HPA** | Horizontal Pod Autoscaler | Escalar pods según carga |
| **Probes** | Health/Readiness Probes | Detectar y reemplazar pods no saludables |
| **PDB** | Pod Disruption Budget | Proteger disponibilidad durante mantenimientos |
| **Resource Limits** | Límites de Recursos | CPU y RAM máximos por pod |
| **Network Policy** | Política de Red | Aislar comunicación entre servicios |
| **Rolling Updates** | Actualizaciones Progresivas | Desplegar nuevas versiones sin downtime |

---

## Stack de Infraestructura Completo

| Capa | Tecnología | Propósito |
|---|---|---|
| **Orquestación** | Kubernetes (on-premise) | Gestión de contenedores |
| **Base de datos** | PostgreSQL HA (Patroni/Citus) | Persistencia y transacciones |
| **Cache** | Redis | Sesiones, datos volátiles, rate limiting |
| **Mensajería** | RabbitMQ | Comunicación asíncrona entre servicios |
| **Almacenamiento** | MinIO / NFS | Archivos, etiquetas, documentos |
| **Monitoring** | Prometheus + Grafana | Métricas y dashboards |
| **Logging** | Loki / ELK | Logs centralizados |
| **Secrets** | Vault / K8s Secrets | Gestión segura de credenciales |
| **CI/CD** | GitLab CI / ArgoCD | Integración y despliegue continuo |
| **Ingress** | Nginx Ingress Controller | Routing de tráfico HTTP |

---

## Referencias

- [Kubernetes — Horizontal Pod Autoscaling](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/)
- [Odoo 19 — System Configuration (multiprocess)](https://www.odoo.com/documentation/19.0/administration/on_premise/deploy.html)

---

*Documento derivado de las secciones 38-39 del [Plan Maestro](../plan.md).*
