---
name: odoo-data-migration
description: >-
  Usar este skill cuando el usuario pida crear migraciones de datos, actualizar
  versiones de módulos, manejar cambios de schema de base de datos, o cuando se
  pregunte sobre el protocolo de migración del proyecto (ADR-022). Incluye scripts
  pre/post-migrate y compatibilidad backward para rolling updates.
---

# Migraciones de Datos — Odoo 19

Guía para crear y gestionar migraciones de datos y schema en módulos Odoo 19.

> **ADR-022**: Database schema migrations son release-gated — las migraciones deben ser backward-compatible durante el rolling update.

---

## Cuándo se Necesita una Migración

| Escenario | ¿Migración necesaria? |
|---|---|
| Agregar campo nuevo | No — Odoo lo crea automáticamente al actualizar |
| Renombrar campo | Sí — datos se pierden sin migración |
| Cambiar tipo de campo | Sí — requiere conversión de datos |
| Eliminar campo | Sí — limpieza y respaldo de datos |
| Cambiar `_name` de modelo | Sí — renombrar tabla e ir.model.data |
| Agregar `models.Constraint()` a datos existentes | Sí — datos existentes podrían violar la constraint |
| Cambiar lógica de computed stored | No — se recalcula al actualizar |
| Mover datos entre modelos | Sí — script de migración |
| Cambiar versión del módulo | Automático — trigger para scripts de migración |

---

## Estructura de Migraciones

```text
custom_addons/wms_work_engine/
├── __manifest__.py                  # version: '19.0.1.1.0'
└── migrations/
    └── 19.0.1.1.0/                  # Coincide con la nueva versión
        ├── pre-migrate.py           # Se ejecuta ANTES de actualizar modelos
        ├── post-migrate.py          # Se ejecuta DESPUÉS de actualizar modelos
        └── end-migrate.py           # Se ejecuta al final de todo el upgrade
```

### ¿Cuándo usar cada script?

| Script | Momento | Caso de uso |
|---|---|---|
| `pre-migrate.py` | Antes de que Odoo actualice el schema | Renombrar columnas, crear columnas temporales, respaldo de datos |
| `post-migrate.py` | Después de que Odoo actualice el schema | Migrar datos, llenar campos nuevos, recalcular values |
| `end-migrate.py` | Al final de TODO el proceso de upgrade | Limpieza final, verificación de integridad |

---

## Templates de Scripts de Migración

### pre-migrate.py

```python
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migración: se ejecuta antes de que Odoo actualice el schema.
    Usar para renombrar columnas, respaldar datos, etc.

    Args:
        cr: cursor de base de datos (sin ORM disponible)
        version: versión anterior del módulo instalado
    """
    if not version:
        # Primera instalación, no hay nada que migrar
        return

    _logger.info('Pre-migración wms_work_engine %s → 19.0.1.1.0', version)

    # Ejemplo: Renombrar columna antes de que Odoo la elimine
    cr.execute("""
        ALTER TABLE wms_work
        RENAME COLUMN old_field_name TO new_field_name
    """)

    # Ejemplo: Respaldar datos de columna que se va a eliminar
    cr.execute("""
        ALTER TABLE wms_work
        ADD COLUMN IF NOT EXISTS _backup_removed_field VARCHAR
    """)
    cr.execute("""
        UPDATE wms_work
        SET _backup_removed_field = removed_field
        WHERE removed_field IS NOT NULL
    """)
```

### post-migrate.py

```python
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Post-migración: se ejecuta después de que Odoo actualice el schema.
    El ORM está disponible a través del environment.

    Args:
        cr: cursor de base de datos
        version: versión anterior del módulo instalado
    """
    if not version:
        return

    _logger.info('Post-migración wms_work_engine %s → 19.0.1.1.0', version)

    env = api.Environment(cr, SUPERUSER_ID, {})

    # Ejemplo: Llenar campo nuevo con valor calculado
    works = env['wms.work'].search([('new_field', '=', False)])
    for work in works:
        work.new_field = work._compute_default_value()

    _logger.info('Migrados %d registros de wms.work', len(works))

    # Ejemplo: Migración con SQL directo (más eficiente para grandes volúmenes)
    cr.execute("""
        UPDATE wms_work
        SET priority_class = CASE
            WHEN priority >= 80 THEN 'high'
            WHEN priority >= 40 THEN 'medium'
            ELSE 'low'
        END
        WHERE priority_class IS NULL
    """)
```

---

## Protocolo de Migración del Proyecto (ADR-022)

En este proyecto, múltiples workloads (`backoffice`, `wms-rf`, `wms-worker`) comparten la misma base de datos. Una migración no puede romper pods activos.

### Regla Fundamental

> Cada migración de schema debe poder coexistir con la versión anterior del código durante al menos 5 minutos (tiempo de rolling update).

### Protocolo de 4 Pasos

```text
1. PRE-DEPLOY (migrations backward-compatible)
   ✅ Agregar columnas nuevas (con DEFAULT)
   ✅ Agregar tablas nuevas
   ✅ Crear índices
   ❌ NO renombrar columnas que el código viejo usa
   ❌ NO eliminar columnas
   ❌ NO cambiar tipos de datos

2. DEPLOY (rolling update)
   - Pods nuevos coexisten con pods viejos
   - Ambos deben funcionar con el mismo schema
   - Duración máxima: 5 minutos

3. POST-DEPLOY (migrations que rompen backward-compat)
   - Solo se ejecutan cuando TODOS los pods tienen código nuevo
   ✅ Eliminar columnas obsoletas
   ✅ Renombrar columnas (si el código nuevo ya no usa el nombre viejo)
   ✅ Cambiar tipos de datos

4. VERIFICATION
   - Health checks
   - Smoke tests
   - Performance baseline comparison
```

### Migración Backward-Compatible (Ejemplo)

Renombrar un campo de `zone_id` a `activity_area_id`:

```python
# PRE-DEPLOY: Agregar campo nuevo, copiar datos
# pre-migrate.py (versión 19.0.1.1.0)
def migrate(cr, version):
    cr.execute("""
        ALTER TABLE wms_work
        ADD COLUMN IF NOT EXISTS activity_area_id INTEGER
    """)
    cr.execute("""
        UPDATE wms_work SET activity_area_id = zone_id
        WHERE zone_id IS NOT NULL
    """)

# DEPLOY: El código nuevo lee de activity_area_id
# El código viejo sigue leyendo de zone_id (ambos existen)

# POST-DEPLOY: Eliminar campo viejo (versión 19.0.1.2.0)
# post-migrate.py
def migrate(cr, version):
    cr.execute("""
        ALTER TABLE wms_work DROP COLUMN IF EXISTS zone_id
    """)
```

---

## Versionamiento de Módulos

Formato: `<odoo_version>.<major>.<minor>.<patch>`

```python
# __manifest__.py
{
    'version': '19.0.1.0.0',   # Release inicial
    # '19.0.1.0.1',             # Bugfix sin migración
    # '19.0.1.1.0',             # Feature con migración
    # '19.0.2.0.0',             # Major change
}
```

La carpeta de migración debe coincidir exactamente con la nueva versión:

```text
migrations/
├── 19.0.1.1.0/     # Migración de 19.0.1.0.x a 19.0.1.1.0
│   └── post-migrate.py
└── 19.0.2.0.0/     # Migración de 19.0.1.x.x a 19.0.2.0.0
    ├── pre-migrate.py
    └── post-migrate.py
```

---

## Mejores Prácticas

1. **Siempre probar la migración** contra un respaldo de la BD de producción
2. **Respaldar la BD** antes de cualquier migración: `./scripts/backup-db.ps1 -DbName "odoo_dev"`
3. **Usar SQL directo** para migraciones masivas (> 10,000 registros) en vez del ORM
4. **Loggear** todo: registros afectados, errores encontrados, tiempo de ejecución
5. **Hacer las migraciones idempotentes**: ejecutarlas dos veces debe producir el mismo resultado
6. **No usar `env.ref()` en pre-migrate** — los datos XML podrían no existir aún

---

## Verificación

1. ¿La carpeta de migración coincide exactamente con la nueva versión?
2. ¿El script pre-migrate no usa el ORM?
3. ¿La migración es backward-compatible (PRE-DEPLOY)?
4. ¿Se respaldó la BD antes de probar?
5. ¿La migración es idempotente?
6. ¿Se probó el rolling update (pods viejos + nuevos coexistiendo)?
