# Ficha de Fase — Template

> Template estándar para detallar cada fase del roadmap al nivel de implementación. Este formato se usa para la bajada del Nivel 2 (Diseño Funcional/Técnico) al Nivel 3 (Implementación).

---

## ¿Cuándo usar este template?

Cuando una fase del roadmap está lista para ser implementada, se crea su ficha detallada usando este template. La ficha reemplaza las descripciones de alto nivel del roadmap con especificaciones implementables.

---

## Template

```markdown
# Fase [N] — [Nombre]

## Propósito
¿Para qué existe esta fase?

## Problema que resuelve
¿Qué problema operacional o técnico aborda?

## Alcance
¿Qué incluye esta fase?

## Fuera de alcance
¿Qué explícitamente NO incluye?

## Actores
¿Quién interactúa con esta funcionalidad? (Operador, Supervisor, Sistema, API)

## Casos de uso
Lista de casos de uso con actor, precondición, flujo y postcondición.

## Flujo funcional
Diagramas de flujo o secuencia de las operaciones principales.

## Entidades
Modelos de datos con campos, tipos y relaciones.

## Estados
Máquinas de estado de cada entidad principal.

## Reglas
Reglas de negocio que aplican (configurables vía Rule Engine).

## Comandos
Acciones que cambian estado (ej: CreateWork, AssignWork, ConfirmPick).

## Eventos
Hechos que se publican cuando algo ocurre (ej: WorkCompleted, InventoryMoved).

## Excepciones
Situaciones de error y su tratamiento.

## Concurrencia
Puntos críticos de concurrencia y estrategia de locking.

## Seguridad
Roles y permisos necesarios.

## Auditoría
Qué acciones se registran en el audit log.

## APIs
Endpoints expuestos (si aplica).

## Procesamiento Async
Qué operaciones se ejecutan de forma asíncrona.

## Modelos Odoo reutilizados
Lista de modelos existentes que se usan tal cual.

## Modelos Odoo extendidos
Lista de modelos existentes que se modifican.

## Modelos nuevos
Lista de modelos nuevos con campos detallados.

## Índices DB
Índices de base de datos necesarios para performance.

## Invariantes (v1.1)
Condiciones que siempre deben ser verdaderas. Ej: "reserved_quantity <= quantity".

## Transaction Boundary (v1.1)
Qué tablas se tocan en cada transacción y su SLO de duración.

## Idempotency Contract (v1.1)
Qué operaciones son idempotentes y cómo se garantiza (idempotency_key, command_id).

## Failure Recovery (v1.1)
Qué pasa si: pod crash, network loss, partial commit. Comportamiento esperado.

## Data Ownership (v1.1)
Qué dominio es dueño de cada modelo/campo. Quién puede modificar qué.

## Migration Impact (v1.1)
¿Esta fase agrega/modifica tablas? ¿Las migraciones son backward-compatible?

## Performance Budget (v1.1)
Tiempo máximo por operación. Ej: "claim < 50ms p99".

## SLO (v1.1)
Service Level Objectives medibles para esta fase.

## Dependencias
Fases o componentes que deben existir antes.

## Observabilidad
Métricas que esta fase expone.

## Pruebas unitarias
Casos de prueba unitaria.

## Pruebas de integración
Casos de prueba de integración.

## Pruebas de concurrencia
Escenarios de concurrencia a probar.

## Pruebas de performance
Benchmarks y SLA de performance.

## Criterios de aceptación
Condiciones que deben cumplirse para considerar la fase completa.

## Definition of Done
Checklist final de completación.
```

---

## Estimación de Tareas

Después de completar la ficha, se descompone en tareas estimables:

```markdown
| Task ID | Tarea | Descripción | Min hrs | Expected hrs | Max hrs |
|---------|-------|-------------|---------|--------------|---------|
| F07-001 | ... | ... | ... | ... | ... |
| F07-002 | ... | ... | ... | ... | ... |
```

Las estimaciones usan **tres puntos** (mínimo, esperado, máximo) para capturar incertidumbre.

---

*Documento derivado de la sección 46 del [Plan Maestro](../plan.md).*
