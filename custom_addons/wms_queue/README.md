# WMS Núcleo de Colas de Trabajo

## Propósito y Límites Arquitectónicos (QUEUE-001 / ARCH-001 / ADR-028)
Establece la identidad canónica para las colas de trabajo (`wms.queue`) en el Kernel WMS.
Desacopla la organización y compatibilidad del trabajo de los mecanismos de claim y asignación transaccional:
- **Work Engine**: Dueño exclusivo de la persistencia de `wms.work` y de la primitiva atómica de claim (`READY -> ASSIGNED`) mediante `FOR UPDATE SKIP LOCKED`.
- **Queue Core (`wms_queue`)**: Define la identidad canónica de cola, su anclaje a almacén/compañía, prioridades de atención y compatibilidad estática (zonas y recursos habilitados).
- **Assignment Engine**: Responsable futuro del scoring dinámico, priorización y selección de candidatos.

## Modelo Canónico (`wms.queue`)
Exact Set Equality de **8 campos funcionales**:
- `name`: Nombre descriptivo de la cola (traducible).
- `code`: Código operacional único por almacén (`UNIQUE(warehouse_id, code)`), normalizado en mayúsculas y sin espacios (máx. 32 chars).
- `warehouse_id`: Almacén operacional al que pertenece la cola (`stock.warehouse`).
- `company_id`: Derivado estructuralmente de `warehouse_id.company_id`.
- `priority`: Prioridad operacional de atención de 0 a 100 (default 50; mayor valor = mayor prioridad).
- `active`: Estado activo/archivado de la cola.
- `zone_ids`: Zonas operacionales atendidas por la cola (`wms.zone`).
- `allowed_resource_ids`: Recursos habilitados para recibir trabajo de la cola (`wms.resource`).

## Semántica de Compatibilidad Fail-Closed
Una cola sin zonas habilitadas o sin recursos asignados se considera no apta para despacho/asignación automática (`is_dispatchable() -> False`). Queda prohibido cualquier fallback FIFO global por almacén.

## Protección contra Drift Bidireccional
- Modificar el almacén de una zona (`wms.zone`) asociada a una cola (activa o archivada) es bloqueado mediante validación cruzada con `.sudo().with_context(active_test=False)`.
- Modificar el almacén de un recurso operacional (`wms.resource`) vinculado a una cola (activa o archivada) es bloqueado mediante validación cruzada con `.sudo().with_context(active_test=False)`.

## Seguridad y RBAC

### Aislamiento Multi-Compañía
Record rule global `[('company_id', 'in', company_ids)]` y `_check_company_auto = True`.

### Matriz de Acceso
- `Operator`: Solo Lectura (1, 0, 0, 0)
- `Supervisor`: Solo Lectura (1, 0, 0, 0)
- `Manager`: Control Total CRUD (1, 1, 1, 1)
- `System Admin`: Control Total CRUD (1, 1, 1, 1)

## Observabilidad (ADR-023)
Excepción de bootstrap: Las métricas `queue_depth` y `queue_wait_time` aplican `N/A` en `QUEUE-001`. Su recolección e instrumentación se iniciará estrictamente en `WORK-004` una vez que `wms.work` incorpore el campo relacional `queue_id`.

## Dependencias
- `stock`
- `wms_core`
- `wms_warehouse_master`
- `wms_resource`
