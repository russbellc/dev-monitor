#!/usr/bin/env bash
# Instalador de Dev Monitor TUI & Skill Modo Desarrollo
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/.local/bin"

mkdir -p "${TARGET_DIR}"
chmod +x "${SCRIPT_DIR}/monitor.py"
chmod +x "${SCRIPT_DIR}/modo-desarrollo.sh"

# 1. Enlaces para comandos CLI
ln -sf "${SCRIPT_DIR}/monitor.py" "${TARGET_DIR}/dev-monitor"
ln -sf "${SCRIPT_DIR}/modo-desarrollo.sh" "${TARGET_DIR}/modo-desarrollo"
ln -sf "${SCRIPT_DIR}/modo-desarrollo.sh" "${TARGET_DIR}/modo-dev"

echo "✅ Binarios instalados en ${TARGET_DIR}:"
echo "   ├── dev-monitor"
echo "   ├── modo-desarrollo"
echo "   └── modo-dev"

# 2. Instalación de Skills para Agentes (Antigravity / Codex)
SKILL_TARGETS=(
    "${HOME}/.agents/skills"
    "${HOME}/proyectos/.agents/skills"
    "${PWD}/.agents/skills"
)

for S_BASE in "${SKILL_TARGETS[@]}"; do
    if [ -d "$(dirname "$S_BASE")" ]; then
        mkdir -p "${S_BASE}/modo-desarrollo"
        cp -f "${SCRIPT_DIR}/skills/modo-desarrollo/SKILL.md" "${S_BASE}/modo-desarrollo/SKILL.md"
        mkdir -p "${S_BASE}/modo-dev"
        cp -f "${SCRIPT_DIR}/skills/modo-dev/SKILL.md" "${S_BASE}/modo-dev/SKILL.md"
        echo "✅ Skill instalado en: ${S_BASE}/modo-desarrollo"
    fi
done

echo ""
echo "🎉 Instalación completada."
echo "👉 Puedes ejecutar desde la terminal: dev-monitor  o  modo-desarrollo"
echo "👉 O pedirle a tu agente de IA: 'modo desarrollo' o 'modo dev'"
