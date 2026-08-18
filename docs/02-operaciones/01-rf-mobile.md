# RF / WMS Mobile — Cliente Móvil para Operadores (v1.1)

> Interface propia de radiofrecuencia diseñada para operación dirigida en piso. Pantallas extremadamente simples, comunicación vía HTTPS y conexión directa al Work Engine.
>
> **v1.1**: Detalla RF Offline Protocol, agrega command journal, corrige "offline-capable" de bullet point a especificación técnica (ADR-017).

---

## Contexto

### ¿Por qué construir nuestro propio RF?

**RF (Radio Frequency)** se refiere a los terminales portátiles que los operadores usan en el piso del almacén. Son dispositivos resistentes (*rugged*) con pantalla, teclado y escáner de código de barras.

Odoo Enterprise incluye `stock_barcode` para escaneo, pero:
- No está disponible en **Community** (nuestro framework es Community)
- No está diseñado para **directed work** (trabajo dirigido)
- Usa las vistas normales del backend, que son lentas y complejas para operación de piso

Necesitamos un **cliente RF propio**, ultraligero, diseñado específicamente para ejecución dirigida de trabajo.

---

## Arquitectura

```text
RF Device (Dispositivo RF)
   │
 HTTPS
   │
WMS API/RF (API dedicada para RF)
   │
Work Engine (Motor de trabajo)
   │
Odoo ORM (Base de datos)
```

| Capa | Significado |
|---|---|
| **RF Device** | Terminal físico con Android/Linux, escáner láser, pantalla pequeña |
| **HTTPS** | Comunicación encriptada entre el dispositivo y el servidor |
| **WMS API/RF** | Endpoint API específico para operaciones RF — rápido, mínimo payload |
| **Work Engine** | Motor que gestiona el ciclo de vida del trabajo |
| **Odoo ORM** | Capa de acceso a datos de Odoo |

---

## Principios de Diseño

| Principio | Significado |
|---|---|
| **Pantallas simples** | Máximo 5-6 líneas de información. Sin decoración innecesaria |
| **Una acción por pantalla** | Cada pantalla pide exactamente una acción del operador |
| **Scan-driven** | El operador avanza escaneando, no navegando menús |
| **Sin decisiones** | El sistema decide, el operador ejecuta |
| **Tolerante a errores** | Si el operador escanea algo incorrecto, se muestra un error claro y puede reintentar |

---

## Ejemplo de Flujo RF: Putaway

### Pantalla 1: Asignación

```text
PUTAWAY

FROM
REC-04                           ← Ubicación de origen

SCAN PALLET
[________________]               ← Operador escanea SSCC del pallet
```

### Pantalla 2: Destino

```text
DESTINATION

A03-R02-L05                      ← Ubicación destino calculada por Putaway Engine

SCAN LOCATION
[________________]               ← Operador escanea etiqueta de la ubicación
```

### Pantalla 3: Confirmación

```text
PUTAWAY CONFIRMED ✓

NEXT WORK?
[F1] YES    [F4] MENU
```

---

## Ejemplo de Flujo RF: Picking

### Pantalla 1: Trabajo asignado

```text
PICK

ORDER: 4521
WAVE: W-105

LOCATION: A03-R02-L01

SCAN LOCATION
[________________]
```

### Pantalla 2: Producto

```text
PICK

SKU-A
LOT: L00231
QTY: 24

SCAN PRODUCT
[________________]
```

### Pantalla 3: Cantidad

```text
CONFIRM QTY

EXPECTED: 24

ACTUAL:
[________________]               ← Confirma o reporta short pick

[F1] CONFIRM    [F3] SHORT
```

---

## RF Offline Protocol (v1.1)

> **ADR-017**: RF offline solo ejecuta Work previamente asignado.

### ¿Qué significa "offline"?

No significa que el operador pueda trabajar indefinidamente sin conexión. Significa que ante una **interrupción temporal de conectividad** (Wi-Fi inestable, zona muerta del almacén), el operador puede continuar ciertos pasos del Work que ya tiene asignado.

### Lo que SÍ se permite offline

| Acción | Offline | Razón |
|---|---|---|
| Continuar Work ya asignado | ✅ | El operador ya tiene la instrucción |
| Ejecutar pasos de scan/confirm | ✅ | Se registran localmente |
| Reportar excepciones | ✅ | Se encolan para sync |

### Lo que NO se permite offline

| Acción | Offline | Razón |
|---|---|---|
| Solicitar nuevo Work | ❌ | Requiere `FOR UPDATE SKIP LOCKED` — imposible sin DB |
| Allocation de inventario | ❌ | Requiere transacción atómica sobre quants |
| Aprobar excepciones | ❌ | Requiere validación del supervisor |

### Command Journal

Cada acción del operador se registra localmente en un **command journal** (diario de comandos) en el dispositivo:

| Campo | Significado |
|---|---|
| `command_id` | UUID único del comando |
| `device_id` | Identificador del dispositivo RF |
| `work_id` | Work al que pertenece |
| `work_version` | Versión del assignment (para detectar reasignaciones) |
| `sequence` | Número secuencial del comando |
| `timestamp` | Timestamp local del dispositivo |
| `command_type` | Tipo: `SCAN_LOCATION`, `SCAN_PRODUCT`, `CONFIRM_PICK`, `CONFIRM_PUT`, `REPORT_SHORT`, `REPORT_DAMAGE` |
| `payload` | Datos del comando (barcode escaneado, cantidad, etc.) |

### Ejemplo: Operador pierde Wi-Fi durante picking

```text
17:15:02  ONLINE   Confirm pick line 1 → enviado al server ✓
17:15:15  *** Wi-Fi lost ***
17:15:30  OFFLINE  Scan location A03-R02-L02 → journal local
17:15:45  OFFLINE  Scan product SKU-B → journal local
17:15:55  OFFLINE  Confirm pick qty=12 → journal local
17:16:10  *** Wi-Fi restored ***
17:16:11  SYNC     Replay command journal:
                     command_1: SCAN_LOCATION → OK
                     command_2: SCAN_PRODUCT → OK
                     command_3: CONFIRM_PICK → OK (idempotent)
```

### Replay Idempotente

El replay al reconectar es **idempotente**:

```text
Server recibe: CONFIRM_PICK(command_id=uuid-123, work_id=10592, ...)

1. ¿Este command_id ya fue procesado?
   → Sí: retornar OK sin reprocesar
   → No: ejecutar normalmente
```

### Conflicto: Work fue reasignado

```text
Operador A pierde Wi-Fi, sigue trabajando offline
Server: lease expira → Work RECLAIMABLE → READY
Operador B toma el Work → assignment_version=2

Operador A reconecta, intenta replay:
  work_version en journal = 1
  work_version actual = 2
  → CONFLICT: Work fue reasignado
  → Descartar journal, notificar operador
```

### Límites del Modo Offline

| Límite | Valor | Razón |
|---|---|---|
| **Duración máxima** | 10 minutos (configurable) | Después, el lease expira y el Work puede ser reasignado |
| **Comandos máximos** | 50 | Prevenir journals enormes |
| **Tipos permitidos** | Solo ejecución | No planning ni allocation |

---

## Referencia

Dynamics 365 y SAP EWM tienen interfaces mobile/RF explícitamente centradas en ejecución dirigida de trabajo, validando que este enfoque es estándar en la industria.

---

*Documento derivado de la sección 34 del [Plan Maestro](../plan.md). Corregido en v1.1: RF Offline Protocol (ADR-017), command journal, replay idempotente.*
