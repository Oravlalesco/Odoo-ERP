# RF / WMS Mobile — Cliente Móvil para Operadores

> Interface propia de radiofrecuencia diseñada para operación dirigida en piso. Pantallas extremadamente simples, comunicación vía HTTPS y conexión directa al Work Engine.

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
| **Offline-capable** | Funcionar con conectividad intermitente |

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

## Referencia

Dynamics 365 y SAP EWM tienen interfaces mobile/RF explícitamente centradas en ejecución dirigida de trabajo, validando que este enfoque es estándar en la industria.

---

*Documento derivado de la sección 34 del [Plan Maestro](../plan.md).*
