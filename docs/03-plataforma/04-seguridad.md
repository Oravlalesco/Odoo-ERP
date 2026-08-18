# Seguridad — RBAC, Roles y Scopes

> Separación de acceso basada en roles operacionales y scopes por bodega/zona. No dependeremos únicamente de ocultar menús.

---

## Contexto

**RBAC (Role-Based Access Control)** — Control de Acceso Basado en Roles — es un modelo de seguridad donde los permisos se asignan a roles, y los roles se asignan a usuarios. Un almacén industrial tiene distintos tipos de usuarios con necesidades de acceso muy diferentes.

---

## Roles

| Rol | En inglés | Acceso |
|---|---|---|
| **Administrador** | Administrator | Configuración completa del sistema |
| **Gerente de Almacén** | Warehouse Manager | Gestión operacional de una o más bodegas |
| **Supervisor** | Supervisor | Gestión de zona/turno, resolución de excepciones |
| **Planificador** | Planner | Waves, allocation, release de pedidos |
| **Operador** | Operator | Ejecución de trabajo vía RF |
| **Controller de Inventario** | Inventory Controller | Conteos, ajustes, precisión |
| **Calidad** | Quality | Inspecciones, liberaciones, retenciones |
| **Integrador** | Integrator | Acceso API para sistemas externos |
| **Auditor** | Auditor | Consulta de logs y eventos (solo lectura) |

---

## Scopes (Alcances)

Además del rol, cada usuario tiene un **scope** (alcance) que limita a qué datos puede acceder:

| Scope | En inglés | Significado |
|---|---|---|
| **Compañía** | Company | Acceso a datos de una empresa específica |
| **Bodega** | Warehouse | Acceso a una o más bodegas |
| **Zona** | Zone | Acceso a zonas específicas dentro de una bodega |
| **Actividad** | Activity | Acceso a tipos de actividad específicos (solo picking, solo putaway) |

### Ejemplo

```text
Usuario: Juan García
Rol: Operator
Scope: Warehouse=SCL01, Zone=A+B, Activity=Picking
→ Solo puede ejecutar trabajo de picking en zonas A y B de la bodega SCL01
```

**No dependeremos únicamente de ocultar menús.** Los permisos se aplican a nivel de datos (record rules), API y lógica de negocio.

---

*Documento derivado de la sección 42 del [Plan Maestro](../plan.md).*
