---
name: git-workflow
description: >-
  Usar este skill cuando el usuario pregunte sobre el flujo de trabajo con Git,
  cómo crear ramas, hacer merges, preparar releases, manejar hotfixes, o cualquier
  operación de control de versiones. El proyecto usa GitFlow como estrategia de
  branching adaptada para desarrollo de módulos Odoo con Docker/K8s.
---

# GitFlow — Flujo de Trabajo Git

Estrategia de branching GitFlow adaptada para el proyecto ERP-WMS-TMS con Odoo 19, Docker y Kubernetes.

---

## Modelo de Ramas

```text
main ─────────────────●──────────────────●──────────────── producción
                     ╱                  ╱
                    ╱ merge            ╱ merge
                   ╱                  ╱
release/1.0.0 ────●─────●           ╱
                 ╱       │ bugfix   ╱
                ╱        ▼         ╱
develop ──●──●──●──●──●──●──●──●──●──●──●──●────────────── integración
          │     │        ▲        │     │
          │     │        │        │     │
          │     └─ feature/wms-work-engine
          │              │
          └── feature/wms-dock-management
                         │
                    hotfix/fix-pick-confirm ──── (desde main)
```

### Ramas Permanentes

| Rama | Propósito | Quién hace merge |
|---|---|---|
| `main` | Producción — código desplegado | Solo desde `release/*` o `hotfix/*` |
| `develop` | Integración — última versión de desarrollo | Desde `feature/*` vía PR |

### Ramas Temporales

| Rama | Origen | Destino | Convención de nombre |
|---|---|---|---|
| `feature/*` | `develop` | `develop` | `feature/<modulo>-<descripcion>` |
| `release/*` | `develop` | `main` + `develop` | `release/<version>` |
| `hotfix/*` | `main` | `main` + `develop` | `hotfix/<descripcion-corta>` |
| `bugfix/*` | `release/*` | `release/*` + `develop` | `bugfix/<descripcion-corta>` |

---

## Ciclo de Desarrollo Completo

### 1. Crear Feature Branch

```bash
# Asegurarse de estar en develop actualizado
git checkout develop
git pull origin develop

# Crear la rama de feature
git checkout -b feature/wms-dock-management

# Trabajar en la feature...
git add .
git commit -m "feat(wms-dock): agregar modelo wms.dock con estado y capacidades"
```

#### Nomenclatura de Features

```text
feature/wms-work-engine          ← módulo nuevo completo
feature/wms-location-extend      ← extensión de modelo existente
feature/erp-partner-fields       ← extensión ERP
feature/tms-route-planning       ← módulo TMS
feature/infra-ci-pipeline        ← infraestructura/CI
feature/docs-adr-028             ← documentación
```

### 2. Mantener Feature Actualizada

```bash
# Sincronizar con develop periódicamente (rebase preferido)
git checkout feature/wms-dock-management
git fetch origin
git rebase origin/develop

# Si hay conflictos, resolverlos y continuar
git rebase --continue

# Si el rebase es muy complejo, usar merge como alternativa
git merge origin/develop
```

> **Regla**: Hacer rebase contra `develop` al menos una vez al día si la feature dura más de 2 días.

### 3. Pull Request a Develop

```bash
# Push de la feature
git push origin feature/wms-dock-management
```

Crear PR en la plataforma (GitHub/GitLab) con:
- **Título**: Sigue el formato de commit convencional (ej: `feat(wms-dock): modelo y vistas de dock management`)
- **Descripción**: Qué hace, por qué, ADRs relevantes, cómo probar
- **Reviewers**: Al menos 1 revisor
- **Labels**: `wms`, `feature`, `odoo-module`

#### Checklist del PR

```markdown
- [ ] Tests pasan: `docker compose exec odoo odoo --test-enable --stop-after-init -i <modulo> -d odoo_test`
- [ ] Módulo se instala sin errores
- [ ] Seguridad configurada (ir.model.access.csv + grupos)
- [ ] Migraciones son backward-compatible (ADR-022)
- [ ] ADRs respetados (011, 012, 013, 026)
- [ ] Documentación actualizada si aplica
```

### 4. Merge a Develop

```bash
# Merge con squash para features pequeñas
git checkout develop
git merge --squash feature/wms-dock-management
git commit -m "feat(wms-dock): modelo completo de dock management (#42)"

# Merge sin squash para features grandes (preserva historia)
git checkout develop
git merge --no-ff feature/wms-dock-management

# Eliminar la rama
git branch -d feature/wms-dock-management
git push origin --delete feature/wms-dock-management
```

> **Preferencia del proyecto**: Usar `--no-ff` (no fast-forward) para mantener la historia de la rama visible en el log.

---

## Releases

### 5. Crear Release Branch

Cuando `develop` tiene suficientes features para un release:

```bash
git checkout develop
git pull origin develop

# Crear rama de release
git checkout -b release/19.0.1.0.0
```

#### En la rama de release:

1. **Actualizar versiones** en todos los `__manifest__.py` afectados
2. **Ejecutar tests completos**: todos los módulos
3. **Verificar migraciones**: protocolo ADR-022
4. **Solo bugfixes** — NO se agregan features nuevas
5. **Actualizar CHANGELOG** si existe

```bash
# Bugfix en la rama de release
git commit -m "fix(wms-work): corregir validación de prioridad en edge case"
```

### 6. Finalizar Release

```bash
# Merge a main
git checkout main
git pull origin main
git merge --no-ff release/19.0.1.0.0
git tag -a v19.0.1.0.0 -m "Release 19.0.1.0.0 — WMS Dock Management + Work Engine fixes"
git push origin main --tags

# Merge de vuelta a develop (para incluir bugfixes del release)
git checkout develop
git merge --no-ff release/19.0.1.0.0
git push origin develop

# Eliminar rama de release
git branch -d release/19.0.1.0.0
git push origin --delete release/19.0.1.0.0
```

#### Versionamiento de Tags

```text
v19.0.1.0.0    ← Coincide con la versión de Odoo en __manifest__.py
v19.0.1.1.0    ← Minor: features nuevas
v19.0.1.1.1    ← Patch: bugfixes
v19.0.2.0.0    ← Major: breaking changes
```

---

## Hotfixes

### 7. Hotfix (corrección urgente en producción)

Cuando hay un bug crítico en `main` que no puede esperar al próximo release:

```bash
# Crear desde main
git checkout main
git pull origin main
git checkout -b hotfix/fix-pick-confirm-duplicate

# Corregir el bug
git commit -m "fix(wms-work): prevenir duplicación en confirm pick por race condition

ADR-010: se refuerza la idempotencia del confirm pick con
INSERT ON CONFLICT en la tabla wms_idempotency."

# Merge a main
git checkout main
git merge --no-ff hotfix/fix-pick-confirm-duplicate
git tag -a v19.0.1.0.1 -m "Hotfix: prevenir duplicación en confirm pick"
git push origin main --tags

# Merge a develop (para que el fix no se pierda)
git checkout develop
git merge --no-ff hotfix/fix-pick-confirm-duplicate
git push origin develop

# Si hay un release activo, merge también ahí
git checkout release/19.0.1.1.0
git merge --no-ff hotfix/fix-pick-confirm-duplicate

# Eliminar rama
git branch -d hotfix/fix-pick-confirm-duplicate
git push origin --delete hotfix/fix-pick-confirm-duplicate
```

> **Importante**: Un hotfix SIEMPRE se mergea tanto a `main` como a `develop` (y al release activo si existe).

---

## Relación con el Protocolo de Migración (ADR-022)

El flujo de GitFlow se integra con el protocolo de deploy:

```text
feature/wms-new-field
    │
    ▼
develop ──── CI: lint + tests
    │
    ▼
release/19.0.1.1.0
    │
    ├── 1. PRE-DEPLOY: migraciones backward-compatible
    │      (ALTER TABLE ADD COLUMN, nuevas tablas, índices)
    │
    ├── 2. DEPLOY: rolling update de pods
    │      (pods viejos + nuevos coexisten ~5 min)
    │
    ├── 3. POST-DEPLOY: migraciones breaking
    │      (DROP COLUMN, ALTER TYPE — solo cuando todos los pods son nuevos)
    │
    └── 4. VERIFICATION: health checks + smoke tests
```

### Regla para Migraciones

- Las migraciones PRE-DEPLOY van en el **mismo commit** que el feature
- Las migraciones POST-DEPLOY van en un **commit separado** en la rama de release
- Nunca incluir migraciones POST-DEPLOY en una feature branch

---

## Flujo Resumido

```text
┌─────────┐    PR + Review    ┌─────────┐    Release     ┌──────┐
│ feature │ ─────────────────▶│ develop │ ──────────────▶│ main │
└─────────┘                   └─────────┘                └──────┘
                                   ▲                        │
                                   │                        │
                                   └────── hotfix ──────────┘
```

| Acción | Comando rápido |
|---|---|
| Nueva feature | `git checkout develop && git checkout -b feature/<nombre>` |
| Sync con develop | `git fetch origin && git rebase origin/develop` |
| Crear release | `git checkout develop && git checkout -b release/<version>` |
| Finalizar release | merge `release` → `main` (tag) → `develop` |
| Hotfix | `git checkout main && git checkout -b hotfix/<nombre>` |
| Finalizar hotfix | merge `hotfix` → `main` (tag) → `develop` |

---

## Verificación

1. ¿La rama se creó desde la base correcta (`develop` para features, `main` para hotfixes)?
2. ¿Los commits siguen la convención de mensajes del proyecto?
3. ¿La feature se rebaseó contra `develop` antes del PR?
4. ¿El release se mergeó tanto a `main` como a `develop`?
5. ¿El hotfix se mergeó tanto a `main` como a `develop`?
6. ¿Se creó un tag con la versión correcta al mergear a `main`?
