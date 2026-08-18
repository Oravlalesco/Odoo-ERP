# Exception Engine — Motor de Excepciones Operacionales

> Un WMS industrial no puede diseñarse solamente para el "happy path". Cada excepción tiene un tratamiento definido que protege el inventario y mantiene la operación en movimiento.

---

## Contexto

En la operación real de un almacén, los problemas son frecuentes: ubicaciones llenas, productos dañados, escáneres que fallan, lotes equivocados. Sin un motor de excepciones, cada problema detiene al operador indefinidamente o, peor, genera acciones incorrectas que corrompen el inventario.

---

## Tipos de Excepciones

| Excepción | En inglés | Significado |
|---|---|---|
| **Faltante** | SHORT | El operador encuentra menos stock del esperado en la ubicación |
| **Dañado** | DAMAGED | Mercadería con daño visible |
| **Ubicación llena** | LOCATION FULL | La ubicación destino no tiene espacio |
| **SKU no encontrado** | SKU NOT FOUND | El producto no está donde el sistema indica |
| **HU no encontrada** | HU NOT FOUND | El pallet o caja no está donde debería |
| **Lote incorrecto** | WRONG LOT | El lote encontrado no coincide con el esperado |
| **Serial incorrecto** | WRONG SERIAL | El número de serie no coincide |
| **Ubicación incorrecta** | WRONG LOCATION | El operador está en una ubicación diferente a la indicada |
| **Fallo de equipo** | EQUIPMENT FAILURE | Montacarga o escáner no funciona |
| **Retención de calidad** | QUALITY HOLD | El inventario fue bloqueado por calidad durante la operación |
| **Error de red** | NETWORK ERROR | Pérdida de conectividad del dispositivo RF |
| **Sobre-recepción** | OVER RECEIPT | Se recibe más mercadería de la esperada |
| **Sub-recepción** | UNDER RECEIPT | Se recibe menos mercadería de la esperada |

---

## Tratamiento de Cada Excepción

Cada excepción debe definir:

| Aspecto | En inglés | Pregunta |
|---|---|---|
| **Quién puede reportarla** | Who can raise? | ¿Solo operador? ¿También supervisor? |
| **Qué pasa con el Work** | What happens to Work? | ¿Se pausa? ¿Se cancela? ¿Se reasigna? |
| **Qué pasa con el stock** | What happens to stock? | ¿Se bloquea? ¿Se ajusta? ¿Se libera la reserva? |
| **¿Necesita supervisor?** | Supervisor needed? | ¿Puede el operador resolver solo o necesita autorización? |
| **¿Ubicación alternativa?** | Alternative location? | ¿El sistema sugiere otra ubicación? |
| **¿Evento de auditoría?** | Audit event? | ¿Se registra en el ledger? (generalmente sí) |

### Ejemplo: Short Pick

```text
Excepción: SHORT
Operador reporta: "Solo hay 18 de los 24 esperados"

→ Work: Se pausa
→ Stock: Se marca la ubicación para conteo
→ Supervisor: Notificado automáticamente
→ Alternativa: Sistema busca otra ubicación con stock del mismo SKU+Lote
→ Decisión del supervisor:
  a) Aceptar pick parcial (18) y generar nuevo work para el faltante
  b) Reasignar a otra ubicación
  c) Cancelar la línea del pedido
→ Audit: Evento registrado con operador, ubicación, qty esperada, qty real
```

---

*Documento derivado de la sección 35 del [Plan Maestro](../plan.md).*
