---
name: git-workflow
description: >-
  Usar este skill cuando el usuario pregunte sobre el flujo de trabajo con Git,
  cómo crear ramas, hacer merges, preparar releases, manejar hotfixes, o cualquier
  operación de control de versiones. El proyecto usa GitFlow como estrategia de
  branching adaptada para desarrollo de módulos Odoo con Docker/K8s.
---

# GitFlow y Control de Versiones — Odoo 19

Estrategia de branching GitFlow adaptada para el desarrollo incremental por Task Contracts en el proyecto ERP-WMS-TMS.

---

## 🛑 Protocolo de Merge de Tasks Contractuales WMS

Para cada slice o tarea técnica revisada bajo Task Contract:

```text
1. BASE CONGELADA:
   Se fija un baseline SHA en develop (ej: develop@9926c4f...).
   La feature branch se crea directamente desde este baseline exacto ($FROZEN_BASE).

2. EXACT COMMIT COUNT:
   La feature branch contiene exactamente el número de commits autorizado (típicamente 1 commit exacto).

3. REVIEW & APPROVED HEAD:
   El reviewer audita el código y aprueba un commit HEAD exacto (ej: HEAD 8fcf736...).

4. DESPUÉS DE APPROVED HEAD:
   - ⛔ NO hacer rebase
   - ⛔ NO hacer amend
   - ⛔ NO hacer squash
   - ⛔ NO agregar commits adicionales
   - Ningún SHA involucrado puede cambiar tras la aprobación

5. VERIFICACIÓN PRE-MERGE (DOBLE ASSERT):
   - git fetch origin
   - Comprobar que origin/develop coincide exactamente con la BASE CONGELADA.
   - Comprobar que el develop local coincide exactamente con la BASE CONGELADA.
   - Si cualquiera diverge: ⛔ STOP NO MERGE (detener, recongelar baseline y reauditar).

6. MERGE & VERIFICACIÓN POST-MERGE:
   - git checkout develop && git merge --no-ff feature/...
   - ✓ merge.parents[0] == baseline develop anterior (FROZEN_BASE)
   - ✓ merge.parents[1] == approved feature HEAD
   - ✓ merge.tree == approved feature HEAD tree
   - ✓ develop == merge SHA
   - ✓ Feature branch eliminada tanto local como remotamente
   - ✓ Congelar nuevo baseline SHA
```

---

## Modelo de Ramas

```text
main ─────────────────●──────────────────●──────────────── producción
                     ╱                  ╱
                    ╱ merge --no-ff    ╱ merge --no-ff
                   ╱                  ╱
release/1.0.0 ────●─────●           ╱
                 ╱       │ bugfix   ╱
                ╱        ▼         ╱
develop ──●──●──●──●──●──●──●──●──●──●──●──●────────────── integración
          │     │        ▲        │     │
          │     │        │        │     │
          │     └─ feature/wms-work-engine
          │              │
          └── feature/hu-003a-sscc-generator
```

### Ramas Permanentes

| Rama | Propósito | Regla de Merge |
|---|---|---|
| `main` | Producción — código desplegado | Solo desde `release/*` o `hotfix/*` mediante PR |
| `develop` | Integración — baseline de desarrollo | Solo desde `feature/*` aprobadas vía `--no-ff` |

### Ramas Temporales

| Rama | Origen | Destino | Convención de Nombre |
|---|---|---|---|
| `feature/*` | `develop` | `develop` | `feature/<modulo>-<descripcion>` o `feature/<task-id>-<slug>` |
| `release/*` | `develop` | `main` + `develop` | `release/<version>` |
| `hotfix/*` | `main` | `main` + `develop` | `hotfix/<descripcion-corta>` |

---

## Ciclo de Desarrollo de una Feature Contractual

### 1. Crear Feature Branch desde la BASE Congelada

En tareas contractuales, la rama **NO** se crea desde "lo último de develop", sino desde el SHA exacto congelado (`$FROZEN_BASE`):

```bash
git fetch origin
git checkout -b feature/<task-id>-<slug> "$FROZEN_BASE"

# Verificar inmediatamente que el merge-base es exactamente el baseline acordado:
test "$(git merge-base "$FROZEN_BASE" HEAD)" = "$FROZEN_BASE"
```

### 2. Desarrollo y Commits Estructurados

```bash
git add custom_addons/wms_inventory/
# Mensaje conciso (máximo 72 caracteres en la primera línea)
git commit -m "feat(inventory): agregar journal operacional de inventario"
```

### 3. Sincronización Pre-Review

En tasks contractuales con BASE congelada:
- `git commit --amend` está permitido antes del approval si se conserva exactamente el mismo baseline.
- **⛔ NO** hacer `git rebase origin/develop` solo porque `develop` haya avanzado remotamente.
- Si es imprescindible cambiar la BASE: **detener la tarea**, acordar y recongelar un nuevo baseline, rebasear y repetir todos los gates de auditoría y runtime.

```bash
# Push inicial
git push -u origin feature/<task-id>-<slug>
# Si hubo amend pre-review conservando la BASE congelada:
git push --force-with-lease origin feature/<task-id>-<slug>
```

### 4. Merge a Develop tras Aprobación

```bash
# 1. Doble verificación estricta de BASE congelada
git fetch origin

# Comprobación de que tanto el remoto como el local están en FROZEN_BASE:
# test "$(git rev-parse origin/develop)" = "$FROZEN_BASE"
# test "$(git rev-parse develop)" = "$FROZEN_BASE"
# Si cualquiera no coincide → ⛔ STOP NO MERGE (no hacer git pull ciego)

# 2. Merge --no-ff exacto
git checkout develop
git merge --no-ff feature/<task-id>-<slug>
git push origin develop

# 3. Eliminación de la rama
git branch -d feature/<task-id>-<slug>
git push origin --delete feature/<task-id>-<slug>
```

---

## Evidencia de Review y Walkthrough Obligatoria

Antes de solicitar la aprobación de un PR o Task, el informe / walkthrough debe contener:

| Elemento | Requisito de Evidencia |
|---|---|
| **BASE Congelada** | SHA exacto del baseline inicial acordado |
| **Commit HEAD** | `CANDIDATE HEAD` en pre-review / `APPROVED HEAD` tras aprobación |
| **Commit Count** | Exactamente el número autorizado (típicamente 1) |
| **Changed Files** | Lista exacta de archivos modificados (diff exacto con Task Contract) |
| **Task / ADRs** | Identificadores de la tarea y ADRs aplicables |
| **Gates Exigidos** | Evidencia de los gates requeridos por el Task Contract: para código runtime, Clean Install / Upgrade y tests; para tareas documentales/tooling, static gates correspondientes |
| **Directivas Globales** | Verificación estática: `Product Unit`, 100% español, sin `sudo()`, etc. |
| **Desviaciones** | Cero desviaciones no autorizadas respecto al contrato |

---

## Releases y Hotfixes

### Release Branch

```bash
git checkout -b release/19.0.1.0.0 develop
# Ajustes de versión en __manifest__.py y tests completos
git checkout main
git merge --no-ff release/19.0.1.0.0
git tag -a v19.0.1.0.0 -m "Release 19.0.1.0.0"
git push origin main --tags

git checkout develop
git merge --no-ff release/19.0.1.0.0
git push origin develop
git branch -d release/19.0.1.0.0
```

### Hotfix Branch

```bash
git checkout -b hotfix/fix-quant-lock main
# Corrección crítica...
git checkout main
git merge --no-ff hotfix/fix-quant-lock
git tag -a v19.0.1.0.1 -m "Hotfix: quant lock issue"
git push origin main --tags

git checkout develop
git merge --no-ff hotfix/fix-quant-lock
git push origin develop
git branch -d hotfix/fix-quant-lock
```

---

## Checklist de Verificación Git

1. ¿La rama feature se originó directamente desde el SHA congelado `$FROZEN_BASE`?
2. ¿El diff contiene **exactamente** los archivos autorizados por el Task Contract?
3. ¿El número de commits es el exacto requerido (típicamente 1 commit)?
4. ¿La primera línea del commit tiene ≤72 caracteres y sigue Conventional Commits?
5. ¿Se evitó hacer rebase ciego contra `develop` durante y después del review?
6. ¿Tras la aprobación del HEAD, se verificó que **tanto `origin/develop` como `develop` local** coinciden con la BASE congelada antes del merge `--no-ff`?
7. ¿El tree de `develop` post-merge coincide exactamente con el tree del HEAD aprobado?
8. ¿El walkthrough contiene toda la evidencia requerida según el tipo de tarea (runtime vs documental)?
