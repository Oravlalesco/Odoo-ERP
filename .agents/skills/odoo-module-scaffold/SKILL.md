---
name: odoo-module-scaffold
description: >-
  Usar este skill cuando el usuario pida crear un nuevo módulo (addon) de Odoo,
  generar la estructura de directorios de un módulo, o inicializar un addon
  personalizado en custom_addons/. También se activa cuando se pregunte cómo
  organizar un nuevo módulo WMS, TMS o ERP.
---

# Scaffold de Módulos Odoo 19

Guía paso a paso para crear módulos (addons) de Odoo 19 en este proyecto ERP-WMS-TMS.

---

## Estructura Obligatoria de un Módulo

Cada módulo en `custom_addons/` debe seguir esta estructura:

```text
custom_addons/<nombre_modulo>/
├── __manifest__.py           # Obligatorio: metadata del módulo
├── __init__.py               # Obligatorio: imports de Python
├── models/
│   ├── __init__.py
│   └── <modelo>.py           # Modelos de datos
├── views/
│   └── <modelo>_views.xml    # Vistas (form, tree, kanban, search)
├── security/
│   ├── ir.model.access.csv   # Permisos de acceso (ACL)
│   └── security.xml          # Grupos y record rules
├── data/
│   └── <datos_iniciales>.xml # Datos de configuración inicial
├── demo/
│   └── demo.xml              # Datos de demostración
├── wizards/
│   ├── __init__.py
│   └── <wizard>.py           # TransientModels (wizards)
├── reports/
│   └── <reporte>.xml         # Templates de reportes QWeb
├── static/
│   └── description/
│       └── icon.png          # Ícono del módulo (opcional)
├── i18n/
│   └── es.po                 # Traducciones
├── controllers/
│   ├── __init__.py
│   └── main.py               # Controladores HTTP/JSON-RPC
└── tests/
    ├── __init__.py
    └── test_<modelo>.py      # Tests unitarios
```

## Template de `__manifest__.py`

```python
{
    'name': 'WMS Work Engine',                    # Nombre legible en español
    'version': '19.0.1.0.0',                      # Formato: odoo_version.major.minor.patch
    'category': 'Inventory/WMS',                   # Categoría funcional
    'summary': 'Motor de trabajo dirigido WMS',    # Resumen corto en español
    'description': """
Motor de Trabajo Dirigido (Directed Work Engine)
=================================================

Transforma necesidades logísticas en unidades de trabajo ejecutables
y las distribuye a través de colas a los recursos disponibles.
    """,
    'author': 'Tu Empresa',
    'website': 'https://tu-empresa.com',
    'license': 'LGPL-3',
    'depends': [
        'stock',                                   # Dependencias de Odoo
        'wms_warehouse_master',                    # Dependencias de módulos WMS propios
    ],
    'data': [
        'security/security.xml',                   # Primero: grupos de seguridad
        'security/ir.model.access.csv',            # Segundo: ACLs
        'views/work_views.xml',                    # Después: vistas
        'data/work_type_data.xml',                 # Último: datos iniciales
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,                           # True si es un módulo principal con menú propio
    'auto_install': False,
}
```

## Convenciones de Nomenclatura

| Elemento | Convención | Ejemplo |
|---|---|---|
| Directorio del módulo | `snake_case` con prefijo | `wms_work_engine` |
| Nombre técnico (`_name`) | Puntos como separador, prefijo `wms.` / `tms.` | `wms.work`, `wms.work.line` |
| Nombre de tabla SQL | Odoo genera automáticamente: puntos → underscores | `wms_work`, `wms_work_line` |
| Archivos Python de modelos | `snake_case` sin prefijo | `work.py`, `work_line.py` |
| Archivos XML de vistas | `<modelo>_views.xml` | `work_views.xml` |
| `xml_id` de vistas | `<modulo>.<modelo>_view_<tipo>` | `wms_work_engine.work_view_form` |
| `xml_id` de acciones | `<modulo>.action_<modelo>` | `wms_work_engine.action_work` |
| `xml_id` de menús | `<modulo>.menu_<nombre>` | `wms_work_engine.menu_work_root` |
| Campos | `snake_case` en inglés | `assigned_resource_id`, `lease_expires_at` |

## `__init__.py` del Módulo

```python
from . import models
from . import wizards      # Solo si tiene wizards
from . import controllers  # Solo si tiene controllers
```

## `models/__init__.py`

```python
from . import work
from . import work_line
from . import work_type
```

## Pasos para Crear un Módulo Nuevo

1. **Crear directorio** en `custom_addons/<nombre_modulo>/`
2. **Crear `__manifest__.py`** con las dependencias correctas
3. **Crear `__init__.py`** raíz y en cada subdirectorio con archivos Python
4. **Crear modelos** en `models/`
5. **Crear vistas** en `views/`
6. **Crear seguridad** en `security/` (ACL + grupos)
7. **Crear tests** en `tests/`
8. **Instalar el módulo**:

### Instalar/Actualizar vía Docker Compose

```bash
# Instalar módulo nuevo
docker compose exec odoo odoo -i wms_work_engine -d odoo_production --stop-after-init

# Actualizar módulo existente
docker compose exec odoo odoo -u wms_work_engine -d odoo_production --stop-after-init
```

### Instalar/Actualizar vía Kubernetes

```bash
ODOO_POD=$(kubectl get pods -n odoo -l app.kubernetes.io/name=odoo -o jsonpath="{.items[0].metadata.name}")

# Instalar
kubectl exec -it $ODOO_POD -n odoo -- odoo -i wms_work_engine -d odoo_production --stop-after-init

# Actualizar
kubectl exec -it $ODOO_POD -n odoo -- odoo -u wms_work_engine -d odoo_production --stop-after-init
```

## Orden de Declaración de Datos en `__manifest__.py`

El orden importa porque Odoo procesa los archivos secuencialmente:

1. `security/security.xml` — Grupos de seguridad primero
2. `security/ir.model.access.csv` — ACLs que referencian los grupos
3. `data/` — Datos de configuración que pueden requerir ACLs
4. `views/` — Vistas que pueden referenciar grupos para visibilidad
5. `reports/` — Reportes al final

## Verificación

Después de crear un módulo:

1. ¿`__manifest__.py` tiene `installable: True`?
2. ¿Todas las dependencias están listadas en `depends`?
3. ¿Todos los archivos `.xml` y `.csv` están listados en `data`?
4. ¿Todos los `__init__.py` importan los archivos Python correctos?
5. ¿El módulo se instala sin errores? → `docker compose exec odoo odoo -i <modulo> -d <db> --stop-after-init`
