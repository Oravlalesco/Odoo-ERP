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

### Estado implementado y siguiente slice

El discovery debe distinguir el roadmap de alto nivel del avance incremental real:

1. Inspecciona `git log --first-parent develop` y los merges recientes de `develop`. No uses `git log --grep` como única evidencia: puede omitir merges cuyo mensaje no contiene el nombre del dominio.
2. Lee primero `docs/README.md`; después abre el documento del programa que contiene la fase marcada `IN PROGRESS`. No uses documentos marcados como `SUPERSEDED` o históricos como autoridad de implementación.
3. Contrasta el historial con el README del módulo activo, su source y sus tests. El último trabajo merged debe ser el slice incremental más reciente integrado en `develop`, no un commit arbitrario relacionado con WMS.
4. Identifica el siguiente task ID concreto en el módulo activo. Una fase completa (`Fase 7`, por ejemplo) no es un slice implementable.
5. Si Git, roadmap, README, source o tests discrepan, devuelve `CONTRACT BLOCKED` con la contradicción; no completes los huecos por inferencia.

En un smoke test read-only no escribas el contrato, pero aplica el mismo discovery y devuelve la evidencia que permitiría seleccionar el task ID.

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
