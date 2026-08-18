# Rule Engine — Typed Policy Engine (v1.1)

> Motor de políticas tipadas que configura el comportamiento de los motores WMS sin cambios de código. Cada dominio define sus propios tipos de políticas con acciones explícitamente whitelisted.
>
> **v1.1**: Cambia de Rule Engine genérico a Typed Policy Engine. Elimina `safe_eval`. Acciones whitelisted por dominio (ADR-018).

---

## Contexto

### Cambio principal en v1.1

La v1.0 proponía un motor de reglas genérico donde cualquier condición podía ejecutar cualquier acción. Esto presenta riesgos:

| Riesgo | Descripción |
|---|---|
| **Complejidad prematura** | Construir un BPM/rule engine genérico antes de necesitarlo |
| **Seguridad** | `safe_eval` permite ejecución de código arbitrario |
| **Validación** | Reglas genéricas son difíciles de validar y simular |
| **Debugging** | Cuando algo falla, ¿qué regla causó el problema? |

> **ADR-018**: Rule Engine usa DSL tipada sin `safe_eval`.

---

## Typed Policy Engine

### Concepto

En lugar de un motor genérico `IF X THEN Y`, cada dominio define su **tipo de política** (*Policy Type*) con:

1. **Condiciones** específicas de ese dominio
2. **Acciones** explícitamente whitelisted para ese dominio
3. **Evaluación** determinista y tipada

### Modelo: `wms.policy`

| Campo | Significado |
|---|---|
| `name` | Nombre descriptivo |
| `policy_type` | Tipo: `PUTAWAY`, `ALLOCATION`, `REPLENISHMENT`, `QUEUE_ELIGIBILITY`, `WAVE_GROUPING` |
| `warehouse_id` | Bodega donde aplica (o todas) |
| `priority` | Orden de evaluación |
| `version` | Versión de la política |
| `active` | Activa/inactiva |
| `valid_from` / `valid_to` | Rango de vigencia |
| `condition_ids` | Lista de condiciones |
| `action_ids` | Lista de acciones |

---

## Políticas por Dominio

### Putaway Policy

**Condiciones disponibles** (whitelisted):

| Condición | Significado | Ejemplo |
|---|---|---|
| `PRODUCT_CATEGORY` | Categoría del producto | Alimentos, electrónica |
| `TEMPERATURE_CLASS` | Clase de temperatura | FROZEN, CHILLED |
| `HAZMAT_CLASS` | Clase hazmat | CLASS_3 |
| `ABC_CLASS` | Clasificación de rotación | A, B, C |
| `HU_TYPE` | Tipo de unidad de manejo | PALLET, CASE |
| `WEIGHT_RANGE` | Rango de peso | 0-500kg, 500-1200kg |
| `OWNER` | Propietario (3PL) | COMPANY-A |

**Acciones disponibles** (whitelisted):

| Acción | Significado |
|---|---|
| `INCLUDE_ZONE` | Incluir zona como candidata |
| `EXCLUDE_ZONE` | Excluir zona |
| `REQUIRE_STORAGE_TYPE` | Requerir tipo de almacenamiento |
| `REQUIRE_STORAGE_CATEGORY` | Requerir categoría de almacenamiento |
| `ADD_SCORE` | Agregar score a un candidato |
| `SET_CONSOLIDATION` | Preferir consolidación con mismo SKU/lote |
| `SET_PROXIMITY` | Preferir cercanía a zona de despacho |

### Allocation Policy

**Condiciones disponibles**:

| Condición | Significado |
|---|---|
| `PRODUCT_CATEGORY` | Categoría del producto |
| `CUSTOMER_ID` | Cliente específico |
| `ROUTE_ID` | Ruta de transporte |
| `ORDER_PRIORITY` | Prioridad del pedido |
| `SHELF_LIFE_REMAINING` | Vida útil restante |

**Acciones disponibles**:

| Acción | Significado |
|---|---|
| `SET_REMOVAL_STRATEGY` | FIFO, FEFO, LIFO, CLOSEST |
| `PREFER_FULL_PALLET` | Preferir pallets completos |
| `PREFER_FULL_CASE` | Preferir cajas completas |
| `MINIMIZE_FRAGMENTATION` | Minimizar ubicaciones distintas |
| `REQUIRE_LOT_CERTIFICATION` | Solo lotes certificados |

### Queue Eligibility Policy

**Condiciones disponibles**:

| Condición | Significado |
|---|---|
| `RESOURCE_ZONE` | Zona del operador |
| `RESOURCE_CERTIFICATION` | Certificación requerida |
| `EQUIPMENT_TYPE` | Tipo de equipo |
| `WORK_TYPE` | Tipo de trabajo |
| `WORK_CLASS` | Clase de trabajo |

**Acciones disponibles**:

| Acción | Significado |
|---|---|
| `ALLOW` | Permitir asignación |
| `DENY` | Denegar asignación |
| `ADD_PRIORITY_SCORE` | Modificar prioridad |

---

## Evaluación

### Modo: First-Match (por defecto)

```text
Policies (ordenadas por prioridad):
  1. IF TEMPERATURE=FROZEN AND HU=PALLET THEN INCLUDE_ZONE=FREEZER-A, SET_CONSOLIDATION=YES
  2. IF HAZMAT!=NONE THEN INCLUDE_ZONE=HAZMAT, EXCLUDE_ZONE=MAIN
  3. DEFAULT: INCLUDE_ZONE=MAIN
```

Se evalúa en orden. La primera que matchea se aplica. Si ninguna matchea, se usa el default.

### Modo: Score-Based

```text
Para cada candidato, sumar scores de todas las policies que aplican:
  Zone match:        +100
  Same SKU:          +50
  Same Lot:          +30
  Closest location:  +20
  ABC preference:    +10
```

El candidato con mayor score gana.

---

## Lo que NO hace el Policy Engine

| Funcionalidad | ¿La hace? | Por qué |
|---|---|---|
| Ejecutar código arbitrario | ❌ | `safe_eval` prohibido |
| Modificar campos de modelos | ❌ | Solo las acciones whitelisted |
| Crear registros de otros modelos | ❌ | No es un workflow engine |
| Evaluar expresiones Python | ❌ | DSL tipada, no código |

---

## Características Mantenidas de v1.0

Las siguientes características de la v1.0 se mantienen:

| Característica | Estado |
|---|---|
| Versionamiento de políticas | ✅ Mantenido |
| Auditoría de cambios | ✅ Mantenido |
| Simulación (dry-run) | ✅ Mantenido |
| Activación/desactivación sin borrar | ✅ Mantenido |
| Override por bodega | ✅ Mantenido |

---

## Modelos

| Modelo | Propósito |
|---|---|
| `wms.policy` | Política con tipo, condiciones y acciones |
| `wms.policy.condition` | Condición tipada de una política |
| `wms.policy.action` | Acción tipada de una política |
| `wms.policy.type` | Catálogo de tipos de política por dominio |

---

*Documento corregido en v1.1. Cambio principal: de Rule Engine genérico a Typed Policy Engine (ADR-018).*
