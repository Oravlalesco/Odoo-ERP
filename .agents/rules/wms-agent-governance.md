---
description: Gobernanza obligatoria para planificación, implementación y auditoría multiagente del WMS.
---

# WMS Multi-Agent Governance

Estas reglas gobiernan cualquier trabajo coordinado por agentes sobre el WMS.

## Authority

La autoridad se resuelve en este orden:

1. `docs/05-decisiones/01-adr.md`;
2. `docs/03-plataforma/`;
3. `docs/01-dominios/`;
4. `docs/04-roadmap/`;
5. README del módulo;
6. source/tests existentes;
7. capacidad de Odoo fijada por el proyecto;
8. skills auxiliares;
9. contrato de tarea congelado;
10. implementación.

Nunca invertir este orden. El contrato solo puede congelar decisiones compatibles con las autoridades superiores; una skill auxiliar no puede sobreescribirlas.

## Role separation

- **Planner:** descubre, diseña y congela el contrato; no implementa.
- **Implementer:** implementa únicamente el contrato congelado; no redefine arquitectura, scope ni acceptance criteria.
- **Auditor:** audita independientemente; no modifica código de producción ni tests.
- **Coordinator:** orquesta y aplica gates; no puede eximir findings P0/P1 ni reinterpretar el contrato.

## Contract freeze

No se puede entrar en `IMPLEMENTATION` hasta que el planner emita `CONTRACT STATUS: FROZEN` con:

- task ID, objetivo, branch y base SHA exacta;
- API y paths esperados;
- invariantes, locking, transaction boundary e idempotencia;
- narrow sudo, RBAC, multi-company y primitives nativas de Odoo;
- Event/Outbox y esquema de eventos si aplica;
- acceptance tests exactos y sus conteos esperados;
- Gate A, Gate B, Git Gate y out of scope.

El implementer no puede cambiar el contrato. Si el contrato resulta inválido, debe devolver `STATE = CONTRACT_BLOCKED`; solo el planner puede emitir `CONTRACT AMENDMENT` y volver a congelarlo.

## Audit order

El auditor debe revisar, en este orden:

1. contrato congelado;
2. estado y diff de Git;
3. source de producción;
4. tests;
5. documentación;
6. schema/security;
7. walkthrough y evidencia runtime.

No debe comenzar por el walkthrough del desarrollador.

## Verdict

- P0/P1 encontrado: `FAIL`.
- Sin P0/P1 pero sin evidencia runtime obligatoria: `PENDING`.
- Todos los gates y evidencias satisfechos: `PASS / READY FOR PR`.

## Git safety

Los agentes nunca deben hacer push directo a `develop`, force-push, merge automático, borrar ramas protegidas ni crear PR salvo que una política humana explícita lo habilite. El workflow termina en `PASS / READY FOR PR`.
