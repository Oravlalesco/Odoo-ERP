# Programa A — Arquitectura y Plataforma (Fases 0–3)

> Las primeras cuatro fases no producen funcionalidad operacional. Producen la **base** sobre la cual todo lo demás se construirá.

---

## Fase 0 — Product Definition & WMS Blueprint

### Propósito
Diseñar el WMS completo antes de tocar código.

### Define
- Capacidades del producto
- Procesos operacionales
- Dominios funcionales
- Actores del sistema
- NFR (*Non-Functional Requirements* / Requisitos No Funcionales): performance, disponibilidad, escalabilidad
- Volúmenes esperados
- Flujos completos
- Excepciones posibles
- Integraciones requeridas
- Límites del producto (qué NO hace)

### Resultado Esperado
Una **especificación funcional completa** del WMS.

### Por qué primero
Porque todo lo posterior depende de estas decisiones. Sin este documento, cada programador tomará decisiones arquitectónicas diferentes.

---

## Fase 1 — Domain Architecture

### Define

| Artefacto | En inglés | Significado |
|---|---|---|
| **Contextos acotados** | Bounded Contexts | Límites claros entre dominios (ej: Inventory vs. Work vs. Queue) |
| **Entidades** | Entities | Objetos del dominio con identidad (ej: Work, Resource, HU) |
| **Agregados** | Aggregates | Grupos de entidades que se modifican juntas transaccionalmente |
| **Máquinas de estado** | State Machines | Ciclos de vida de cada entidad (ej: Work: draft → ready → assigned → completed) |
| **Comandos** | Commands | Acciones que cambian estado (ej: AssignWork, ConfirmPick) |
| **Eventos** | Events | Hechos que ocurrieron (ej: WorkCompleted, InventoryMoved) |
| **Propiedad** | Ownership | Qué dominio es dueño de cada entidad |
| **Dependencias** | Dependencies | Qué dominio necesita a cuáles otros |

### Resultado
```text
WMS Domain Model v1
```

---

## Fase 2 — Data Architecture

### Define

| Artefacto | Significado |
|---|---|
| Modelos Odoo reutilizados | Qué modelos existentes usamos tal cual |
| Modelos Odoo extendidos | Qué modelos existentes modificamos |
| Modelos WMS nuevos | Qué modelos creamos de cero |
| Índices | Índices de base de datos para queries críticas |
| Constraints | Restricciones de integridad de datos |
| Locks | Estrategia de bloqueo para concurrencia |
| Historial | Qué datos se historizarán |
| Retención | Cuánto tiempo se mantienen los datos |
| Particionamiento | Cómo dividir tablas grandes |

### Resultado
```text
ER completo (diagrama entidad-relación)
Data Dictionary (diccionario de datos)
Transaction boundaries (límites transaccionales)
```

---

## Fase 3 — Platform Architecture

### Construye

| Componente | Propósito |
|---|---|
| Kubernetes | Cluster base con namespaces y network policies |
| PostgreSQL HA | Base de datos con réplicas |
| RabbitMQ | Message broker para async |
| Redis | Cache |
| Storage | Almacenamiento de archivos |
| Ingress | Routing de tráfico |
| Monitoring | Prometheus + Grafana |
| Logging | Logs centralizados |
| Secrets | Gestión de credenciales |
| Backups | Backup automatizado de DB y files |
| CI/CD | Pipeline de integración y despliegue continuo |

---

*Documento derivado de las Fases 0-3 del [Plan Maestro](../plan.md).*
