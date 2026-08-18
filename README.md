# 📦 ERP-WMS-TMS: Odoo Stack en Contenedores & Kubernetes (K3s / K8s)

[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-K3s%20%7C%20K8s-326CE5?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![Odoo](https://img.shields.io/badge/Odoo-19.0-714B67?logo=odoo&logoColor=white)](https://www.odoo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

Stack modular y desacoplado para el desarrollo y despliegue de **Odoo ERP 19** con enfoque especializado en **WMS** (*Warehouse Management System*) y **TMS** (*Transportation Management System*).

Diseñado con una arquitectura de contenedores independientes basada en estándares Cloud Native:
* 🛠️ **Desarrollo Local Ágil:** Soporte nativo para Docker Compose con recarga en caliente de módulos personalizados.
* ⚡ **Despliegue Ligero en K3s:** Optimizado con almacenamiento `local-path` y enrutamiento con Traefik Ingress.
* 🌐 **Escalabilidad a K8s de Producción:** Preparado para migración inmediata hacia clústeres Kubernetes estándar (AWS EKS, GCP GKE, AKS o Bare-Metal) mediante **Kustomize**.

---

## 🏛️ Arquitectura del Sistema

```
                         ┌─────────────────────────────────────────┐
                         │           Cliente / Navegador           │
                         └────────────────────┬────────────────────┘
                                              │ HTTP(S) / Websockets
                                              ▼
                         ┌─────────────────────────────────────────┐
                         │   Ingress Controller (Traefik / NGINX)  │
                         └───────┬─────────────────────────┬───────┘
                                 │ :8069 (HTTP)            │ :8072 (Longpolling/WS)
                                 ▼                         ▼
                         ┌─────────────────────────────────────────┐
                         │           Odoo Service (ClusterIP)      │
                         └────────────────────┬────────────────────┘
                                              │
                                              ▼
                         ┌─────────────────────────────────────────┐
                         │         Pod: Odoo App Container         │
                         │   - Core Odoo 19.0                      │
                         │   - Librerías Python (WMS/TMS)          │
                         │   - Volúmenes: Filestore + Addons       │
                         └────────────────────┬────────────────────┘
                                              │ Puerto 5432
                                              ▼
                         ┌─────────────────────────────────────────┐
                         │        Pod: PostgreSQL 16 Alpine        │
                         │   - Base de Datos Relacional            │
                         │   - Volumen Persistente (PVC)           │
                         └─────────────────────────────────────────┘
```

---

## 📁 Estructura del Proyecto

```text
ERP-WMS-TMS/
├── custom_addons/                 # Directorio para módulos personalizados (ERP, WMS, TMS)
├── docker/
│   └── odoo/
│       ├── Dockerfile             # Imagen personalizada con soporte WMS/TMS
│       └── odoo.conf              # Archivo de configuración base para Odoo
├── k8s/                           # Manifiestos de Kubernetes con Kustomize
│   ├── base/                      # Manifiestos canónicos estándar
│   │   ├── namespace.yaml
│   │   ├── configmap.yaml
│   │   ├── secrets.example.yaml
│   │   ├── postgres-pvc.yaml
│   │   ├── postgres-deployment.yaml
│   │   ├── postgres-service.yaml
│   │   ├── odoo-pvc.yaml
│   │   ├── odoo-deployment.yaml
│   │   ├── odoo-service.yaml
│   │   ├── ingress.yaml
│   │   └── kustomization.yaml
│   └── overlays/
│       ├── k3s-local/             # Overlay específico para K3s (Traefik + local-path)
│       │   ├── kustomization.yaml
│       │   ├── storageclass-patch.yaml
│       │   └── ingress-traefik-patch.yaml
│       └── k8s-prod/              # Overlay para K8s estándar / Nube (TLS + NGINX)
│           ├── kustomization.yaml
│           ├── storageclass-prod-patch.yaml
│           └── ingress-tls-patch.yaml
├── scripts/                       # Scripts de automatización y mantenimiento
│   ├── deploy-k3s.ps1 / .sh       # Despliegue en K3s
│   └── backup-db.ps1 / .sh        # Respaldo automático de base de datos
├── docker-compose.yml             # Orquestación para desarrollo local rápido
├── .env.example                   # Variables de entorno de referencia
├── .gitignore
└── README.md
```

---

## 🚀 Opción 1: Desarrollo Local Rápido con Docker Compose

Si deseas comenzar a desarrollar inmediatamente en tu máquina local sin necesidad de levantar un clúster Kubernetes:

### 1. Configurar variables de entorno
```bash
cp .env.example .env
```
*(En Windows PowerShell: `Copy-Item .env.example .env`)*

### 2. Construir e iniciar los contenedores
```bash
docker compose up -d --build
```

### 3. Acceder al sistema
* **URL:** [http://localhost:8069](http://localhost:8069)
* **Master Password:** Definido en tu archivo `.env` (`ODOO_ADMIN_PASSWORD`).
* Para ver los logs en tiempo real:
  ```bash
  docker compose logs -f odoo
  ```

---

## ⚡ Opción 2: Despliegue en K3s (Local / Edge)

K3s incluye por defecto el controlador Ingress **Traefik** y el StorageClass **`local-path`**.

### 1. Crear el archivo de secretos
Copia la plantilla de secretos y personaliza las contraseñas:
```bash
cp k8s/base/secrets.example.yaml k8s/base/secrets.yaml
```

### 2. Desplegar mediante el script automatizado
**En Windows (PowerShell):**
```powershell
.\scripts\deploy-k3s.ps1
```

**En Linux / Mac (Bash):**
```bash
chmod +x ./scripts/*.sh
./scripts/deploy-k3s.sh
```

*(O manualmente con `kubectl`:)*
```bash
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/secrets.yaml
kubectl apply -k k8s/overlays/k3s-local
```

### 3. Configuración de DNS Local
Para acceder mediante el Ingress en tu navegador, añade la siguiente entrada en tu archivo `hosts`:
* **Windows:** `C:\Windows\System32\drivers\etc\hosts`
* **Linux / Mac:** `/etc/hosts`

```text
127.0.0.1  odoo.local
```
Luego abre [http://odoo.local](http://odoo.local) en tu navegador.

*(Alternativamente, puedes usar Port-Forwarding sin Ingress:)*
```bash
kubectl port-forward svc/odoo-service 8069:8069 -n odoo
```

---

## 🌐 Opción 3: Despliegue en Kubernetes Estándar (K8s Producción)

Para desplegar en clústeres administrados (EKS, GKE, AKS o K8s Bare-Metal):

### 1. Configurar Secretos y Dominio
1. Crea tu archivo `k8s/base/secrets.yaml` con contraseñas seguras.
2. Edita `k8s/overlays/k8s-prod/ingress-tls-patch.yaml` con tu dominio real (ej. `erp.miempresa.com`).
3. Ajusta la clase de almacenamiento en `k8s/overlays/k8s-prod/storageclass-prod-patch.yaml` según tu proveedor de nube (ej. `gp3` en AWS, `standard-rwo` en GCP, `managed-csi` en Azure).

### 2. Aplicar Manifiestos
```bash
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/secrets.yaml
kubectl apply -k k8s/overlays/k8s-prod
```

---

## 🧩 Desarrollo de Módulos Personalizados (WMS & TMS)

Todos los módulos propios deben ubicarse en la carpeta `custom_addons/`.

### Crear un nuevo módulo
1. Crea una nueva subcarpeta en `custom_addons/mi_nuevo_modulo/`.
2. Incluye el archivo `__manifest__.py` con la metadata del módulo y las dependencias (ej. `stock`, `sale`, `purchase`).
3. Para actualizar un módulo directamente desde la terminal del contenedor:

**En Docker Compose:**
```bash
docker compose exec odoo odoo -u mi_nuevo_modulo -d nombre_de_tu_bd --stop-after-init
```

**En K3s / K8s:**
```bash
# Obtener el nombre del pod de Odoo
$ODOO_POD=$(kubectl get pods -n odoo -l app.kubernetes.io/name=odoo -o jsonpath="{.items[0].metadata.name}")

# Actualizar el módulo
kubectl exec -it $ODOO_POD -n odoo -- odoo -u mi_nuevo_modulo -d odoo_production --stop-after-init
```

---

## 🛠️ Comandos de Mantenimiento y Operaciones

### Monitoreo de Pods y Servicios
```bash
# Ver estado de todos los recursos
kubectl get all -n odoo

# Ver logs de Odoo en tiempo real
kubectl logs -f deployment/odoo -n odoo

# Ver logs de PostgreSQL
kubectl logs -f deployment/postgres -n odoo
```

### Respaldos de Base de Datos
Utiliza los scripts incluidos en `scripts/`:

**En Windows PowerShell:**
```powershell
.\scripts\backup-db.ps1 -DbName "odoo_production"
```

**En Linux / Mac:**
```bash
./scripts/backup-db.sh odoo_production
```

### Reiniciar el Servicio de Odoo
```bash
kubectl rollout restart deployment/odoo -n odoo
```

---

## 🔒 Variables de Entorno y Seguridad

| Variable | Descripción | Valor por Defecto / Sugerido |
| :--- | :--- | :--- |
| `POSTGRES_USER` | Usuario de base de datos para Odoo | `odoo` |
| `POSTGRES_PASSWORD` | Contraseña del usuario PostgreSQL | *(Generar string seguro)* |
| `POSTGRES_DB` | Nombre de base de datos principal | `odoo_production` |
| `ODOO_ADMIN_PASSWORD` | Master password para crear/eliminar/restaurar BDs | *(Generar string seguro)* |
| `ODOO_HTTP_PORT` | Puerto HTTP expuesto localmente | `8069` |
| `ODOO_LONGPOLLING_PORT`| Puerto para Websockets / Longpolling | `8072` |

> [!WARNING]
> Nunca hagas commit de los archivos `.env` o `k8s/base/secrets.yaml` en tu repositorio Git. Mantén únicamente los archivos `.example` versionados.

---

## 📄 Licencia

Este proyecto está estructurado bajo licencia **LGPL-3.0**. Los módulos personalizados en `custom_addons/` pueden adoptar licenciamiento privativo o de código abierto según los requerimientos de tu organización.
