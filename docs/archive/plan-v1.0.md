Sí. El problema del plan anterior es que era principalmente un **roadmap de implementación**. Antes de eso necesitamos una **arquitectura funcional y técnica maestra del producto WMS completo**. Recién cuando sepamos exactamente qué sistema queremos construir tiene sentido dividirlo en fases, módulos y horas.

La referencia correcta tampoco debería ser solamente “qué tiene Odoo”. Dynamics 365 estructura Warehouse Management alrededor de waves, work templates, work pools y location directives; SAP EWM estructura la ejecución alrededor de Warehouse Tasks, Warehouse Orders, queues, resources y RF. Esos patrones existen precisamente para desacoplar planificación, inventario y ejecución física. ([Microsoft Learn][1])

Además, confirmé algo importante para Community: `stock` y `stock_picking_batch` están efectivamente en el repositorio público Odoo 19.0 bajo LGPL; `stock_picking_batch` incluye batch y wave. En cambio, el módulo `stock_barcode` no está presente en esa ruta del repositorio Community, por lo que para nuestro diseño debemos asumir un **RF/WMS Mobile propio**, no depender de Enterprise. 

# Plan Maestro — WMS industrial sobre Odoo 19 Community

Propongo que construyamos el sistema en **cuatro niveles de definición**:

```text
NIVEL 0 — PRODUCTO
¿Qué WMS queremos construir?

        ↓

NIVEL 1 — ARQUITECTURA
¿Qué dominios y motores tendrá?

        ↓

NIVEL 2 — DISEÑO FUNCIONAL/TÉCNICO
¿Cómo funciona cada dominio?

        ↓

NIVEL 3 — IMPLEMENTACIÓN
Módulos Odoo, modelos, APIs, eventos,
tests, infraestructura y tareas.
```

El error sería saltar inmediatamente al nivel 3.

---

# 1. Objetivo del producto

El objetivo no sería:

> agregar características WMS a Odoo Inventory.

Sería:

> **Construir una plataforma WMS industrial sobre el framework Odoo 19 Community, capaz de coordinar inventario, recursos, operadores, equipos y flujos físicos de una o múltiples bodegas con alta concurrencia, trazabilidad completa y operación distribuida sobre Kubernetes on-premise.**

Odoo será:

* framework empresarial;
* ORM;
* modelo transaccional;
* seguridad;
* configuración;
* maestros;
* backoffice;
* motor de inventario base;
* extensibilidad modular.

Pero nuestro WMS agregará una nueva capa:

```text
                ODOO FRAMEWORK
                      │
              ┌───────▼───────┐
              │   WMS DOMAIN  │
              └───────┬───────┘
                      │
       ┌──────────────┼───────────────┐
       │              │               │
 Planning         Execution       Inventory
 Engines           Engines          Core
       │              │               │
       └──────────────┼───────────────┘
                      │
                 PostgreSQL
```

---

# 2. Los tres niveles lógicos del WMS

Esta separación será fundamental.

## Nivel A — Registro logístico

Representa **qué debe suceder**.

Ejemplos:

```text
Purchase Order
ASN
Inbound Order
Sales Order
Outbound Order
Transfer
Return
Shipment
```

Aquí Odoo tiene bastante infraestructura reutilizable.

---

## Nivel B — Planificación WMS

Determina **cómo debería ejecutarse**.

Por ejemplo:

```text
Pedido
  ↓
Allocation
  ↓
Wave
  ↓
Picking Strategy
  ↓
Location Strategy
  ↓
Work Generation
```

Aquí empezamos a construir nuestro WMS.

---

## Nivel C — Ejecución física

Representa **qué está haciendo el operador ahora**.

```text
Work
 ↓
Queue
 ↓
Operator
 ↓
Equipment
 ↓
RF
 ↓
Scan
 ↓
Pick
 ↓
Confirm
```

Aquí estará la mayor diferencia respecto de Odoo Inventory estándar.

SAP EWM sigue un patrón similar: Warehouse Tasks se agrupan en Warehouse Orders y posteriormente se asignan mediante queues/resources; en RF el sistema incluso puede seleccionar el Warehouse Order más apropiado para el recurso. ([SAP Help Portal][2])

---

# 3. Mapa completo del producto

Antes de pensar en fases, propongo definir estos **16 macrodominios**.

```text
01 Warehouse Master
02 Inventory
03 Handling Units
04 Work Execution
05 Resources
06 Rules
07 Inbound
08 Putaway
09 Internal Logistics
10 Allocation
11 Outbound Planning
12 Picking
13 Packing & Shipping
14 Inventory Control
15 Integration
16 Control Tower
```

Y alrededor de ellos:

```text
Security
Audit
Observability
Concurrency
Messaging
Kubernetes
Testing
Data Governance
Performance
High Availability
Disaster Recovery
```

---

# 4. Warehouse Master

### Propósito

Crear la representación digital de la bodega física.

### Qué hará

Representará:

```text
Company
 └ Warehouse
     ├ Building
     ├ Zone
     ├ Activity Area
     ├ Aisle
     ├ Rack
     ├ Level
     ├ Bin
     ├ Dock
     ├ Staging
     ├ Packing Station
     └ Quality Area
```

Odoo ya maneja warehouses y ubicaciones jerárquicas, por lo que debemos extender `stock.warehouse` y `stock.location`, no crear un modelo paralelo. ([Odoo][3])

### Cada ubicación tendrá capacidades

Por ejemplo:

```text
storage type
zone
capacity weight
capacity volume
maximum HU
temperature range
hazardous compatibility
allowed products
allowed HU types
pick sequence
travel sequence
replenishment profile
putaway profile
```

### Qué esperamos

Que cualquier algoritmo WMS pueda responder:

> ¿Qué puede guardarse aquí?

> ¿Puede llegar este equipo?

> ¿Qué operador trabaja aquí?

> ¿Qué tan lejos está esta ubicación?

> ¿Es picking, reserva, staging o recepción?

### Por qué hacerlo así

Porque los algoritmos de putaway, picking, slotting, replenishment y routing necesitan una representación operacional de la bodega, no solamente un nombre de ubicación.

---

# 5. Inventory Domain

Este será uno de los dominios más protegidos.

### Fuente de verdad

Continuaría siendo Odoo:

```text
stock.move
stock.move.line
stock.quant
```

No crearía una segunda base de inventario.

El módulo `stock` Community 19 ya contiene warehouses, moves, move lines, quants, lots, packages, storage categories, replenishment y trazabilidad. 

### El WMS agregará

```text
Inventory Status
Inventory Ownership
Reservation Context
HU Context
Quality Status
Operational Availability
Inventory Events
```

Ejemplo:

```text
SKU A
Warehouse SCL01
Location A03-R02-L04
Lot L00231
HU 780...
Owner COMPANY-A
Status AVAILABLE
Qty 120
```

---

# 6. Inventory Ledger

Además del stock actual tendremos trazabilidad operacional.

```text
wms.inventory.event
```

Ejemplo:

```text
12:04 RECEIVE
Supplier → RECEIVING

12:07 MOVE
RECEIVING → QUALITY

12:18 RELEASE
QUALITY → AVAILABLE

12:22 PUTAWAY
QUALITY → A03

16:42 PICK
A03 → CART-12

16:50 PACK
CART-12 → BOX-993

17:03 STAGE
BOX-993 → DOCK-04

17:20 LOAD
DOCK-04 → TRUCK-21
```

No pretende reemplazar `stock.move`.

Su propósito será:

* auditoría;
* troubleshooting;
* integración;
* analytics;
* reconstrucción operativa.

---

# 7. Handling Unit Engine

En un WMS industrial no se mueve solamente SKU.

Se mueven:

```text
Pallet
Case
Carton
Tote
Bin
Container
Parcel
```

Construiríamos sobre:

```text
stock.quant.package
```

pero agregando semántica de **Handling Unit (HU)**.

GS1 establece SSCC como identificación única de la unidad logística. ([GS1][4])

El modelo permitirá:

```text
PALLET
  │
  ├ BOX
  │ └ SKU-A x 24
  │
  ├ BOX
  │ └ SKU-A x 24
  │
  └ BOX
    ├ SKU-B x 10
    └ SKU-C x 6
```

Operaciones:

```text
Create
Pack
Unpack
Split
Merge
Nest
Unnest
Seal
Move
Relabel
Consume
Ship
```

---

# 8. Work Execution Engine

Este será probablemente **el componente más importante de toda la plataforma**.

Su propósito:

> transformar necesidades logísticas en unidades de trabajo ejecutables.

Ejemplo:

```text
Inbound Order
     ↓
Receipt
     ↓
Putaway Planning
     ↓
WORK 10592
```

Contenido:

```text
Work 10592

Priority 80

Line 10
PICK
RECEIVING-04
PALLET 10092

Line 20
PUT
A04-R02-L03
```

Modelos previstos:

```text
wms.work
wms.work.line
wms.work_type
wms.work_class
wms.work_template
wms.work_dependency
wms.work_exception
```

---

# 9. Queue Engine

Work y Queue son conceptos distintos.

```text
WORK
qué hacer

QUEUE
quién puede tomarlo
```

Ejemplo:

```text
QUEUE-PUTAWAY-FORKLIFT-A
```

podría aceptar solamente:

```text
Zone = A
Equipment = Forklift
Certification = HighRack
Weight <= 1200kg
```

SAP EWM asigna queues utilizando, entre otras variables, áreas de actividad de origen/destino y permite asociar recursos y grupos de recursos a queues. ([SAP Help Portal][5])

Nuestro Queue Engine tendrá:

```text
priority
activity area
resource profile
equipment requirement
work type
warehouse
zone
deadline
cutoff
```

---

# 10. Resource Engine

No modelaremos al operario simplemente como:

```text
res.users
```

Crearemos:

```text
wms.resource
```

que se relacionará con el usuario Odoo.

Podrá representar:

```text
Operator
Forklift
Reach Truck
Pallet Jack
Robot
AGV
AMR
Picking Station
```

Con capacidades:

```text
warehouse
zones
certifications
work classes
weight capability
equipment type
current position
current queue
availability
shift
```

Entonces:

```text
Get Next Work
```

podrá elegir trabajo compatible.

---

# 11. Assignment Engine

Cuando un trabajador pida:

```text
NEXT WORK
```

no recibirá simplemente el primer registro.

Evaluaremos:

```text
priority
deadline
queue
zone
distance
equipment
capability
current location
work aging
wave priority
route
```

conceptualmente:

```text
score =
 priority
 + urgency
 + proximity
 + affinity
 + queue priority
 - travel cost
```

Esto podrá evolucionar posteriormente hacia optimización matemática sin cambiar el modelo operacional.

---

# 12. Concurrencia

Esta arquitectura existe precisamente porque tendremos múltiples operadores.

Por ejemplo:

```text
250 RF devices

50 → Picking
35 → Putaway
20 → Replenishment
10 → Counts
40 → Packing
...
```

Las operaciones críticas tendrán locking explícito.

PostgreSQL documenta `FOR UPDATE` para proteger filas concurrentemente y `SKIP LOCKED` específicamente como mecanismo apropiado para múltiples consumidores de una estructura tipo queue. ([PostgreSQL][6])

Por ejemplo:

```sql
SELECT id
FROM wms_work
WHERE state = 'ready'
ORDER BY priority DESC
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

Esto permite:

```text
Operator A → Work 10
Operator B → Work 11
Operator C → Work 12
```

sin esperar unos por otros ni duplicar asignaciones.

---

# 13. Rule Engine

No quiero que nuestro WMS termine conteniendo cientos de:

```python
if warehouse == ...
if product.category == ...
```

Crearemos políticas configurables.

```text
wms.rule
wms.rule_condition
wms.rule_action
wms.rule_set
wms.rule_version
```

Aplicables a:

```text
Putaway
Allocation
Replenishment
Wave
Work
Queue
Picking
Packing
Quality
Shipping
```

Ejemplo:

```text
RULE PUTAWAY_FROZEN

IF
temperature_class = FROZEN

AND
HU_TYPE = PALLET

THEN
zone = FREEZER
```

Las reglas deberán ser:

```text
versionadas
auditables
testeables
simulables
publicables
```

---

# 14. Inbound

El dominio Inbound completo abarcará:

```text
ASN
Appointment
Gate
Dock Assignment
Arrival
Unload
Receiving
Verification
Discrepancies
Quality
HU
Putaway
Cross Dock
Closure
```

Flujo:

```text
ASN
 ↓
Expected Receipt
 ↓
Arrival
 ↓
Dock
 ↓
Unload
 ↓
Scan HU
 ↓
Receive
 ↓
Validation
 ↓
Quality?
 ├ YES → Quality
 └ NO
 ↓
Putaway planning
 ↓
Work
```

---

# 15. Dock & Yard

Lo incorporaría conceptualmente desde ahora, aunque se implemente después.

Entidades:

```text
Dock
Appointment
Vehicle
Trailer
Gate Visit
Yard Position
Loading Door
```

Porque inbound y outbound eventualmente necesitan saber:

> qué vehículo está esperando,

> qué dock está disponible,

> dónde debe estacionarse,

> qué carga corresponde.

No queremos rediseñar la arquitectura cuando llegue esa necesidad.

---

# 16. Quality Management

Se manejará mediante estados y flujo operacional.

```text
RECEIVED
    ↓
QUALITY
    ├ PASS → AVAILABLE
    ├ HOLD
    ├ QUARANTINE
    ├ DAMAGED
    └ REJECTED
```

Y generará Work cuando corresponda:

```text
MOVE TO QUARANTINE
MOVE TO DAMAGE
MOVE TO AVAILABLE
```

---

# 17. Putaway Engine

Su pregunta principal es:

> ¿Dónde debo almacenar esta HU/mercadería?

Considerará:

```text
warehouse
zone
storage type
product
category
ABC class
velocity
HU
weight
volume
temperature
hazardous
lot
owner
same SKU
same lot
available capacity
distance
consolidation
```

Dynamics utiliza Location Directives precisamente para determinar ubicaciones de PICK y PUT. ([Microsoft Learn][7])

Odoo 19 ya dispone de storage categories y capacidades básicas, por lo que aprovecharemos esa información y agregaremos nuestro motor de selección. ([Odoo][8])

---

# 18. Cross Dock Engine

Ejemplo:

```text
Inbound:
100 SKU-A

Outbound urgent:
80 SKU-A

                 ┌→ 80 Cross Dock → Outbound
Receiving → 100 ─┤
                 └→ 20 Putaway
```

Evita almacenar y volver a retirar innecesariamente.

Dynamics también contempla planned cross-docking dentro de su Warehouse Management. ([Microsoft Learn][9])

---

# 19. Replenishment Engine

Separaremos:

```text
Reserve Storage
        ↓
Pick Face
```

Estrategias:

```text
Min/Max
Demand Driven
Wave Driven
Top Off
Emergency
Empty Location
```

Ejemplo:

```text
Pick Face
current = 40
min = 100
max = 600

↓
REPLENISH 560
```

Dynamics modela replenishment templates como reglas para determinar cuándo y cómo reponer una ubicación. ([Microsoft Learn][10])

---

# 20. Slotting Engine

Putaway y slotting tampoco son lo mismo.

Putaway pregunta:

> ¿Dónde guardo esto ahora?

Slotting pregunta:

> ¿Dónde debería vivir normalmente este SKU?

Analizará:

```text
velocity
order affinity
size
weight
picks/day
seasonality
travel distance
replenishment frequency
```

Salida:

```text
SKU-A

Current:
A98

Recommended:
A03

Expected travel reduction:
23 %
```

Primero será analítico/recomendación.

Luego podrá generar Work.

---

# 21. Allocation Engine

Su pregunta será:

> Tengo una demanda de 200 unidades. ¿Qué inventario debo comprometer?

Considerará:

```text
availability
status
warehouse
owner
lot
expiry
FIFO
FEFO
LIFO
closest
full pallet
full box
least fragmentation
customer rules
route
```

Odoo 19 ya implementa estrategias como FIFO, LIFO, FEFO y closest location; nuestra capa debe extenderlas con la semántica WMS empresarial necesaria. ([Odoo][11])

---

# 22. Outbound Release Engine

No todos los pedidos deberían inmediatamente generar picking.

Existirá:

```text
Order
 ↓
Eligible
 ↓
Released
 ↓
Allocated
 ↓
Waved
 ↓
Work Generated
```

Esto permite controlar carga operativa.

---

# 23. Wave Engine

Será otro motor central.

Su propósito:

> organizar demanda outbound en unidades operativas coherentes.

Por ejemplo:

```text
WAVE 20260817-01

Cutoff 16:00
Carrier A
Zone 1/2
Orders 1,240
Lines 4,890
Units 18,200
```

Dynamics considera Wave Templates una de las piezas centrales de Warehouse Management; SAP utiliza waves para crear warehouse orders/tasks. ([Microsoft Learn][12])

---

# 24. Picking Engine

Debe soportar desde el diseño:

```text
Discrete
Batch
Wave
Cluster
Zone
Pick & Pass
Case
Piece
Full Pallet
Two-Step
Multi-Order
```

Odoo Community 19 dispone de `stock_picking_batch`; su manifest incluye además vistas de wave, por lo que podemos reutilizar parte del modelo estándar sin convertirlo en nuestro Work Engine. 

Eso es importante:

```text
stock.picking.batch
       ≠
wms.work
```

Uno agrupa operaciones logísticas.

El otro representa ejecución física.

---

# 25. Route Optimization

Picking necesitará secuenciar ubicaciones.

Inicial:

```text
location picking_sequence
```

Después:

```text
warehouse graph
       ↓
shortest path
```

Posteriormente:

```text
dynamic route optimization
```

Pero ya debemos guardar coordenadas/topología necesarias desde el modelo inicial.

---

# 26. Consolidation

Cuando distintos operadores preparen partes del mismo pedido:

```text
ZONE A ─┐
ZONE B ─┼→ CONSOLIDATION → ORDER
ZONE C ─┘
```

Necesitaremos:

```text
Consolidation Point
Order Container
Expected Contents
Received Contents
Exceptions
```

---

# 27. Packing Engine

Funciones:

```text
Packing Station
Cartonization
Container selection
Weight
Dimensions
SSCC
Package hierarchy
Label
Verification
Closing
```

Después podremos agregar algoritmos de **cartonization**.

---

# 28. Staging

Antes de loading:

```text
PACKED
 ↓
STAGING LANE
 ↓
ROUTE / TRUCK / DOCK
```

Debe conocer:

```text
route
carrier
vehicle
shipment
dock
sequence
```

---

# 29. Loading

RF dirigido:

```text
SCAN TRUCK
 ↓
SCAN DOCK
 ↓
SCAN SSCC
 ↓
Validate shipment
 ↓
LOAD
```

Debe impedir:

```text
wrong truck
wrong route
wrong shipment
duplicate HU
```

---

# 30. Shipping

El WMS cierra:

```text
shipment
inventory
HU lifecycle
work
manifest
integration
```

y genera eventos para:

```text
ERP
TMS
Carrier
Customer
BI
```

---

# 31. Reverse Logistics

También debe existir desde el diseño.

```text
Return Authorization
 ↓
Receive
 ↓
Inspection
 ↓
Disposition
```

Destino:

```text
Restock
Repair
Quarantine
Scrap
Return Supplier
```

---

# 32. Cycle Counting

Tipos:

```text
ABC
Scheduled
Zero Balance
Location
SKU
HU
Exception
High Value
```

Flujo:

```text
Count Work
 ↓
Blind Count
 ↓
Variance
 ↓
Recount?
 ↓
Approval?
 ↓
Adjustment
```

---

# 33. Labor Management

Tendremos datos reales de:

```text
work assigned
start
finish
travel
wait
exceptions
```

por lo que podremos calcular:

```text
Units/hour
Lines/hour
Picks/hour
Travel time
Idle time
Work utilization
Queue time
```

Esto no debe convertirse en vigilancia individual indiscriminada; operacionalmente servirá para capacidad, planificación y detección de cuellos de botella.

---

# 34. RF / WMS Mobile

Dado que queremos Community, diseñaría un cliente propio.

No usaría las vistas normales del backend.

Arquitectura:

```text
RF Device
   │
 HTTPS
   │
WMS API/RF
   │
Work Engine
   │
Odoo ORM
```

Pantallas extremadamente simples.

Ejemplo:

```text
PUTAWAY

FROM
REC-04

SCAN PALLET

[________________]
```

Luego:

```text
DESTINATION

A03-R02-L05

SCAN LOCATION

[________________]
```

Dynamics y SAP tienen interfaces mobile/RF explícitamente centradas en ejecución dirigida de trabajo. ([Microsoft Learn][13])

---

# 35. Exception Engine

Un WMS industrial no puede diseñarse solamente para el happy path.

Necesitamos:

```text
SHORT
DAMAGED
LOCATION FULL
SKU NOT FOUND
HU NOT FOUND
WRONG LOT
WRONG SERIAL
WRONG LOCATION
EQUIPMENT FAILURE
QUALITY HOLD
NETWORK ERROR
OVER RECEIPT
UNDER RECEIPT
```

Cada excepción debe definir:

```text
Who can raise?
What happens to Work?
What happens to stock?
Supervisor needed?
Alternative location?
Audit event?
```

---

# 36. Integration Platform

No permitiremos que otros sistemas accedan directamente al ORM.

Construiremos:

```text
/api/wms/v1
```

y contratos:

```text
InboundOrder
OutboundOrder
Inventory
Receipt
Shipment
HU
Status
Event
```

Internamente:

```text
Inbox
Outbox
Idempotency
Correlation ID
Retry
DLQ
Schema Version
```

---

# 37. Síncrono vs asíncrono

Regla principal:

### Síncrono

Lo que el operario necesita para continuar:

```text
Scan
Reserve
Pick
Put
Work assignment
HU validation
```

### Asíncrono

Lo que puede ocurrir posteriormente:

```text
ERP notification
TMS
Reporting
Emails
Analytics
Heavy waves
Optimization
Exports
```

---

# 38. Arquitectura de Kubernetes

Odoo soporta un servidor multiproceso para producción, pero para nuestro caso además segmentaremos responsabilidades operacionalmente. ([Odoo][14])

```text
                        LOAD BALANCER
                              │
                           INGRESS
                              │
       ┌──────────────────────┼─────────────────────┐
       │                      │                     │
       ▼                      ▼                     ▼
 ODOO BACKOFFICE          WMS RF/API          INTEGRATION API
 Deployment              Deployment             Deployment
       │                      │                     │
       └──────────────────────┼─────────────────────┘
                              │
                       PostgreSQL HA
                              │
               ┌──────────────┼───────────────┐
               │              │               │
             Redis        RabbitMQ        Object/File
                          / Broker          Storage
                              │
                      ┌───────┴────────┐
                      │                │
                 Async Workers    Integration
                                    Workers
```

Kubernetes permite HPA sobre workloads escalables, probes para health/readiness y PodDisruptionBudgets para limitar interrupciones voluntarias; serán componentes del baseline de producción, no mejoras posteriores. ([Kubernetes][15])

---

# 39. Separación de runtime

Misma aplicación, distintos workloads:

```text
odoo-backoffice
wms-rf
wms-api
wms-worker
wms-integration
wms-scheduler
```

No estoy proponiendo seis bases de código.

Estoy proponiendo:

```text
           WMS SOURCE
               │
        Container Image
               │
 ┌─────────────┼──────────────┐
 ↓             ↓              ↓
RF Pods    Worker Pods   Backoffice Pods
```

Esto permitirá que un peak de RF no compita directamente con reporting administrativo.

---

# 40. Observability

Dos niveles.

### Plataforma

```text
CPU
RAM
Pods
DB connections
queries
locks
deadlocks
RabbitMQ
latency
errors
```

### Negocio

```text
orders waiting
work ready
work aging
queue depth
picks/hour
putaway/hour
wave progress
dock utilization
inventory accuracy
short picks
replenishment backlog
```

---

# 41. Control Tower

Construiremos un verdadero monitor operacional.

Ejemplo:

```text
WAREHOUSE SCL01

Inbound
13 trucks
4 delayed

Receiving
2,430 HU pending

Putaway
840 HU
Oldest: 47 min

Picking
Wave 105
87%

Packing
320 orders waiting

Staging
120 pallets

Shipping
3 trucks loading
```

Será equivalente conceptualmente al monitor operacional que productos WMS de clase empresarial utilizan para supervisar ejecución.

---

# 42. Seguridad

Habrá separación entre:

```text
Administrator
Warehouse Manager
Supervisor
Planner
Operator
Inventory Controller
Quality
Integrator
Auditor
```

Y scopes:

```text
Company
Warehouse
Zone
Activity
```

No dependeremos únicamente de ocultar menús.

---

# 43. Auditoría

Cada acción crítica tendrá:

```text
operator
device
timestamp
warehouse
work
source
destination
before
after
correlation_id
```

Ejemplo:

```text
17:14:02
OPERATOR 129
RF 24
WORK 98933

PICK

SKU X
LOT L04

FROM A03
QTY 24
```

---

# 44. Disponibilidad

El sistema debe tolerar:

```text
pod crash
worker crash
retry
duplicate event
network interruption
node maintenance
```

sin provocar:

```text
duplicate pick
duplicate shipment
duplicate reservation
```

Esto implica idempotencia en todo command crítico.

---

# 45. Plan maestro de desarrollo revisado

Ahora sí las fases tienen sentido.

No las considero simplemente una secuencia de funcionalidades.

Las dividiría en **seis programas**.

---

## PROGRAMA A — Arquitectura y plataforma

### Fase 0 — Product Definition & WMS Blueprint

**Propósito**

Diseñar el WMS entero.

**Define**

* capacidades;
* procesos;
* dominios;
* actores;
* NFR;
* volúmenes;
* flujos;
* excepciones;
* integraciones;
* límites del producto.

**Resultado esperado**

Una especificación funcional completa del WMS.

**Por qué primero**

Porque todo lo posterior depende de estas decisiones.

---

## Fase 1 — Domain Architecture

Define:

```text
Bounded contexts
Entities
Aggregates
State Machines
Commands
Events
Ownership
Dependencies
```

Resultado:

```text
WMS Domain Model v1
```

---

## Fase 2 — Data Architecture

Definiremos:

```text
Odoo models reused
Odoo models extended
WMS models
Indexes
Constraints
Locks
History
Retention
Partitioning
```

Resultado:

```text
ER completo
Data Dictionary
Transaction boundaries
```

---

## Fase 3 — Platform Architecture

Construiremos:

```text
Kubernetes
PostgreSQL HA
RabbitMQ
Redis
Storage
Ingress
Monitoring
Logging
Secrets
Backups
CI/CD
```

---

## PROGRAMA B — WMS Foundation

### Fase 4 — Warehouse Master

Topología completa.

### Fase 5 — Inventory Core

Stock, availability, reservation, traceability.

### Fase 6 — Handling Units / GS1

Pallets, cajas, SSCC.

### Fase 7 — Work Engine

Work / Work Lines / templates.

### Fase 8 — Queue & Resource Engine

Operarios/equipos/colas/asignación.

### Fase 9 — Rule Engine

Configuración declarativa.

Estas seis fases producen el verdadero **kernel WMS**.

---

# PROGRAMA C — Inbound & Internal Logistics

### Fase 10 — RF Framework

Cliente operacional.

### Fase 11 — Inbound & Receiving

ASN → recepción.

### Fase 12 — Quality

Quality/Hold/Quarantine.

### Fase 13 — Putaway

Location determination.

### Fase 14 — Cross Dock

Inbound → outbound.

### Fase 15 — Internal Movements

Reubicaciones y movimientos.

### Fase 16 — Replenishment

Reserva → pick face.

### Fase 17 — Slotting

Optimización de almacenamiento.

---

# PROGRAMA D — Outbound

### Fase 18 — Outbound Orchestration

Órdenes y release.

### Fase 19 — Allocation

Selección de stock.

### Fase 20 — Wave Planning

Agrupación operacional.

### Fase 21 — Picking

Todos los modelos de picking.

### Fase 22 — Consolidation

Unificación de picks.

### Fase 23 — Packing

Empaque y cartonización.

### Fase 24 — Staging

Preparación de carga.

### Fase 25 — Loading

Carga dirigida por RF.

### Fase 26 — Shipping

Cierre de despacho.

---

# PROGRAMA E — Inventory & Enterprise Operations

### Fase 27 — Cycle Counting

Conteos.

### Fase 28 — Inventory Adjustments

Control de diferencias.

### Fase 29 — Returns

Reverse logistics.

### Fase 30 — Yard & Dock Management

Gate/dock/vehicle.

### Fase 31 — Labor Management

Productividad/capacidad.

### Fase 32 — Value Added Services

Por ejemplo:

```text
labeling
repacking
kitting
assembly
inspection
```

### Fase 33 — Production Supply

Si posteriormente alimentamos manufactura:

```text
warehouse
 ↓
production staging
 ↓
production
```

---

# PROGRAMA F — Plataforma empresarial

### Fase 34 — Integration Platform

ERP/TMS/OMS/carriers.

### Fase 35 — Control Tower

Monitor operacional.

### Fase 36 — Analytics & KPI

Productividad y capacidad.

### Fase 37 — Observability

Técnica y negocio.

### Fase 38 — Security Hardening

RBAC, secrets, network policy.

### Fase 39 — Performance Engineering

Carga y concurrencia.

### Fase 40 — High Availability

Fallos controlados.

### Fase 41 — Disaster Recovery

Backup/restore/failover.

### Fase 42 — Pilot

Una operación real.

### Fase 43 — Production Rollout

Rollout progresivo.

---

# PROGRAMA G — Optimización avanzada

Una vez estable la plataforma:

### Fase 44 — Dynamic Slotting

### Fase 45 — Route Optimization

### Fase 46 — Dynamic Waves

### Fase 47 — Labor Forecasting

### Fase 48 — Predictive Replenishment

### Fase 49 — Anomaly Detection

### Fase 50 — AI Optimization Layer

Pero ninguna IA tendrá autoridad directa para alterar inventario.

La estructura será:

```text
AI / Optimizer
      │
 recommendation
      ↓
WMS deterministic engine
      │
 validation
      ↓
transaction
```

---

# 46. Cómo detallaremos ahora cada fase

Aquí cambia definitivamente la metodología.

Cada fase tendrá una ficha estructurada:

```text
FASE
│
├── Propósito
│
├── Problema que resuelve
│
├── Alcance
│
├── Fuera de alcance
│
├── Actores
│
├── Casos de uso
│
├── Flujo funcional
│
├── Entidades
│
├── Estados
│
├── Reglas
│
├── Comandos
│
├── Eventos
│
├── Excepciones
│
├── Concurrencia
│
├── Seguridad
│
├── Auditoría
│
├── APIs
│
├── Procesamiento Async
│
├── Modelos Odoo reutilizados
│
├── Modelos Odoo extendidos
│
├── Modelos nuevos
│
├── Índices DB
│
├── Dependencias
│
├── Observabilidad
│
├── Pruebas unitarias
│
├── Pruebas integración
│
├── Pruebas concurrencia
│
├── Pruebas performance
│
├── Criterios aceptación
│
└── Definition of Done
```

Y recién **después**:

```text
Task ID
Task
Description
Min hours
Expected hours
Max hours
```

---

# 47. También tendremos decisiones arquitectónicas formales

Por ejemplo:

```text
ADR-001
stock.quant remains inventory source of truth

ADR-002
stock.picking is not Work

ADR-003
WMS Work is explicitly modeled

ADR-004
External integrations are asynchronous by default

ADR-005
RF has its own execution API

ADR-006
PostgreSQL owns transaction consistency

ADR-007
Redis cannot own inventory state

ADR-008
Queue assignment uses database locking

ADR-009
Rules are declarative and versioned

ADR-010
All externally received commands are idempotent
```

Esto evitará que durante dos años de desarrollo distintos programadores empiecen a solucionar el mismo problema de formas diferentes.

---

# 48. Lo que creo que debemos construir

El sistema final ya no lo describiría como:

> Odoo con módulos WMS.

Lo describiría como:

```text
                    WMS PLATFORM
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   Planning Layer   Execution Layer   Inventory Layer
        │                │                │
 Allocation          Work             Odoo Stock
 Waves               Queue            Quants
 Slotting            Resources        Moves
 Routing             RF               Lots
 Replenishment       Exceptions       Packages
        │                │                │
        └────────────────┼────────────────┘
                         │
                 Integration Layer
                         │
             ERP / OMS / TMS / WCS
                         │
                 Kubernetes Platform
```

Y esa arquitectura nos permite algo importante:

**Odoo deja de ser la limitación arquitectónica del WMS y pasa a ser el framework sobre el cual construimos el producto.**

Creo que ése es el cambio conceptual que necesitábamos.

---

## Próximo paso de la planificación

Ya no seguiría agregando funcionalidades arbitrariamente. El siguiente trabajo debería ser construir el **“WMS Master Blueprint v1.0”** comenzando por las Fases **0, 1, 2 y 3**, pero describiendo primero el **modelo completo de dominios y sus interacciones**.

La primera pieza que desarrollaría con mucho detalle sería:

```text
WMS MASTER DOMAIN MODEL
```

con aproximadamente:

```text
Warehouse
Location
Zone
Activity Area
Resource
Equipment
SKU
Lot
Serial
Handling Unit
Inventory
Inventory Status
Reservation
Inbound Order
Receipt
Quality
Work
Work Line
Queue
Rule
Putaway
Replenishment
Outbound Order
Allocation
Wave
Pick
Pack
Shipment
Dock
Vehicle
Cycle Count
Exception
Integration Event
Audit Event
```

y las relaciones entre todos ellos.

Ese **Domain Model maestro debe existir antes de tocar código**, porque va a determinar prácticamente toda la arquitectura posterior. A partir de ahí podemos tomar **Fase 0 — Product Definition & WMS Blueprint** y llevarla al nivel de detalle extremo que estás buscando: propósito → funcionamiento → decisiones → entidades → workflows → excepciones → NFR → pruebas → criterios de aceptación → tareas y horas.

[1]: https://learn.microsoft.com/en-us/dynamics365/supply-chain/warehousing/warehouse-management-overview?utm_source=chatgpt.com "Warehouse management overview - Dynamics 365"
[2]: https://help.sap.com/docs/SAP_SUPPLY_CHAIN_MANAGEMENT/dc8e3ce481cc493aad2145b99e6c53eb/3d267d0c-463f-4bf5-b2b9-a72eac15dccc.html?utm_source=chatgpt.com "Warehouse Order"
[3]: https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/inventory_management/warehouses.html?utm_source=chatgpt.com "Warehouses — Odoo 19.0 documentation"
[4]: https://www.gs1.org/standards/gs1-logistic-label-guideline/current-standard?utm_source=chatgpt.com "GS1 Logistic Label Guideline"
[5]: https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/9832125c23154a179bfa1784cdc9577a/6ccdcb53ad377114e10000000a174cb4.html?utm_source=chatgpt.com "Queue | SAP Help Portal"
[6]: https://www.postgresql.org/docs/current/sql-select.html?utm_source=chatgpt.com "PostgreSQL: Documentation: 18: SELECT"
[7]: https://learn.microsoft.com/en-us/dynamics365/supply-chain/warehousing/create-location-directive?utm_source=chatgpt.com "Work with location directives - Dynamics 365"
[8]: https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/shipping_receiving/daily_operations/storage_category.html?utm_source=chatgpt.com "Storage categories — Odoo 19.0 documentation"
[9]: https://learn.microsoft.com/en-us/dynamics365/supply-chain/warehousing/planned-cross-docking?utm_source=chatgpt.com "Planned cross docking - Dynamics 365"
[10]: https://learn.microsoft.com/en-us/dynamics365/supply-chain/warehousing/replenishment-over-location-capacity?utm_source=chatgpt.com "Replenishment over location capacity - Supply Chain ..."
[11]: https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/shipping_receiving/removal_strategies.html?utm_source=chatgpt.com "Removal strategies — Odoo 19.0 documentation"
[12]: https://learn.microsoft.com/en-us/dynamics365/supply-chain/warehousing/warehouse-configuration?utm_source=chatgpt.com "Warehouse configuration overview - Dynamics 365"
[13]: https://learn.microsoft.com/en-us/dynamics365/supply-chain/warehousing/configure-mobile-devices-warehouse?utm_source=chatgpt.com "Set up mobile devices for warehouse work"
[14]: https://www.odoo.com/documentation/19.0/administration/on_premise/deploy.html?utm_source=chatgpt.com "System configuration — Odoo 19.0 documentation"
[15]: https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/?utm_source=chatgpt.com "Horizontal Pod Autoscaling"
