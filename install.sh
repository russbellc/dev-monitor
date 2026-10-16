#!/usr/bin/env bash
# Instalador de Dev Monitor TUI
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/.local/bin"

mkdir -p "${TARGET_DIR}"
chmod +x "${SCRIPT_DIR}/monitor.py"

ln -sf "${SCRIPT_DIR}/monitor.py" "${TARGET_DIR}/dev-monitor"

echo "✅ Dev Monitor instalado exitosamente en ${TARGET_DIR}/dev-monitor"
echo "👉 Puedes ejecutarlo desde cualquier directorio escribiendo: dev-monitor"
