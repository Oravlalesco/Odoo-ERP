---
name: wms-contract-audit
description: >-
  Auditar de forma independiente un candidate WMS contra contrato FROZEN,
  Git, source, tests, seguridad, documentación y evidencia runtime.
---

# WMS Contract Audit

Audita en modo read-only. Nunca edites ni corrijas el candidate.

## Orden de revisión

1. contrato congelado;
2. branch, base SHA, candidate SHA, estado y diff de Git;
3. production source;
4. tests y conteos contractuales;
5. documentación y ADRs;
6. schema, ACLs, record rules, RBAC y multi-company;
7. walkthrough y evidencia runtime.

No aceptes el walkthrough como sustituto de source o evidencia reproducible.

## Checklist WMS

Verifica expected paths y file-count gate, invariantes, locking selectivo, boundary transaccional, primitive Odoo nativa, Event + Outbox atómicos mediante `_append_events_with_outbox()`, idempotencia de comandos externos, narrow sudo justificado, compatibilidad backward y Gate A/B.

Distingue evidencia local, CI remota y afirmaciones no verificadas. Un test no ejecutado no cuenta como PASS.

## Verdict

Cada finding incluye severidad, path/línea o comando reproducible, impacto y referencia contractual:

- `P0` o `P1`: `FAIL` y retorno al implementer;
- sin P0/P1 pero con evidencia obligatoria faltante: `PENDING`;
- todos los gates, tests y evidencias satisfechos: `PASS / READY FOR PR`.

El auditor no puede cambiar el contrato. Si el contrato es incorrecto, reporta `CONTRACT BLOCKED` al coordinator para que el planner decida una enmienda.
