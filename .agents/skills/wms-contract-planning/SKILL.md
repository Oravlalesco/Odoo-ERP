---
name: wms-contract-planning
description: >-
  Planificar slices WMS contra la documentación autoritativa y producir
  contratos técnicos congelados antes de cualquier implementación.
---

# WMS Contract Planning

Usa esta skill solo para discovery y diseño. No escribas producción ni tests de implementación.

## Discovery obligatorio

Resuelve y registra:

- `git branch --show-current`, `git rev-parse HEAD` y base SHA de `develop`;
- estado limpio/sucio y cambios no relacionados;
- roadmap y último trabajo merged relevante;
- ADRs y documentación de plataforma/dominio aplicables;
- módulo, modelos, vistas, seguridad y tests actuales;
- Odoo pinned y mecanismo ORM nativo que ejecutará la mutación, si aplica.

La autoridad es: ADR -> plataforma -> dominios -> roadmap -> README -> source/tests -> skills auxiliares. Una contradicción bloquea el contrato.

## Contract Freeze

Escribe `.wms-agent-state/contracts/<task-id>.md` con:

```text
CONTRACT STATUS: DRAFT | FROZEN | BLOCKED
TASK ID:
BASE SHA:
BRANCH:
GOAL:
API / ENTRYPOINT:
EXPECTED PATHS:
INVARIANTS:
LOCKING:
TRANSACTION BOUNDARY:
IDEMPOTENCY:
NARROW SUDO:
RBAC:
MULTI-COMPANY:
ODOO NATIVE PRIMITIVES:
EVENT / OUTBOX:
ACCEPTANCE TESTS (exact IDs and expected count):
GATE A:
GATE B:
GIT GATE:
OUT OF SCOPE:
```

`FROZEN` requiere base SHA exacta, paths y conteos de tests verificables, y gates ejecutables. Si falta una decisión, usa `BLOCKED`. Solo el planner puede emitir un `CONTRACT AMENDMENT` y volver a congelar.
