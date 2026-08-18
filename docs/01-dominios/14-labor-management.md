# Labor Management — Gestión de Productividad

> Medición y análisis de la productividad operativa del almacén, basada en datos reales de ejecución de trabajo.

---

## Contexto

Como el WMS dirige todo el trabajo (Work Engine), automáticamente captura datos reales de cada tarea: cuándo se asignó, cuándo empezó, cuándo terminó, dónde hubo espera, qué excepciones ocurrieron. Esto permite calcular métricas de productividad sin sistemas adicionales.

> **Nota importante**: Labor Management no debe convertirse en vigilancia individual indiscriminada. Operacionalmente sirve para planificación de capacidad, detección de cuellos de botella y mejora continua.

---

## Datos Capturados

| Dato | En inglés | Significado |
|---|---|---|
| **Trabajo asignado** | Work Assigned | Momento en que se asignó el work al operador |
| **Inicio** | Start | Momento en que el operador comenzó a ejecutar |
| **Fin** | Finish | Momento de completación |
| **Viaje** | Travel | Tiempo de desplazamiento entre ubicaciones |
| **Espera** | Wait | Tiempo en que el operador esperó por trabajo |
| **Excepciones** | Exceptions | Interrupciones, short picks, problemas |

---

## Métricas Calculables

| Métrica | En inglés | Significado |
|---|---|---|
| **Unidades/hora** | Units/Hour | Cantidad de unidades procesadas por hora |
| **Líneas/hora** | Lines/Hour | Líneas de trabajo completadas por hora |
| **Picks/hora** | Picks/Hour | Recolecciones por hora |
| **Tiempo de viaje** | Travel Time | Porcentaje del tiempo dedicado a desplazamiento |
| **Tiempo muerto** | Idle Time | Porcentaje del tiempo sin actividad productiva |
| **Utilización** | Work Utilization | Porcentaje del tiempo en trabajo productivo vs. total |
| **Tiempo en cola** | Queue Time | Tiempo promedio que un work espera antes de ser asignado |

Estas métricas se agregan por operador, turno, zona, tipo de trabajo y bodega para identificar patrones y oportunidades de mejora.

---

*Documento derivado de la sección 33 del [Plan Maestro](../plan.md).*
