# Plataforma DEV vs PROD — Diferencias de Infraestructura

> Documenta explícitamente las diferencias entre el entorno de desarrollo/staging y el entorno de producción. Lo que funciona para un desarrollador local no sirve para 250 operadores RF (ADR-020/021/022).

---

## Contexto

El repositorio actual despliega una infraestructura válida para desarrollo:
- 1 Odoo pod, 1 PostgreSQL pod, workers=0
- Addons montados desde PVC
- Filestore en ReadWriteOnce PVC
- Sin separación de workloads

Esto está **correcto para desarrollo**. Pero no es producción.

---

## Matriz de Diferencias

| Aspecto | DEV / Staging | Producción |
|---|---|---|
| **PostgreSQL** | 1 pod, strategy=Recreate | PostgreSQL Operator HA (primary + replicas) |
| **Odoo pods** | 1 pod, workers=0 | HPA por workload (backoffice, RF, API, worker) |
| **Addons** | PVC mount `/mnt/extra-addons` | **Imagen inmutable** (addons dentro del container) |
| **Filestore** | ReadWriteOnce PVC | RWX (CephFS/NFS) o Object Storage |
| **Redis** | Opcional | Requerido (cache, sessions, rate limiting) |
| **RabbitMQ** | Opcional | Requerido (async, outbox, integration) |
| **Monitoring** | Opcional | Prometheus + Grafana |
| **Logging** | stdout | Loki / ELK centralizado |
| **Secrets** | K8s Secrets básicos | Vault o Sealed Secrets |
| **CI/CD** | git push manual | Pipeline completo: test → build → push → deploy |
| **Ingress** | Traefik (K3s default) | Nginx Ingress + TLS |
| **Backup** | Manual | Automatizado: WAL archiving + PITR |

---

## Addons Inmutables (ADR-020)

### DEV (actual)

```yaml
volumeMounts:
  - name: odoo-extra-addons
    mountPath: /mnt/extra-addons
```

Esto permite iterar rápidamente durante desarrollo.

### PROD (objetivo)

```dockerfile
FROM odoo:19.0
COPY custom_addons /mnt/extra-addons
```

```text
git commit
   ↓
CI: lint + tests
   ↓
docker build (imagen inmutable con addons)
   ↓
docker push registry.example.com/wms:sha-abc123
   ↓
kubectl set image deployment/wms-rf wms=registry.example.com/wms:sha-abc123
```

**Garantía**: Pod A, Pod B, Pod C ejecutan exactamente el mismo código.

---

## PostgreSQL HA

### DEV (actual)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
spec:
  replicas: 1
  strategy:
    type: Recreate
```

### PROD (objetivo)

Usar un **PostgreSQL Operator** (ej: CloudNativePG, Zalando PostgreSQL Operator):

```text
Primary → Replica 1 → Replica 2
            ↓
      WAL archiving → Object Storage
            ↓
      PITR capability
```

Componentes:
- **Primary**: read-write
- **Replicas**: read-only (reporting, analytics)
- **WAL archiving**: Point-in-Time Recovery
- **Connection pooling**: PgBouncer
- **Monitoring**: pg_stat_statements, métricas a Prometheus

> **Nota v1.1**: Se elimina la referencia a "Patroni/Citus" como alternativas equivalentes. Citus es para distributed queries y **no es necesario en este WMS inicialmente**. Patroni o CloudNativePG son orquestadores de HA — eso sí es lo que necesitamos.

---

## Filestore Multi-Node (ADR-021)

### Problema

```yaml
accessModes: ["ReadWriteOnce"]
```

Con RWO, solo un nodo puede montar el volumen. Si hay múltiples pods RF en diferentes nodos, no pueden compartir el filestore.

### Opciones

| Opción | Pros | Contras |
|---|---|---|
| **RWX via CephFS/NFS** | Transparente para Odoo | Performance, complejidad de storage |
| **Object Storage (MinIO/S3)** | Escalable, independiente | Requiere módulo Odoo de attachment storage |
| **Externalizar attachments a DB** | Simple | Aumenta tamaño de DB |

---

## Database Migration Protocol (ADR-022)

### El Problema

Todos los workloads (`backoffice`, `wms-rf`, `wms-worker`) usan la misma base de datos. Un `odoo -u wms_work` modifica tablas que RF está usando activamente.

### Protocolo

```text
1. PRE-DEPLOY
   - Ejecutar migraciones backward-compatible
   - Verificar: ¿las queries de RF siguen funcionando con el schema nuevo?
   
2. DEPLOY
   - Rolling update: pods nuevos con código nuevo
   - Pods viejos coexisten brevemente con pods nuevos
   - Ambos deben funcionar con el mismo schema

3. POST-DEPLOY
   - Si es necesario, ejecutar migraciones que rompen backward-compat
   - Estas solo se ejecutan cuando todos los pods tienen código nuevo

4. VERIFICATION
   - Health checks
   - Smoke tests
   - Performance baseline comparison
```

### Regla

> Cada migración de schema debe poder coexistir con la versión anterior del código durante al menos 5 minutos (tiempo de rolling update).

---

*Documento nuevo para v1.1 (ADR-020/021/022).*
