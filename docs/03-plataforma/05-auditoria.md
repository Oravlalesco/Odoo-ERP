# Auditoría — Trazabilidad de Acciones Críticas

> Cada acción crítica registra: quién, desde dónde, cuándo, qué cambió, en el contexto de qué trabajo, con un correlation_id para rastreo completo.

---

## Contexto

**Audit** (Auditoría) es el registro inmutable de toda acción crítica que ocurre en el sistema. En un WMS industrial, la trazabilidad completa no es opcional — es requisito para cumplimiento normativo, resolución de problemas e investigación de discrepancias.

---

## Campos del Registro de Auditoría

Cada acción crítica registra:

| Campo | En inglés | Significado |
|---|---|---|
| **Operador** | Operator | Quién ejecutó la acción |
| **Dispositivo** | Device | Desde qué terminal RF o estación |
| **Timestamp** | Timestamp | Fecha y hora exacta con resolución de milisegundos |
| **Bodega** | Warehouse | En qué bodega ocurrió |
| **Trabajo** | Work | Work asociado (si aplica) |
| **Origen** | Source | Ubicación o estado de origen |
| **Destino** | Destination | Ubicación o estado de destino |
| **Antes** | Before | Estado/cantidad antes de la acción |
| **Después** | After | Estado/cantidad después de la acción |
| **Correlation ID** | Correlation ID | Identificador que agrupa eventos relacionados de un mismo flujo |

### Ejemplo

```text
17:14:02.341
OPERATOR 129
RF 24
WORK 98933

PICK

SKU X
LOT L04

FROM A03
QTY 24

correlation_id: flow-4521-pick-003
```

Este registro permite responder:
- ¿Quién movió el SKU X del lote L04?
- ¿A qué hora?
- ¿Desde qué dispositivo?
- ¿En el contexto de qué trabajo?
- ¿Qué más pasó en ese mismo flujo? (buscar por correlation_id)

---

*Documento derivado de la sección 43 del [Plan Maestro](../plan.md).*
