# ==============================================================================
# Script de Respaldo de Base de Datos en K3s/K8s (PowerShell)
# ==============================================================================
param(
    [string]$DbName = "odoo_production",
    [string]$OutputDir = "./backups"
)

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupFile = "$OutputDir/backup_${DbName}_${timestamp}.sql"

Write-Host "🔍 Buscando pod de PostgreSQL..." -ForegroundColor Cyan
$pgPod = (kubectl get pods -n odoo -l app.kubernetes.io/name=postgres -o jsonpath="{.items[0].metadata.name}")

if (-not $pgPod) {
    Write-Host "❌ Error: No se encontró ningún pod de PostgreSQL en el namespace 'odoo'." -ForegroundColor Red
    exit 1
}

Write-Host "💾 Generando volcado de la base de datos '$DbName' desde el pod '$pgPod'..." -ForegroundColor Cyan
kubectl exec -n odoo $pgPod -- pg_dump -U odoo $DbName > $backupFile

if (Test-Path $backupFile) {
    Write-Host "✅ Respaldo generado correctamente en: $backupFile" -ForegroundColor Green
} else {
    Write-Host "❌ Falló la creación del respaldo." -ForegroundColor Red
}
