#!/bin/bash
# ==============================================================================
# Script de Respaldo de Base de Datos en K3s/K8s (Bash)
# ==============================================================================
set -e

DB_NAME="${1:-odoo_production}"
OUTPUT_DIR="${2:-./backups}"

mkdir -p "$OUTPUT_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${OUTPUT_DIR}/backup_${DB_NAME}_${TIMESTAMP}.sql"

echo "🔍 Buscando pod de PostgreSQL..."
PG_POD=$(kubectl get pods -n odoo -l app.kubernetes.io/name=postgres -o jsonpath="{.items[0].metadata.name}")

if [ -z "$PG_POD" ]; then
    echo "❌ Error: No se encontró ningún pod de PostgreSQL en el namespace 'odoo'."
    exit 1
fi

echo "💾 Generando volcado de la base de datos '${DB_NAME}' desde el pod '${PG_POD}'..."
kubectl exec -n odoo "$PG_POD" -- pg_dump -U odoo "$DB_NAME" > "$BACKUP_FILE"

echo "✅ Respaldo generado correctamente en: $BACKUP_FILE"
