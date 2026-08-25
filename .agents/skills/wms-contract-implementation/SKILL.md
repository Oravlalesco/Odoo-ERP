---
name: wms-contract-implementation
description: >-
  Implementar un slice WMS únicamente contra un contrato FROZEN, con
  aislamiento Git, gates Odoo y evidencia de candidate SHA.
---

# WMS Contract Implementation

No implementes nada sin leer el contrato `.wms-agent-state/contracts/<task-id>.md` y verificar `CONTRACT STATUS: FROZEN`.

## Guardrails

- Confirma `BASE SHA`, branch/worktree, expected paths y out of scope antes de editar.
- No rebasees ni mezcles `develop` después del freeze.
- No redefinas invariantes, API, acceptance criteria ni conteos.
- Si el contrato es inválido, detente con `STATE = CONTRACT_BLOCKED` y solicita `CONTRACT AMENDMENT`.
- Para inventario, inspecciona el Odoo pinned y usa el mecanismo ORM nativo; no mutar `stock.quant` directamente.
- Event + Outbox deben pasar por `_append_events_with_outbox()`; el helper no administra la transacción ni usa `sudo()`.
- Commands externos requieren `command_id`/`idempotency_key`; primitives físicas internas no idempotentes permanecen privadas.

## Validación y handoff

Ejecuta exactamente Gate A (instalación limpia), Gate B (upgrade) y los acceptance tests del contrato en las bases permitidas. Reporta comandos, exit codes, resultados y evidencia runtime distinguiendo evidencia local de remota.

Entrega:

- candidate SHA;
- lista de paths y diff summary;
- tests/gates ejecutados y resultados;
- riesgos o bloqueos;
- confirmación de que no se modificó `develop`.
