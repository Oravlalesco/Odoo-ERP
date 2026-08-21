# Handling Units — Industrialización de `stock.package` (v1.2)

> Odoo 19 ya posee jerarquía de paquetes, dimensiones, SSCC y peso. No reconstruimos esa base. Industrializamos `stock.package` agregando semántica WMS: ciclo de vida, operaciones, clasificación operacional y trazabilidad.
>
> **v1.2**: Confirmado `stock.package` como nombre correcto (`_name = 'stock.package'` en Odoo 19). La clase Python es `StockPackage`.

---

## Contexto

### Cambios principales

La documentación v1.0 proponía construir HU "sobre el paquete básico de Odoo".

**Confirmación v1.2**:

1. El modelo real en Odoo 19 es **`stock.package`** (clase Python `StockPackage`, `_name = 'stock.package'`)
2. Odoo 19 ya posee **mucho más** de lo que documentábamos: jerarquía, dimensiones, peso, tipos de paquete con capacidades

> **ADR-013**: `stock.package` es la base de Handling Units. No crearemos un modelo de HU separado.

---

## Lo que Odoo 19 YA posee

### `stock.package`

| Campo | Significado | Ya existe |
|---|---|---|
| `name` | Referencia del paquete (puede ser SSCC) | ✅ |
| `package_type_id` | Tipo de paquete (dimensiones, peso, etc.) | ✅ |
| `parent_package_id` | Paquete padre (pack-in-pack) — jerarquía | ✅ |
| `child_package_ids` | Paquetes hijos (relación inversa) | ✅ |
| `location_id` | Ubicación actual del paquete | ✅ |
| `owner_id` | Propietario del paquete | ✅ |
| `shipping_weight` | Peso de envío real | ✅ |
| `pack_date` | Fecha de empaque | ✅ |
| `quant_ids` | Contenido: quants dentro del paquete | ✅ |
| `valid_sscc` | Validador algorítmico GS1 SSCC-18 sobre `name` | ✅ |

### `stock.package.type`

| Campo | Significado | Ya existe |
|---|---|---|
| `name` | Nombre del tipo (ej: "Euro Pallet") | ✅ |
| `height`, `width`, `packaging_length` | Dimensiones físicas | ✅ |
| `base_weight` | Peso tara (peso del contenedor vacío) | ✅ |
| `max_weight` | Peso máximo permitido | ✅ |
| `barcode` | Código de barras del tipo de paquete | ✅ |
| Storage capacities | Capacidades de almacenamiento por categoría | ✅ |

**Conclusión**: No necesitamos reconstruir jerarquía, dimensiones, tipo de paquete ni peso. Esto reduce significativamente el esfuerzo de la Fase HU.

---

## Lo que el WMS agrega

### Extensiones a `stock.package`

| Campo | En inglés | Estado | Significado |
|---|---|---|---|
| `hu_state` | HU State | ✅ HU-002 | Estado del ciclo de vida WMS: `EMPTY`, `OPEN`, `CLOSED`, `IN_TRANSIT`, `SHIPPED`, `RETURNED`, `DISPOSED` (False = no inicializado) |
| `hu_class` | HU Class | ✅ HU-002 | Clasificación operacional: `PALLET`, `CASE`, `TOTE`, `CONTAINER`, `MIXED` (False = no asignada) |
| `name` / `valid_sscc` | SSCC Reference | ✅ Odoo Nativo | Se reutiliza `stock.package.name` + `valid_sscc` nativos de Odoo 19; **no se crea un campo `sscc` duplicado** |
| `seal_number` | Seal Number | ⏸ Diferido | Número de sello de seguridad (para transporte) |
| `gtin` | GTIN | ⏸ Diferido | Global Trade Item Number del contenedor |
| `label_state` | Label State | ⏸ Diferido | Estado de la etiqueta GS1: `PENDING`, `PRINTED`, `APPLIED`, `DAMAGED` |
| `current_work_id` | Current Work | ⏸ Diferido | Work activo asociado a esta HU |
| `last_work_id` | Last Work | ⏸ Diferido | Último Work completado sobre esta HU |
| `weight_gross` | Gross Weight | ⏸ Diferido | Peso bruto real (tara + contenido, si se justifica frente a `shipping_weight`) |
| `weight_net` | Net Weight | ⏸ Diferido | Peso neto (solo contenido) |

> [!NOTE]
> `stock.package.history` ya existe en Odoo 19 nativo y se reutiliza para la trazabilidad de movimientos físicos de paquetes. Un futuro modelo `wms.hu.operation` sólo registrará operaciones de semántica WMS adicional (pack/unpack/split/merge).

### Ciclo de Vida de la HU

```mermaid
stateDiagram-v2
    [*] --> EMPTY: Crear HU
    EMPTY --> OPEN: Pack (agregar contenido)
    OPEN --> OPEN: Pack más / Unpack parcial
    OPEN --> CLOSED: Cerrar y sellar
    CLOSED --> IN_TRANSIT: Cargar en transporte
    IN_TRANSIT --> SHIPPED: Confirmar despacho
    SHIPPED --> RETURNED: Devolución
    RETURNED --> OPEN: Reabrir para inspección
    OPEN --> EMPTY: Unpack total
    EMPTY --> DISPOSED: Dar de baja
    CLOSED --> OPEN: Reabrir
```

### Operaciones sobre HU

| Operación | En inglés | Significado | Genera Work |
|---|---|---|---|
| **Crear** | Create | Registrar una HU nueva en el sistema | No |
| **Empacar** | Pack | Agregar contenido a la HU | Sí |
| **Desempacar** | Unpack | Retirar contenido de la HU | Sí |
| **Dividir** | Split | Dividir una HU en dos o más | Sí |
| **Consolidar** | Merge | Combinar contenido de dos HU en una | Sí |
| **Cerrar** | Close | Sellar, pesar, etiquetar | Sí |
| **Reabrir** | Reopen | Abrir HU sellada para inspección o corrección | Sí (con autorización) |
| **Mover** | Move | Mover la HU completa a otra ubicación | Sí |
| **Disponer** | Dispose | Dar de baja la HU (destruir, reciclar) | No |

La trazabilidad de movimientos físicos de paquetes ya está cubierta de forma nativa por `stock.package.history` en Odoo 19. Para registrar eventos semánticos WMS adicionales (pack, unpack, split, merge), un futuro modelo `wms.hu.operation` (diferido) podrá capturar:

### HU Operation History (`wms.hu.operation` — ⏸ Diferido)

| Campo | Significado |
|---|---|
| `package_id` | HU afectada |
| `operation_type` | Tipo de operación |
| `operator_id` | Quién ejecutó |
| `device_id` | Desde qué dispositivo |
| `timestamp` | Cuándo |
| `work_id` | Work asociado |
| `details` | Detalles específicos (ej: qué quants se agregaron/removieron) |
| `correlation_id` | ID de correlación |

---

## SSCC — Serial Shipping Container Code

### ¿Qué es?

**SSCC** (Serial Shipping Container Code) es un identificador único global de 18 dígitos asignado a cada unidad logística (pallet, caja, contenedor) siguiendo el estándar GS1.

```text
(00) 1 7601234 000000001 2
 AI  E  GCP     Serial   Check
```

| Componente | Significado |
|---|---|
| AI `(00)` | Application Identifier: indica que es un SSCC |
| Extension digit | Dígito de extensión (aumenta capacidad de numeración) |
| GCP | Global Company Prefix (identificador de la empresa) |
| Serial | Número secuencial único |
| Check digit | Dígito verificador |

### Implementación

Odoo 19 tiene un campo `valid_sscc` que valida si `name` cumple el algoritmo checksum GS1 SSCC-18, y `name` se utiliza directamente como la referencia SSCC.

En **HU-003A**, se implementa el modelo asignador `wms.sscc.sequence`, que configura y consume un contador transaccional `ir.sequence` estándar para producir identificadores SSCC-18 conformes a GS1 (`extension_digit (1) + GCP (4..12) + serial (12..4) + check_digit (1)`). La asignación de estos códigos a paquetes (`package.name`) y el motor de etiquetas logísticas se implementan en **HU-003B**.

---

## Relación con Odoo

### Modelos Reutilizados

| Modelo | Qué reutilizamos |
|---|---|
| `stock.package` | **Base completa** de HU: jerarquía, ubicación, propietario, contenido, referencia `name`, validación `valid_sscc` |
| `stock.package.type` | **Base completa** de tipo de paquete: dimensiones (`packaging_length`, `width`, `height`), peso, capacidades |
| `stock.package.history` | Historial nativo de movimientos y traslados físicos de paquetes |
| `ir.sequence` | Contador transaccional y atómico consumido por `wms.sscc.sequence` |

### Modelos Extendidos

| Modelo | Extensión |
|---|---|
| `stock.package` | **Implementados en HU-002**: `hu_state`, `hu_class`. **Diferidos**: `seal_number`, `gtin`, `label_state`, `current_work_id`, `last_work_id`, `weight_gross`, `weight_net`. (Nota: no se crea campo `sscc`; se reutiliza `name` + `valid_sscc`). |

### Modelos Nuevos

| Modelo | Estado | Propósito |
|---|---|---|
| `wms.sscc.sequence` | ✅ HU-003A | Asignador de secuencias GS1 SSCC-18 con GCP configurable y contador `ir.sequence` |
| `wms.hu.operation` | ⏸ Diferido | Historial de operaciones semánticas WMS sobre HU (movimientos físicos cubiertos por `stock.package.history`) |

> **Nota**: Ya **no** se propone `wms.handling.unit` como modelo independiente. La HU ES `stock.package` extendido (ADR-013).

---

## Dependencias

```mermaid
graph LR
    WM["01 Warehouse Master"] --> HU["03 Handling Units"]
    HU --> INV["02 Inventory"]
    HU --> WE["04 Work Execution"]
    HU --> PACK["11 Packing & Shipping"]
    HU --> IN["07 Inbound"]
```

---

*Documento corregido en v1.2. v1.0→v1.1: documentados campos existentes, eliminado modelo HU separado. v1.1→v1.2: confirmado `stock.package` como nombre correcto (ADR-013).*
