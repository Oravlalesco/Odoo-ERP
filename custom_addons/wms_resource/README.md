# WMS Resource Identity Core

## Propósito y Límites Arquitectónicos (ADR-028)
Garantiza el desacople de la autenticación (`res.users`) de la ejecución física polimórfica (humanos y equipos materiales) en el ecosistema WMS. Funciona como un modelo satélite sobre Odoo estándar para proveer identidad sin inyectar lógicas de negocio operacionales directas.

## Foundations Reutilizadas
- `resource.resource`: Ecosistema base de polimorfismo, calendarios y hojas de ruta.
- `stock.warehouse`: Contexto espacial primario de la operación.

## Modelo Satélite (`wms.resource`)
Se trata de una relación 1:0..1 que provee **3 campos funcionales**:
- `resource_id`: (Many2one) Vínculo requerido al recurso nativo (`resource.resource`) con restricción de identidad (`UNIQUE`).
- `warehouse_id`: Almacén operacional de despliegue.
- `company_id`: Derivado estrictamente del almacén asignado.

## Invariantes y Protección contra Drift
- Validación continua en `write()` sobre `resource.resource` (protección pasiva).
- Prohibición de cambio de compañía si existe perfil satélite.
- Exigencia estricta de asignación de `user_id` para recursos de tipo humano.
- Prohibición de desvinculación de un `user_id` si el humano ya cuenta con perfil WMS activo.

## Seguridad RBAC y Multi-Compañía
- **Aislamiento absoluto (`check_company=True`)**: Interacciones delimitadas a las compañías autorizadas del usuario.
- **Rule `operator own`**: El Operador visualiza exclusivamente su propio perfil WMS.
- **Roles**:
  - `Operator / Supervisor`: Solo Lectura (`Read`).
  - `Manager / System Admin`: Lectura, Creación, Escritura, Borrado (`CRUD`).

## Dependencias
Dependencias directas del ecosistema Odoo 19 WMS:
- `resource`
- `stock`
- `wms_core`
- `wms_warehouse_master`
