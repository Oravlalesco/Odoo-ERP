---
name: odoo-module-scaffold
description: >-
  Usar este skill cuando el usuario pida crear un nuevo módulo (addon) de Odoo,
  generar la estructura de directorios de un módulo, o inicializar un addon
  personalizado en custom_addons/. También se activa cuando se pregunte cómo
  organizar un nuevo módulo WMS, TMS o ERP.
---

# Scaffold de Módulos — Odoo 19

Guía para crear e inicializar módulos (addons) en `custom_addons/` siguiendo la metodología de desarrollo incremental por slices.

---

## 🛑 Estructura Incremental por Slices

> **Un addon contiene ÚNICAMENTE los directorios y archivos exigidos por el Task Contract actual.**
>
> Está estrictamente prohibido crear directorios vacíos, archivos vacíos o componentes anticipados "por completitud".

### Ejemplos de Estructuras según el Slice

#### 1. Pure Scaffold (Slice Inicial de Inicialización)
```text
custom_addons/wms_example/
├── __init__.py
├── __manifest__.py
├── README.md
└── tests/
    ├── __init__.py
    └── test_module_installation.py
```

#### 2. Core Model & Security (Slice de Modelo sin UI)
```text
custom_addons/wms_example/
├── __init__.py
├── __manifest__.py
├── README.md
├── models/
│   ├── __init__.py
│   └── example_model.py
├── security/
│   ├── ir.model.access.csv
│   └── wms_example_security.xml
└── tests/
    ├── __init__.py
    └── test_example_model.py
```

#### 3. Backoffice UI (Slice Posterior de Interfaz)
```text
custom_addons/wms_example/
└── views/
    ├── example_views.xml
    └── example_menus.xml
```

---

## Catálogo de Estructura Completa Posible de un Addon

> **⚠️ Advertencia**: La siguiente lista muestra las carpetas estándar que un addon puede llegar a tener a lo largo de su ciclo de vida.
> **Existir en este catálogo NO autoriza a crear la carpeta.** Cada carpeta se crea únicamente cuando el Task Contract vigente la especifica.

```text
custom_addons/<nombre_modulo>/
├── __manifest__.py           # Metadata del módulo (obligatorio)
├── __init__.py               # Imports raíz de Python (obligatorio)
├── README.md                 # Documentación del módulo
├── models/                   # Modelos persistentes (si el módulo define datos)
├── security/                 # Grupos, privilegios, ACLs y record rules (si hay modelos)
├── views/                    # Vistas XML, acciones y menús (solo si hay UI requerida)
├── data/                     # Datos iniciales / secuencias / datos no modificables
├── demo/                     # Datos de prueba para desarrollo
├── wizards/                  # TransientModels y wizards interactivos
├── reports/                  # Reportes QWeb / PDF / ZPL
├── controllers/              # Controladores HTTP / JSON-RPC
├── migrations/               # Scripts de migración pre/post/end (ADR-022)
├── i18n/                     # Archivos de traducción (.po)
├── static/                   # Recursos frontend (JS, CSS, SCSS, XML OWL, imágenes)
└── tests/                    # Tests unitarios y de integración (obligatorio)
```

---

## Template de `__manifest__.py`

```python
{
    'name': 'Motor de Trabajo WMS',               # Nombre visible en español (INV-AGENT-001)
    'version': '19.0.1.0.0',                      # Formato: 19.0.major.minor.patch
    'category': 'Inventory/WMS',
    'summary': 'Motor de trabajo dirigido WMS',
    'description': """
Motor de Trabajo Dirigido WMS
==============================
Transforma necesidades logísticas en unidades de trabajo ejecutables.
    """,
    'author': 'Equipo de Desarrollo',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'wms_core',
    ],
    'data': [
        'security/security.xml',                   # 1. Privilegios y Grupos
        'security/ir.model.access.csv',            # 2. ACLs
        # Vistas y datos solo si el slice actual los incluye:
        # 'views/work_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
```

---

## Convenciones de Nomenclatura

| Elemento | Convención | Ejemplo |
|---|---|---|
| Directorio del módulo | `snake_case` con prefijo | `wms_inventory`, `tms_routing` |
| Nombre técnico (`_name`) | Puntos como separador, prefijo `wms.` / `tms.` | `wms.work`, `wms.inventory.event` |
| Tabla SQL (automática) | Puntos convertidos a underscores | `wms_work`, `wms_inventory_event` |
| Archivos Python de modelo | `snake_case` sin prefijo de módulo | `inventory_event.py`, `work.py` |
| Archivos XML de vistas | `<modelo>_views.xml` | `work_views.xml` |
| Archivos de seguridad | `security.xml` o `<modulo>_security.xml` | `wms_inventory_security.xml` |

---

## Ejecución con Docker Compose

```bash
# 1. Inicialización limpia de BD de pruebas (desechable)
docker compose run --rm --entrypoint "" odoo odoo \
  db --db_host db --db_port 5432 -r odoo -w $DB_PASS \
  init --force odoo_test

# 2. Instalación del módulo nuevo
docker compose run --rm odoo odoo \
  --stop-after-init -i <nombre_modulo> -d odoo_test

# 3. Ejecución de tests del módulo
docker compose run --rm odoo odoo \
  --test-enable --stop-after-init -d odoo_test \
  --test-tags /<nombre_modulo>
```

---

## Checklist de Verificación de Scaffold

1. ¿El módulo incluye **únicamente** los archivos y carpetas requeridos por el Task Contract actual?
2. ¿No existen carpetas vacías ni archivos `.keep`?
3. ¿`__manifest__.py` tiene `installable: True`, nombre legible en español y dependencias correctas?
4. ¿El orden en `data` respeta: seguridad primero, luego ACLs, luego vistas/datos?
5. ¿Todos los `__init__.py` importan los módulos Python reales existentes?
6. ¿El módulo se instala limpiamente en Docker sin errores?
