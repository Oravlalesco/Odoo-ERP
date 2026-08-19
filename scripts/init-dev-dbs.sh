#!/bin/bash
# ==============================================================================
# Inicialización de bases de datos de desarrollo y testing para Odoo 19
# BOOT-002: Dev/Test Database Protocol
# ==============================================================================
#
# USO:
#   ./scripts/init-dev-dbs.sh          # Inicializa odoo_dev (si no existe) y odoo_test (--force)
#   ./scripts/init-dev-dbs.sh dev      # Solo odoo_dev
#   ./scripts/init-dev-dbs.sh test     # Solo odoo_test (--force siempre)
#
# POLÍTICA:
#   odoo_dev  → PERSISTENTE: si existe, no se toca. Reset solo con flag explícito.
#   odoo_test → DESECHABLE:  siempre se recrea con --force para reproducibilidad.
#
# REQUIERE:
#   - Docker Compose con servicio 'db' corriendo (healthy)
#   - Servicio 'odoo' definido en docker-compose.yml
#
# NOTA TÉCNICA:
#   El entrypoint oficial de odoo:19.0 inyecta --db_host/--db_port/--db_user/--db_password
#   DESPUÉS del comando, lo cual colisiona con los subcomandos `db` y `module`.
#   Solución: usar --entrypoint "" y pasar credenciales antes del subcomando.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

DEV_DB="${ODOO_DEV_DB:-odoo_dev}"
TEST_DB="${ODOO_TEST_DB:-odoo_test}"
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${POSTGRES_USER:-odoo}"
DB_PASS="${POSTGRES_PASSWORD:-odoo_secure_password_2026}"

cd "$PROJECT_DIR"

# Argumentos de conexión a DB para subcomandos odoo db/module
DB_ARGS="--db_host $DB_HOST --db_port $DB_PORT -r $DB_USER -w $DB_PASS"

odoo_cmd() {
    docker compose run --rm --entrypoint "" odoo odoo $DB_ARGS "$@"
}

# Verificar que db está corriendo
echo "=== Verificando PostgreSQL... ==="
docker compose exec db pg_isready -U "$DB_USER" || {
    echo "ERROR: PostgreSQL no está corriendo. Ejecute 'docker compose up -d db' primero."
    exit 1
}

init_dev_db() {
    echo ""
    echo "=== Inicializando base de datos: $DEV_DB (PERSISTENTE) ==="
    EXISTS=$(docker compose exec db psql -U "$DB_USER" -tAc "SELECT 1 FROM pg_database WHERE datname='$DEV_DB'" 2>/dev/null || echo "")
    if [ "$EXISTS" = "1" ]; then
        echo "  → $DEV_DB ya existe. No se modifica (política PERSISTENTE)."
        echo "  → Para resetear: ./scripts/init-dev-dbs.sh con ODOO_FORCE_DEV=1"
    else
        echo "  → Creando $DEV_DB..."
        odoo_cmd db init "$DEV_DB"
        echo "  → $DEV_DB inicializada correctamente."
    fi
}

init_test_db() {
    echo ""
    echo "=== Inicializando base de datos: $TEST_DB (DESECHABLE) ==="
    echo "  → Recreando $TEST_DB con --force..."
    odoo_cmd db init --force "$TEST_DB"
    echo "  → $TEST_DB inicializada correctamente (limpia)."
}

TARGET="${1:-all}"

case "$TARGET" in
    dev)  init_dev_db ;;
    test) init_test_db ;;
    all)  init_dev_db; init_test_db ;;
    *)    echo "Uso: $0 [dev|test|all]"; exit 1 ;;
esac

echo ""
echo "=== Bases de datos disponibles ==="
docker compose exec db psql -U "$DB_USER" -tAc "SELECT datname FROM pg_database WHERE datname LIKE 'odoo_%' ORDER BY datname"
echo ""
echo "Protocolo:"
echo "  $DEV_DB  → desarrollo manual (persistente)"
echo "  $TEST_DB → tests automatizados (desechable, --force en cada suite)"
echo ""
