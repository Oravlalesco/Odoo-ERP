---
name: odoo-data-migration
description: >-
  Usar este skill cuando el usuario pida crear migraciones de datos, actualizar
  versiones de módulos, manejar cambios de schema de base de datos, o cuando se
  pregunte sobre el protocolo de migración del proyecto (ADR-022). Incluye scripts
  pre/post/end-migrate y compatibilidad backward para rolling updates.
---

# Migraciones de Datos y Schema — Odoo 19

Guía para crear y gestionar migraciones de datos y schema en módulos Odoo 19 respetando el protocolo backward-compatible de ADR-022 y las capacidades del `MigrationManager` nativo de Odoo.

> **ADR-022**: Database schema migrations son release-gated — las migraciones deben ser backward-compatible durante el rolling update.

---

## 🛑 Excepción de Contexto de Mantenimiento

> **El uso de `SUPERUSER_ID` y SQL masivo sin ORM mostrado en este skill aplica EXCLUSIVAMENTE a scripts de migración ejecutados por el framework de upgrade de Odoo.**
>
> Los scripts de migración son código de mantenimiento con privilegios elevados que se ejecutan durante ventanas de actualización.
> Está estrictamente prohibido extrapolar o copiar estos patrones a:
> - `models/` (lógica de negocio o métodos de modelos runtime)
> - `controllers/` (endpoints HTTP/API)
> - Servicios o motores WMS runtime
> - Métodos-comando o crons ordinarios

---

## Fases de Ejecución en el `MigrationManager` de Odoo 19

El framework de migraciones de Odoo 19 soporta tres prefijos de script:

```text
custom_addons/<nombre_modulo>/migrations/<version>/
├── pre-migrate.py    # o pre-*.py: Se ejecuta ANTES de actualizar el schema del módulo (solo SQL)
├── post-migrate.py   # o post-*.py: Se ejecuta DESPUÉS de actualizar el schema del módulo (ORM disponible)
└── end-migrate.py    # o end-*.py: Se ejecuta DESPUÉS de que TODOS los módulos del upgrade han cargado
```

| Prefijo | Momento de Ejecución | Entorno Disponible | Uso Principal |
|---|---|---|---|
| `pre-*` | Antes de que Odoo toque el schema del módulo | Solo cursor SQL (`cr`) | DDL aditivo, preparación de columnas temporales, transformaciones SQL |
| `post-*` | Tras cargar el schema y vistas del módulo | ORM disponible (`api.Environment(cr, SUPERUSER_ID, {})`) | Backfill de modelos del módulo, cómputos con lógica ORM |
| `end-*` | Tras actualizar **todos** los módulos del proceso | ORM completo y registry consolidado | Validaciones de integridad cross-módulo, recomputes globales |

---

## Protocolo de Migración Backward-Compatible (ADR-022)

En este proyecto, múltiples pods (`backoffice`, `wms-rf`, `wms-worker`) comparten la base de datos. Cada migración debe permitir que pods viejos y nuevos coexistan durante el rolling update (~5 minutos).

```text
FASE 1: PRE-DEPLOY / EXPAND (Release 1 — Migraciones 100% Backward-Compatible)
   ✅ Agregar columnas nuevas aditivas (ADD COLUMN IF NOT EXISTS)
   ✅ Backfill inicial de datos desde la columna vieja hacia la nueva
   ✅ Agregar tablas nuevas e índices
   ⛔ PROHIBIDO RENAME COLUMN destructivo (rompe pods viejos que consultan el nombre anterior)
   ⛔ PROHIBIDO DROP COLUMN (rompe queries activas del código viejo)

FASE 2: DEPLOY (Rolling update de pods en K8s — Coexistencia de ~5 min)
   ⚠️ IMPORTANTE: El backfill inicial NO es sincronización continua.
   Si ambas versiones pueden escribir durante la ventana de coexistencia:
   - El código nuevo debe implementar compatibilidad de lectura/escritura dual (dual-write/fallback).
   - O el Task Contract debe definir un mecanismo explícito de sincronización transaccional.

FASE 3: POST-DEPLOY / CONTRACT (Release 2 Posterior — Limpieza Breaking)
   - Solo cuando TODOS los pods ejecutan el código nuevo y ningún runtime usa el campo viejo.
   ✅ Retirar la compatibilidad dual
   ✅ Eliminar columnas obsoletas (DROP COLUMN)
   ✅ Eliminar tablas descartadas
```

---

## Templates de Scripts de Migración

### 1. `pre-migrate.py` (Fase Expand — SQL Aditivo sin ORM)

```python
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Pre-migración (PRE-DEPLOY / Expand): aditiva y backward-compatible con código viejo."""
    if not version:
        return

    _logger.info('Ejecutando pre-migración aditiva wms_work_engine %s → 19.0.1.1.0', version)

    # 1. Agregar columna nueva sin destruir la anterior
    cr.execute("""
        ALTER TABLE wms_work
        ADD COLUMN IF NOT EXISTS activity_area_id INTEGER
    """)

    # 2. Backfill masivo eficiente con SQL para no saturar memoria en tablas grandes
    cr.execute("""
        UPDATE wms_work
        SET activity_area_id = zone_id
        WHERE zone_id IS NOT NULL AND activity_area_id IS NULL
    """)
```

### 2. `post-migrate.py` (Fase Backfill / Cómputo con ORM vía `SUPERUSER_ID`)

```python
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Post-migración: se ejecuta después de que Odoo actualizó el schema de este módulo."""
    if not version:
        return

    _logger.info('Ejecutando post-migración wms_work_engine %s → 19.0.1.1.0', version)

    # Excepción de contexto autorizada exclusivamente para migraciones de datos
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Paginación por keyset (id > last_id) preservando el filtro de registros faltantes
    last_id = 0
    while True:
        works = env['wms.work'].search([
            ('id', '>', last_id),
            ('activity_area_id', '=', False),
        ], order='id', limit=1000)
        if not works:
            break

        for work in works:
            # Transformación o cómputo definido por el Task Contract
            work.activity_area_id = work._compute_default_activity_area()

        last_id = works[-1].id
        env.invalidate_all()

    _logger.info('Post-migración completada para wms.work')
```

### 3. `end-migrate.py` (Validaciones Finales Cross-Módulo)

```python
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """End-migración: se ejecuta tras finalizar la actualización de todos los módulos."""
    if not version:
        return

    _logger.info('Ejecutando end-migración wms_work_engine %s → 19.0.1.1.0', version)

    env = api.Environment(cr, SUPERUSER_ID, {})

    # Verificación de integridad cross-módulo una vez que todo el registry está cargado
    invalid_count = env['wms.work'].search_count([
        ('activity_area_id', '=', False),
        ('state', 'not in', ('draft', 'cancelled')),
    ])
    if invalid_count > 0:
        _logger.warning('Existen %d registros de trabajo sin área de actividad asignada tras el upgrade.', invalid_count)
```

---

## Cuándo Usar SQL Masivo vs ORM en Migraciones

| Criterio | SQL Directo en Migración | ORM con `SUPERUSER_ID` |
|---|---|---|
| **Volumen** | Millones de filas (evita OOM y lentitud) | Miles de filas o lotes pequeños |
| **Lógica requerida** | Copia de columnas, valores estáticos, joins SQL | Lógica de negocio compleja, campos calculados con dependencias Python |
| **Fase habitual** | `pre-migrate.py` | `post-migrate.py` / `end-migrate.py` |
| **Manejo de Cache** | No aplica (el ORM aún no está instanciado en pre) | Requiere `env.invalidate_all()` periódico con paginación keyset |

---

## Checklist de Verificación de Migraciones

1. ¿La carpeta de migración coincide exactamente con la versión del `__manifest__.py`?
2. ¿`pre-migrate.py` es puramente aditivo y **NO** realiza `RENAME COLUMN` ni `DROP COLUMN` destructivo?
3. ¿La migración permite la coexistencia pacífica de pods viejos y nuevos durante el rolling update (ADR-022)?
4. ¿Puede un pod viejo escribir después del backfill inicial? Si es así, ¿cómo se mantiene la sincronización entre el schema viejo y nuevo durante la ventana de coexistencia?
5. ¿El uso de `SUPERUSER_ID` está estrictamente restringido a scripts de migración (`post-` / `end-`) y no en runtime (INV-AGENT-005)?
6. ¿La migración por lotes en ORM usa paginación por keyset preservando el filtro de registros no migrados?
7. ¿La migración es idempotente (ejecutarla dos veces produce el mismo resultado)?
8. ¿Si se utiliza `end-migrate.py`, la operación justifica ejecutarse tras el cierre de todos los módulos?
