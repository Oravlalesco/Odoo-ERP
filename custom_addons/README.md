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
# 0. Reset de odoo_test (DESECHABLE — siempre --force)
#
#    ⚠️  db init requiere --entrypoint "" porque el entrypoint oficial
#    de odoo:19.0 inyecta --db_host/--db_port/--db_user/--db_password
#    DESPUÉS del comando, colisionando con los subcomandos posicionales
#    de Odoo 19 (db, module). Verificado durante BOOT-005.
#
docker compose run --rm --entrypoint "" odoo odoo \
  db --db_host db --db_port 5432 -r odoo -w <pass> \
  init --force odoo_test

# 1. Install (entrypoint normal — flags de conexión se inyectan correctamente)
#
#    Nota: Odoo 19 CLI documenta `odoo module install`, pero ese subcomando
#    presenta el mismo conflicto con el entrypoint Docker de nuestra imagen.
#    Usamos el flag -i del comando server, validado operacionalmente.
#
docker compose run --rm odoo odoo \
  --stop-after-init -i <module_name> -d odoo_test

# 2. Upgrade (idempotencia)
#
#    Misma consideración que install: usamos -u en lugar de `module upgrade`.
#
docker compose run --rm odoo odoo \
  --stop-after-init -u <module_name> -d odoo_test

# 3. Tests
docker compose run --rm odoo odoo \
  --test-enable --stop-after-init -d odoo_test \
  --test-tags /<module_name>
```

## Referencias

- [Odoo Module Scaffold Skill](../../.agents/skills/odoo-module-scaffold/SKILL.md)
- [ADR-001 a ADR-027](../docs/05-decisiones/01-adr.md)
- [Odoo Baseline Registry](../docs/03-plataforma/09-odoo-baseline-registry.md)
