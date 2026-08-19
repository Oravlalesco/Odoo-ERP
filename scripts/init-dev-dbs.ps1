# ==============================================================================
# Inicialización de bases de datos de desarrollo y testing para Odoo 19
# BOOT-002: Dev/Test Database Protocol
# ==============================================================================
#
# USO:
#   .\scripts\init-dev-dbs.ps1          # Inicializa odoo_dev (si no existe) y odoo_test (--force)
#   .\scripts\init-dev-dbs.ps1 dev      # Solo odoo_dev
#   .\scripts\init-dev-dbs.ps1 test     # Solo odoo_test (--force siempre)
#
# POLÍTICA:
#   odoo_dev  → PERSISTENTE: si existe, no se toca. Reset solo con flag explícito.
#   odoo_test → DESECHABLE:  siempre se recrea con --force para reproducibilidad.
#
# NOTA TÉCNICA:
#   El entrypoint oficial de odoo:19.0 inyecta --db_host/--db_port/--db_user/--db_password
#   DESPUÉS del comando, lo cual colisiona con los subcomandos `db` y `module`.
#   Solución: usar --entrypoint "" y pasar credenciales antes del subcomando.
# ==============================================================================

param(
    [ValidateSet("all", "dev", "test")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"

$DevDb  = if ($env:ODOO_DEV_DB)        { $env:ODOO_DEV_DB }        else { "odoo_dev" }
$TestDb = if ($env:ODOO_TEST_DB)       { $env:ODOO_TEST_DB }       else { "odoo_test" }
$DbHost = if ($env:DB_HOST)            { $env:DB_HOST }            else { "db" }
$DbPort = if ($env:DB_PORT)            { $env:DB_PORT }            else { "5432" }
$DbUser = if ($env:POSTGRES_USER)      { $env:POSTGRES_USER }      else { "odoo" }
$DbPass = if ($env:POSTGRES_PASSWORD)  { $env:POSTGRES_PASSWORD }  else { "odoo_secure_password_2026" }

# Argumentos de conexión a DB para subcomandos odoo db/module
$DbArgs = @("--db_host", $DbHost, "--db_port", $DbPort, "-r", $DbUser, "-w", $DbPass)

function Invoke-OdooCmd {
    param([Parameter(ValueFromRemainingArguments)]$Args)
    docker compose run --rm --entrypoint "" odoo odoo @DbArgs @Args
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Comando Odoo falló con código $LASTEXITCODE" -ForegroundColor Red
        exit 1
    }
}

# Verificar PostgreSQL
Write-Host "`n=== Verificando PostgreSQL... ===" -ForegroundColor Cyan
docker compose exec db pg_isready -U $DbUser
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: PostgreSQL no está corriendo. Ejecute 'docker compose up -d db' primero." -ForegroundColor Red
    exit 1
}

function Initialize-DevDb {
    Write-Host "`n=== Inicializando base de datos: $DevDb (PERSISTENTE) ===" -ForegroundColor Cyan
    $exists = docker compose exec db psql -U $DbUser -tAc "SELECT 1 FROM pg_database WHERE datname='$DevDb'" 2>$null
    if ($exists -and $exists.Trim() -eq "1") {
        Write-Host "  → $DevDb ya existe. No se modifica (política PERSISTENTE)." -ForegroundColor Yellow
        Write-Host "  → Para resetear: Invoke-OdooCmd db init --force $DevDb" -ForegroundColor DarkGray
    } else {
        Write-Host "  → Creando $DevDb..." -ForegroundColor Green
        Invoke-OdooCmd db init $DevDb
        Write-Host "  → $DevDb inicializada correctamente." -ForegroundColor Green
    }
}

function Initialize-TestDb {
    Write-Host "`n=== Inicializando base de datos: $TestDb (DESECHABLE) ===" -ForegroundColor Cyan
    Write-Host "  → Recreando $TestDb con --force..." -ForegroundColor Green
    Invoke-OdooCmd db init --force $TestDb
    Write-Host "  → $TestDb inicializada correctamente (limpia)." -ForegroundColor Green
}

switch ($Target) {
    "dev"  { Initialize-DevDb }
    "test" { Initialize-TestDb }
    "all"  { Initialize-DevDb; Initialize-TestDb }
}

Write-Host "`n=== Bases de datos disponibles ===" -ForegroundColor Cyan
docker compose exec db psql -U $DbUser -tAc "SELECT datname FROM pg_database WHERE datname LIKE 'odoo_%' ORDER BY datname"

Write-Host "`nProtocolo:" -ForegroundColor White
Write-Host "  $DevDb  → desarrollo manual (persistente)" -ForegroundColor White
Write-Host "  $TestDb → tests automatizados (desechable, --force en cada suite)" -ForegroundColor White
Write-Host ""
