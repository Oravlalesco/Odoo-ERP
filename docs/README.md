# Plan Maestro — WMS Industrial sobre Odoo 19 Community

> Índice maestro de la documentación técnica y funcional del sistema WMS.

Este repositorio documenta el diseño completo de una **plataforma WMS (Warehouse Management System / Sistema de Gestión de Almacén) industrial** construida sobre el framework Odoo 19 Community. El documento original de visión se encuentra en [plan.md](plan.md).

---

## 📋 Estructura de la Documentación

### 🎯 Visión del Producto

| # | Documento | Descripción |
|---|-----------|-------------|
| 1 | [Objetivo del Producto](00-vision/01-objetivo-producto.md) | Qué sistema construimos, por qué Odoo como framework y diferenciación frente a Odoo Inventory estándar |
| 2 | [Niveles Lógicos y Mapa del Producto](00-vision/02-niveles-logicos.md) | Los tres niveles lógicos (Registro, Planificación, Ejecución) y los 16 macrodominios |

---

### 🏗️ Dominios del WMS

| # | Documento | Dominio | Secciones del Plan |
|---|-----------|---------|-------------------|
| 1 | [Warehouse Master](01-dominios/01-warehouse-master.md) | Topología y representación digital de la bodega | §4 |
| 2 | [Inventory](01-dominios/02-inventory.md) | Dominio de inventario y Ledger de eventos | §5-6 |
| 3 | [Handling Units](01-dominios/03-handling-units.md) | Unidades de manejo: pallets, cajas, SSCC | §7 |
| 4 | [Work Execution](01-dominios/04-work-execution.md) | Motor de trabajo y motor de colas | §8-9 |
| 5 | [Resources](01-dominios/05-resources.md) | Recursos, operadores, equipos y asignación | §10-11 |
| 6 | [Rule Engine](01-dominios/06-rule-engine.md) | Motor de reglas configurables | §13 |
| 7 | [Inbound](01-dominios/07-inbound.md) | Recepción, Dock/Yard y Calidad | §14-16 |
| 8 | [Putaway](01-dominios/08-putaway.md) | Almacenamiento dirigido y Cross Dock | §17-18 |
| 9 | [Internal Logistics](01-dominios/09-internal-logistics.md) | Replenishment y Slotting | §19-20 |
| 10 | [Outbound](01-dominios/10-outbound.md) | Allocation, Waves, Picking, Consolidation | §21-26 |
| 11 | [Packing & Shipping](01-dominios/11-packing-shipping.md) | Empaque, Staging, Loading y Despacho | §27-30 |
| 12 | [Reverse Logistics](01-dominios/12-reverse-logistics.md) | Devoluciones y logística inversa | §31 |
| 13 | [Inventory Control](01-dominios/13-inventory-control.md) | Conteo cíclico y control de inventario | §32 |
| 14 | [Labor Management](01-dominios/14-labor-management.md) | Gestión de productividad y mano de obra | §33 |

---

### ⚙️ Operaciones

| # | Documento | Descripción | Secciones del Plan |
|---|-----------|-------------|-------------------|
| 1 | [RF / WMS Mobile](02-operaciones/01-rf-mobile.md) | Cliente móvil para operadores RF | §34 |
| 2 | [Exception Engine](02-operaciones/02-exception-engine.md) | Motor de excepciones operacionales | §35 |
| 3 | [Control Tower](02-operaciones/03-control-tower.md) | Monitor operacional en tiempo real | §41 |

---

### 🖥️ Plataforma Técnica

| # | Documento | Descripción | Secciones del Plan |
|---|-----------|-------------|-------------------|
| 1 | [Integración](03-plataforma/01-integracion.md) | API, contratos, síncrono vs asíncrono | §36-37 |
| 2 | [Kubernetes](03-plataforma/02-kubernetes.md) | Arquitectura K8s, separación de runtime, escalabilidad | §38-39 |
| 3 | [Observability](03-plataforma/03-observability.md) | Monitoreo de plataforma y negocio | §40 |
| 4 | [Seguridad](03-plataforma/04-seguridad.md) | RBAC, roles y scopes | §42 |
| 5 | [Auditoría](03-plataforma/05-auditoria.md) | Trazabilidad de acciones críticas | §43 |
| 6 | [Disponibilidad](03-plataforma/06-disponibilidad.md) | Tolerancia a fallos e idempotencia | §44 |

---

### 🗺️ Roadmap

| # | Documento | Programa | Fases |
|---|-----------|----------|-------|
| 1 | [Programa A](04-roadmap/01-programa-a.md) | Arquitectura y Plataforma | 0–3 |
| 2 | [Programa B](04-roadmap/02-programa-b.md) | WMS Foundation (Kernel) | 4–9 |
| 3 | [Programa C](04-roadmap/03-programa-c.md) | Inbound & Internal Logistics | 10–17 |
| 4 | [Programa D](04-roadmap/04-programa-d.md) | Outbound | 18–26 |
| 5 | [Programa E](04-roadmap/05-programa-e.md) | Inventory & Enterprise Operations | 27–33 |
| 6 | [Programa F](04-roadmap/06-programa-f.md) | Plataforma Empresarial | 34–43 |
| 7 | [Programa G](04-roadmap/07-programa-g.md) | Optimización Avanzada (AI/ML) | 44–50 |

---

### 📐 Decisiones y Templates

| # | Documento | Descripción | Secciones del Plan |
|---|-----------|-------------|-------------------|
| 1 | [ADR — Architecture Decision Records](05-decisiones/01-adr.md) | Decisiones arquitectónicas formales | §47 |
| 2 | [Ficha de Fase — Template](05-decisiones/02-ficha-fase-template.md) | Template para detallar cada fase | §46 |

---

## 🔗 Documento Original

El plan maestro completo, sin modificar, se encuentra en [plan.md](plan.md).
