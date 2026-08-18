# ==============================================================================
# Script de Despliegue en K3s (PowerShell)
# ==============================================================================
Write-Host "🚀 Iniciando despliegue de Odoo (ERP-WMS-TMS) en K3s..." -ForegroundColor Cyan

$secretPath = "k8s/base/secrets.yaml"
$examplePath = "k8s/base/secrets.example.yaml"

if (-not (Test-Path $secretPath)) {
    Write-Host "⚠️  No se encontró '$secretPath'. Copiando plantilla desde '$examplePath'..." -ForegroundColor Yellow
    Copy-Item $examplePath $secretPath
    Write-Host "❗ IMPORTANTE: Revisa y edita '$secretPath' con tus credenciales reales antes de pasar a producción." -ForegroundColor Yellow
}

Write-Host "📦 Aplicando Namespace y Secretos..." -ForegroundColor Cyan
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f $secretPath

Write-Host "⚙️ Aplicando manifiestos mediante Kustomize (Overlay: k3s-local)..." -ForegroundColor Cyan
kubectl apply -k k8s/overlays/k3s-local

Write-Host "⏳ Esperando a que PostgreSQL y Odoo estén listos..." -ForegroundColor Cyan
kubectl rollout status deployment/postgres -n odoo --timeout=120s
kubectl rollout status deployment/odoo -n odoo --timeout=180s

Write-Host "✅ ¡Despliegue completado con éxito!" -ForegroundColor Green
Write-Host "📌 Puedes verificar el estado ejecutando: kubectl get all -n odoo" -ForegroundColor White
