#!/bin/bash
# ==============================================================================
# Script de Despliegue en K3s (Bash)
# ==============================================================================
set -e

echo "🚀 Iniciando despliegue de Odoo (ERP-WMS-TMS) en K3s..."

SECRET_FILE="k8s/base/secrets.yaml"
EXAMPLE_FILE="k8s/base/secrets.example.yaml"

if [ ! -f "$SECRET_FILE" ]; then
    echo "⚠️  No se encontró '$SECRET_FILE'. Copiando plantilla desde '$EXAMPLE_FILE'..."
    cp "$EXAMPLE_FILE" "$SECRET_FILE"
    echo "❗ IMPORTANTE: Revisa y edita '$SECRET_FILE' con tus credenciales reales antes de pasar a producción."
fi

echo "📦 Aplicando Namespace y Secretos..."
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f "$SECRET_FILE"

echo "⚙️ Aplicando manifiestos mediante Kustomize (Overlay: k3s-local)..."
kubectl apply -k k8s/overlays/k3s-local

echo "⏳ Esperando a que PostgreSQL y Odoo estén listos..."
kubectl rollout status deployment/postgres -n odoo --timeout=120s
kubectl rollout status deployment/odoo -n odoo --timeout=180s

echo "✅ ¡Despliegue completado con éxito!"
echo "📌 Puedes verificar el estado ejecutando: kubectl get all -n odoo"
