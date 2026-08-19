# Custom Addons — Módulos WMS/TMS/ERP

Directorio de módulos personalizados Odoo 19 para el proyecto WMS sobre ERP.

> Montado como `/mnt/extra-addons` dentro del contenedor Odoo.

---

## Convención de Nombres

| Prefijo | Dominio | Ejemplo |
|---|---|---|
| `wms_` | Warehouse Management System | `wms_core`, `wms_inventory`, `wms_work` |
| `tms_` | Transport Management System | `tms_core`, `tms_routing` |
| `erp_` | Extensiones ERP/integraciones | `erp_sync`, `erp_product_ext` |

## Estructura de un Módulo

```text
custom_addons/
└── wms_core/
    ├── __init__.py
    ├── __manifest__.py
    ├── models/
    │   ├── __init__.py
    │   └── ...
    ├── views/
    │   └── ...
    ├── security/
    │   ├── ir.model.access.csv
    │   └── ...
    ├── data/
    │   └── ...
    ├── tests/
    │   ├── __init__.py
    │   └── test_*.py
    └── README.md
```

## Reglas

1. **Un módulo = una responsabilidad de dominio** (ADR-001, ADR-002)
2. **No crear directorios vacíos**: cada módulo se crea cuando se necesita
3. **Dependencias explícitas**: en `__manifest__.py` → `depends`
4. **Autor**: nombre de la organización del proyecto
5. **Versión**: `19.0.1.0.0` (major Odoo . major . minor . patch . fix)
6. **Licencia**: `LGPL-3`

## Verificación de un Módulo

Cada módulo debe pasar esta secuencia antes de merge:

```bash
# 1. Install desde cero (odoo_test limpia)
docker compose run --rm --entrypoint "" odoo odoo \
  --db_host db --db_port 5432 -r odoo -w <pass> \
  db init --force odoo_test

docker compose run --rm --entrypoint "" odoo odoo \
  --db_host db --db_port 5432 -r odoo -w <pass> \
  module install <module_name> -d odoo_test

# 2. Upgrade (idempotencia)
docker compose run --rm --entrypoint "" odoo odoo \
  --db_host db --db_port 5432 -r odoo -w <pass> \
  module upgrade <module_name> -d odoo_test

# 3. Tests
docker compose run --rm --entrypoint "" odoo odoo \
  -c /etc/odoo/odoo.conf \
  --db_host db --db_port 5432 -r odoo -w <pass> \
  --test-enable --stop-after-init -d odoo_test
```

## Referencias

- [Odoo Module Scaffold Skill](../../.agents/skills/odoo-module-scaffold/SKILL.md)
- [ADR-001 a ADR-027](../docs/05-decisiones/01-adr.md)
- [Odoo Baseline Registry](../docs/03-plataforma/09-odoo-baseline-registry.md)
