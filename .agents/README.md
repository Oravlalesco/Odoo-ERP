# Desarrollo WMS con Antigravity

El workspace contiene un equipo multiagente preparado para `/teamwork-preview`:

```text
wms-coordinator
├── wms-planner       discovery + CONTRACT FROZEN
├── wms-implementer   implementación en branch/worktree aislado
└── wms-auditor       auditoría independiente read-only
```

## Uso operativo

1. En Antigravity selecciona el agente `wms-coordinator`.
2. Inicia `/teamwork-preview`.
3. Usa una instrucción como:

```text
Continúa autónomamente con el siguiente slice del roadmap WMS.

Usa obligatoriamente:
wms-planner -> wms-implementer -> wms-auditor.

El planner debe descubrir el estado actual del repositorio y producir
CONTRACT STATUS: FROZEN antes de cualquier modificación.

El implementer debe trabajar contra ese contrato, en un Git
worktree/feature branch aislado, ejecutar todos los acceptance tests y
gates definidos, y entregar candidate SHA.

El auditor debe empezar con contexto limpio y revisar contract -> git ->
source -> tests -> docs -> schema/security -> runtime evidence.

Si hay P0/P1, volver al implementer únicamente con los findings y repetir
la auditoría. Detener solo en PASS / READY FOR PR.

No crear ni mergear PR. No modificar develop.
```

Los contratos, handoffs, auditorías y escalaciones se escriben en `.wms-agent-state/`, excluido localmente mediante `.git/info/exclude`. No se versionan dentro del feature diff.

## Smoke test local

Antes del primer slice autónomo:

1. Abre **Customizations → Rules** y confirma que `wms-agent-governance` esté en modo **Always On**.
2. Abre **Customizations → Custom Agents** y confirma que se cargaron `wms-coordinator`, `wms-planner`, `wms-implementer` y `wms-auditor`.
3. Ejecuta `/agents`, selecciona `wms-coordinator` como main agent e inicia una conversación nueva. Los workers aparecen en la sección **Subagents** después de ser invocados.
4. Solicita un discovery read-only que invoque únicamente a `wms-planner` con `Workspace=inherit`.
5. Confirma en el panel de subagents que la invocación termina y devuelve el reporte solicitado sin modificar archivos.
6. Solo después habilita `/teamwork-preview` para un slice real.

El coordinator declara `inheritCustomizations: true`; este ajuste es obligatorio para que un custom main agent pueda descubrir y reutilizar los subagents definidos en el workspace.

## Límites de autonomía

- El planner descubre el siguiente slice; ningún agente hardcodea un HU.
- El implementer no puede ampliar ni enmendar el contrato.
- El auditor no puede modificar código ni aprobar una corrección propia.
- El coordinator no puede saltarse P0/P1 ni convertir `PENDING` en `PASS`.
- El workflow termina antes de push, merge o PR; la protección de `develop` se mantiene mediante reglas del servidor y queda fuera de la autoridad de los agentes.
