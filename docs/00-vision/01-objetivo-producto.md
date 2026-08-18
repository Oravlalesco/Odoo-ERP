# Objetivo del Producto

> Construir una plataforma WMS industrial sobre el framework Odoo 19 Community, capaz de coordinar inventario, recursos, operadores, equipos y flujos físicos de una o múltiples bodegas con alta concurrencia, trazabilidad completa y operación distribuida sobre Kubernetes on-premise.

---

## Contexto

### ¿Qué es un WMS?

Un **WMS (Warehouse Management System)** — en español, **Sistema de Gestión de Almacén** — es una plataforma de software que controla y optimiza todas las operaciones dentro de un almacén o bodega: desde la recepción de mercadería hasta su despacho, incluyendo almacenamiento, preparación de pedidos, empaque y gestión de inventario.

### ¿Por qué construir uno propio?

Los WMS industriales de referencia — como los que ofrecen **SAP EWM (Extended Warehouse Management)** y **Microsoft Dynamics 365 Warehouse Management** — están diseñados para operaciones de alta complejidad y concurrencia. Sin embargo, vienen atados a ecosistemas propietarios con costos de licenciamiento significativos.

Odoo, por su parte, ofrece un módulo `stock` (inventario) que es funcional pero pensado para operaciones simples. No cuenta con:

- Motor de trabajo dirigido (*directed work*)
- Colas de ejecución para operadores
- Gestión de recursos y equipos
- Estrategias de olas (*waves*) y asignación avanzada
- Interface RF (*Radio Frequency*) para operadores de piso

**Nuestro proyecto no busca "agregar características WMS a Odoo Inventory", sino construir una plataforma WMS completa usando Odoo como framework base.**

---

## Definición del Producto

### Lo que NO es

> Agregar características WMS a Odoo Inventory.

### Lo que SÍ es

> Una plataforma WMS industrial sobre el framework Odoo 19 Community, capaz de coordinar inventario, recursos, operadores, equipos y flujos físicos de una o múltiples bodegas con alta concurrencia, trazabilidad completa y operación distribuida sobre Kubernetes on-premise.

---

## ¿Qué aporta Odoo como framework?

Odoo no será "el WMS". Odoo será la **base tecnológica** sobre la cual construimos el producto:

| Capacidad de Odoo | Qué nos aporta |
|---|---|
| **Framework empresarial** | Estructura de aplicación, módulos, vistas, menús |
| **ORM (Object-Relational Mapping)** | Capa de abstracción que traduce modelos Python a tablas PostgreSQL |
| **Modelo transaccional** | Gestión de transacciones de base de datos |
| **Seguridad** | Sistema de usuarios, grupos, permisos y record rules |
| **Configuración** | Parámetros de sistema, settings, configuraciones por compañía |
| **Maestros** | Datos maestros: productos, partners, unidades de medida, categorías |
| **Backoffice** | Interfaz administrativa web completa |
| **Motor de inventario base** | `stock.move`, `stock.quant`, `stock.picking` — estructura transaccional de inventario |
| **Extensibilidad modular** | Capacidad de agregar módulos que extienden la funcionalidad sin modificar el código fuente |

### Confirmación técnica: Community vs Enterprise

Se ha confirmado que los siguientes módulos están disponibles en **Odoo 19 Community** (licencia LGPL):

| Módulo | Disponible en Community | Qué incluye |
|---|---|---|
| `stock` | ✅ Sí | Warehouses, moves, move lines, quants, lots, packages, storage categories, replenishment, trazabilidad |
| `stock_picking_batch` | ✅ Sí | Batch picking y wave picking |
| `stock_barcode` | ❌ No (Enterprise) | Interface de escaneo con código de barras |

**Consecuencia clave**: debemos diseñar y construir nuestro propio **cliente RF/Mobile** para la operación de piso, no depender de `stock_barcode` de Enterprise.

---

## La capa que el WMS agrega

Sobre Odoo construiremos una capa completa de gestión de almacén industrial:

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

### Glosario de capas

| Capa | En inglés | Significado |
|---|---|---|
| **Planning Engines** | Motores de Planificación | Algoritmos que deciden *qué hacer* y *cómo hacerlo*: allocation (asignación de stock), waves (agrupación de pedidos), putaway (almacenamiento dirigido), replenishment (reposición), slotting (ubicación óptima de SKUs) |
| **Execution Engines** | Motores de Ejecución | Componentes que gestionan *quién lo hace* y *cuándo*: work (trabajo), queues (colas), resources (recursos), assignment (asignación), RF (terminales de radiofrecuencia) |
| **Inventory Core** | Núcleo de Inventario | La fuente de verdad del inventario, basada en los modelos de Odoo (`stock.quant`, `stock.move`) con extensiones WMS |

---

## Diferenciación frente a WMS de referencia

### SAP EWM (Extended Warehouse Management)

SAP EWM estructura la ejecución alrededor de:

- **Warehouse Tasks** (Tareas de Almacén): unidad mínima de trabajo dirigido
- **Warehouse Orders** (Órdenes de Almacén): agrupación de tasks para un recurso
- **Queues** (Colas): mecanismo de distribución de trabajo
- **Resources** (Recursos): operadores y equipos que ejecutan trabajo

Nuestro WMS adopta estos mismos patrones porque desacoplan correctamente *planificación*, *inventario* y *ejecución física*.

### Microsoft Dynamics 365 Warehouse Management

Dynamics estructura su WMS alrededor de:

- **Waves** (Olas): agrupación de demanda para procesamiento
- **Work Templates** (Plantillas de Trabajo): definiciones de qué trabajo generar
- **Work Pools** (Pools de Trabajo): clasificación de trabajo
- **Location Directives** (Directivas de Ubicación): reglas para determinar ubicaciones de pick y put

Estos conceptos también los adoptamos en nuestro diseño.

### Nuestro WMS

Tomamos lo mejor de ambas referencias y lo construimos sobre un framework de código abierto:

| Concepto | SAP EWM | Dynamics 365 | Nuestro WMS |
|---|---|---|---|
| Unidad de trabajo | Warehouse Task | Work | `wms.work` + `wms.work.line` |
| Agrupación de trabajo | Warehouse Order | Work Pool | `wms.work_class` |
| Distribución | Queue + Resource | Work Template | Queue Engine + Resource Engine |
| Planificación | Wave | Wave Template | Wave Engine |
| Ubicaciones | Storage Bin + Type | Location Directive | Location extendido + Rule Engine |
| Framework base | SAP NetWeaver | .NET + Azure | Odoo 19 Community + PostgreSQL |

---

## Visión de la Arquitectura Final

El sistema final no se describe como "Odoo con módulos WMS", sino como:

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

### Glosario de componentes finales

| Componente | Significado |
|---|---|
| **Allocation** | Motor que decide qué inventario comprometer para cumplir una demanda |
| **Waves** | Motor que agrupa pedidos en unidades operativas coherentes |
| **Slotting** | Motor que determina la ubicación óptima permanente de cada SKU |
| **Routing** | Motor de secuenciación y optimización de rutas dentro del almacén |
| **Replenishment** | Motor que repone las ubicaciones de picking desde reserva |
| **Work** | Motor que transforma necesidades logísticas en unidades de trabajo ejecutables |
| **Queue** | Motor que organiza trabajo en colas para distribución a recursos |
| **Resources** | Representación de operadores, equipos y su disponibilidad |
| **RF** | Interface de radiofrecuencia para operadores de piso |
| **Exceptions** | Motor que maneja situaciones fuera del flujo normal |
| **ERP** | Enterprise Resource Planning — sistema de gestión empresarial |
| **OMS** | Order Management System — sistema de gestión de pedidos |
| **TMS** | Transportation Management System — sistema de gestión de transporte |
| **WCS** | Warehouse Control System — sistema de control de equipos automatizados |

---

## Principio Arquitectónico Clave

> **Odoo deja de ser la limitación arquitectónica del WMS y pasa a ser el framework sobre el cual construimos el producto.**

Esto significa que:

1. No estamos limitados por lo que Odoo Inventory "puede hacer"
2. Podemos modelar entidades, flujos y motores que Odoo no contempla
3. Mantenemos la compatibilidad con el ecosistema Odoo (módulos, ERP, contabilidad)
4. Aprovechamos la infraestructura existente (ORM, seguridad, vistas, API) sin reinventarla

---

## Referencias

- [Dynamics 365 Warehouse Management Overview](https://learn.microsoft.com/en-us/dynamics365/supply-chain/warehousing/warehouse-management-overview)
- [SAP EWM — Warehouse Order](https://help.sap.com/docs/SAP_SUPPLY_CHAIN_MANAGEMENT/dc8e3ce481cc493aad2145b99e6c53eb/3d267d0c-463f-4bf5-b2b9-a72eac15dccc.html)
- [Odoo 19 — Warehouses Documentation](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/inventory_management/warehouses.html)

---

*Documento derivado de las secciones 1-3 del [Plan Maestro](../plan.md).*
