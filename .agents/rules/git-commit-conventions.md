# Convenciones de Commits — Conventional Commits

Estas reglas aplican a **todos los commits** del proyecto. Son obligatorias.

---

## Formato de Commit

```text
<tipo>(<alcance>): <descripción>

[cuerpo opcional]

[footer opcional]
```

### Tipo (obligatorio)

| Tipo | Cuándo usar | Ejemplo |
|---|---|---|
| `feat` | Nueva funcionalidad | `feat(wms-work): agregar máquina de estados del Work` |
| `fix` | Corrección de bug | `fix(wms-dock): corregir validación de capacidad` |
| `refactor` | Refactorización sin cambio funcional | `refactor(wms-work): extraer lógica de claim a método privado` |
| `docs` | Cambios en documentación | `docs(adr): agregar ADR-028 sobre RF offline` |
| `test` | Agregar o corregir tests | `test(wms-work): agregar test de concurrencia para claim` |
| `chore` | Tareas de mantenimiento | `chore(docker): actualizar imagen base a odoo:19.0@sha256:...` |
| `style` | Formato, whitespace, sin cambio lógico | `style(wms-work): aplicar formato PEP8` |
| `perf` | Mejora de performance | `perf(allocation): optimizar query de candidatos con índice` |
| `ci` | Cambios en CI/CD | `ci: agregar stage de tests al pipeline` |
| `build` | Cambios en build/dependencias | `build(docker): agregar librería pika para RabbitMQ` |
| `revert` | Revertir un commit anterior | `revert: revert "feat(wms-dock): ..."` |

### Alcance (recomendado)

El alcance identifica el módulo o componente afectado:

```text
feat(wms-work): ...        ← Módulo wms_work_engine
fix(wms-dock): ...         ← Módulo wms_dock_management
docs(adr): ...             ← Architecture Decision Records
test(wms-alloc): ...       ← Tests del módulo de allocation
chore(k8s): ...            ← Manifiestos de Kubernetes
ci(pipeline): ...          ← Pipeline CI/CD
build(docker): ...         ← Dockerfile o docker-compose
```

### Descripción (obligatoria)

- En español
- Empieza con verbo en infinitivo: `agregar`, `corregir`, `actualizar`, `eliminar`, `refactorizar`
- Sin punto final
- Máximo 72 caracteres en la primera línea

### Cuerpo (opcional)

Para commits que necesitan explicación adicional:

```text
fix(wms-work): prevenir duplicación en confirm pick

El confirm pick no verificaba idempotencia correctamente cuando
dos requests llegaban simultáneamente. Se implementa el patrón
INSERT ON CONFLICT (ADR-010) para garantizar que solo un request
procesa el comando.

Tablas afectadas: wms_idempotency, wms_work
```

### Footer (opcional)

```text
feat(wms-dock): agregar modelo de dock con appointment

BREAKING CHANGE: se renombra el campo zone_id a activity_area_id
en wms.work. Requiere migración 19.0.1.1.0.

Refs: ADR-028
```

| Footer | Significado |
|---|---|
| `BREAKING CHANGE:` | Cambio que rompe compatibilidad |
| `Refs: ADR-NNN` | Referencia a Architecture Decision Record |
| `Fixes #123` | Cierra un issue |
| `Co-authored-by:` | Co-autoría |

---

## Ejemplos Completos

```text
feat(wms-work): agregar lease protocol con heartbeat

Implementa el protocolo de lease para work assignment (ADR-015/016):
- claim_token único por asignación
- lease_expires_at con renovación por heartbeat
- auto-requeue de ASSIGNED sin ejecución
- RECONCILIATION_REQUIRED para IN_PROGRESS (ADR-025)

Refs: ADR-015, ADR-016, ADR-025
```

```text
fix(stock-location): usar wms_location_role en vez de usage

El código usaba location.usage == 'quality_hold' que no es un valor
válido de Odoo. Corregido para usar wms_location_role según ADR-026.

Refs: ADR-026
```

```text
chore(docker): fijar versión de Odoo por digest

ADR-027 requiere que la versión de Odoo se fije por digest SHA,
no solo por tag, para evitar cambios silenciosos upstream.

Refs: ADR-027
```

---

## Commits Prohibidos

| ❌ Incorrecto | ✅ Correcto |
|---|---|
| `fix bug` | `fix(wms-work): corregir validación de prioridad negativa` |
| `update` | `feat(wms-dock): agregar campo capacity al modelo dock` |
| `WIP` | `feat(wms-dock): agregar modelo base wms.dock (WIP)` |
| `changes` | `refactor(wms-alloc): separar lógica de scoring en servicio` |
| `asdf` | No commitear hasta tener un mensaje descriptivo |
| `feat: add stuff` | `feat(wms-work): agregar generación automática de referencia` |
