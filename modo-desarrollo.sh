#!/usr/bin/env bash
# modo-desarrollo.sh — Configura el layout tri-panel de desarrollo en Herdr
# Layout:
#   - Derecha:        [Principal]  (Sesión de desarrollo activo)
#   - Izquierda-Arriba: [Monitor]    (dev-monitor TUI en tiempo real)
#   - Izquierda-Abajo:  [Soporte]    (Consultas sin implementar)

set -e

PROJECT_ARG="$1"
CURRENT_DIR="$(pwd)"

# 1. Determinar el nombre del proyecto
if [ -n "$PROJECT_ARG" ]; then
    PROJECT_NAME="$PROJECT_ARG"
else
    FOLDER_NAME="$(basename "$CURRENT_DIR")"
    if [ "$FOLDER_NAME" = "03medical_app" ] || [ "$FOLDER_NAME" = "thania" ]; then
        PROJECT_NAME="thania"
    else
        PROJECT_NAME="$FOLDER_NAME"
    fi
fi

echo "🚀 Iniciando Modo Desarrollo para el proyecto: [${PROJECT_NAME}]..."

# 2. Verificar que Herdr esté disponible
if ! command -v herdr >/dev/null 2>&1; then
    echo "❌ Error: 'herdr' CLI no está disponible en este entorno."
    exit 1
fi

PANES_JSON=$(herdr pane list 2>/dev/null || echo "{}")

# Identificar el workspace activo (del panel focused)
ACTIVE_WORKSPACE=$(echo "$PANES_JSON" | jq -r '.result.panes[] | select(.focused == true) | .workspace_id' | head -1)

if [ -z "$ACTIVE_WORKSPACE" ] || [ "$ACTIVE_WORKSPACE" = "null" ]; then
    # Fallback al primer workspace
    ACTIVE_WORKSPACE=$(echo "$PANES_JSON" | jq -r '.result.panes[0].workspace_id' | head -1)
fi

echo "📌 Workspace activo: ${ACTIVE_WORKSPACE}"

# Obtener panes del workspace activo
WORKSPACE_PANES=$(echo "$PANES_JSON" | jq -c "[.result.panes[] | select(.workspace_id == \"${ACTIVE_WORKSPACE}\")]")
NUM_PANES=$(echo "$WORKSPACE_PANES" | jq 'length')

MONITOR_PANE=$(echo "$WORKSPACE_PANES" | jq -r '.[] | select(.label == "Monitor") | .pane_id' | head -1)
SOPORTE_PANE=$(echo "$WORKSPACE_PANES" | jq -r '.[] | select(.label == "Soporte") | .pane_id' | head -1)
PRINCIPAL_PANE=$(echo "$WORKSPACE_PANES" | jq -r '.[] | select(.label == "Principal") | .pane_id' | head -1)

# 3. Si no existen con esos nombres pero ya hay 3 o más paneles en el workspace
if [ "$NUM_PANES" -ge 3 ]; then
    # Asignar por posición si no tenían label
    if [ -z "$PRINCIPAL_PANE" ] || [ "$PRINCIPAL_PANE" = "null" ]; then
        PRINCIPAL_PANE=$(echo "$WORKSPACE_PANES" | jq -r '.[] | select(.focused == true) | .pane_id' | head -1)
    fi
    if [ -z "$MONITOR_PANE" ] || [ "$MONITOR_PANE" = "null" ]; then
        MONITOR_PANE=$(echo "$WORKSPACE_PANES" | jq -r ".[] | select(.pane_id != \"${PRINCIPAL_PANE}\") | .pane_id" | head -1)
    fi
    if [ -z "$SOPORTE_PANE" ] || [ "$SOPORTE_PANE" = "null" ]; then
        SOPORTE_PANE=$(echo "$WORKSPACE_PANES" | jq -r ".[] | select(.pane_id != \"${PRINCIPAL_PANE}\" and .pane_id != \"${MONITOR_PANE}\") | .pane_id" | head -1)
    fi
fi

# 4. Si faltan paneles (solo hay 1 o 2), crearlos
if [ "$NUM_PANES" -lt 3 ]; then
    CURRENT_FOCUSED=$(echo "$WORKSPACE_PANES" | jq -r '.[] | select(.focused == true) | .pane_id' | head -1)
    if [ -z "$CURRENT_FOCUSED" ] || [ "$CURRENT_FOCUSED" = "null" ]; then
        CURRENT_FOCUSED=$(echo "$WORKSPACE_PANES" | jq -r '.[0].pane_id')
    fi

    echo "⚙️ Configurando distribución de 3 paneles..."
    if [ "$NUM_PANES" -eq 1 ]; then
        # Dividir a la derecha para dejar el principal
        SPLIT_RIGHT=$(herdr pane split "${CURRENT_FOCUSED}" --direction right --ratio 0.55 2>/dev/null || echo "{}")
        PRINCIPAL_PANE=$(echo "$SPLIT_RIGHT" | jq -r '.result.pane_id // empty')
        
        # El pane original pasa a ser el lado izquierdo (Monitor)
        MONITOR_PANE="${CURRENT_FOCUSED}"
        
        # Dividir el monitor hacia abajo para crear Soporte
        SPLIT_DOWN=$(herdr pane split "${MONITOR_PANE}" --direction down --ratio 0.50 2>/dev/null || echo "{}")
        SOPORTE_PANE=$(echo "$SPLIT_DOWN" | jq -r '.result.pane_id // empty')
    elif [ "$NUM_PANES" -eq 2 ]; then
        P1=$(echo "$WORKSPACE_PANES" | jq -r '.[0].pane_id')
        P2=$(echo "$WORKSPACE_PANES" | jq -r '.[1].pane_id')
        PRINCIPAL_PANE="$P2"
        MONITOR_PANE="$P1"
        SPLIT_DOWN=$(herdr pane split "${MONITOR_PANE}" --direction down --ratio 0.50 2>/dev/null || echo "{}")
        SOPORTE_PANE=$(echo "$SPLIT_DOWN" | jq -r '.result.pane_id // empty')
    fi
fi

# 5. Aplicar nombres estandarizados
if [ -n "$PRINCIPAL_PANE" ] && [ "$PRINCIPAL_PANE" != "null" ]; then
    herdr pane rename "${PRINCIPAL_PANE}" "Principal" >/dev/null 2>&1 || true
fi
if [ -n "$MONITOR_PANE" ] && [ "$MONITOR_PANE" != "null" ]; then
    herdr pane rename "${MONITOR_PANE}" "Monitor" >/dev/null 2>&1 || true
fi
if [ -n "$SOPORTE_PANE" ] && [ "$SOPORTE_PANE" != "null" ]; then
    herdr pane rename "${SOPORTE_PANE}" "Soporte" >/dev/null 2>&1 || true
fi

# 6. Lanzar o actualizar el Monitor en el panel Monitor
MONITOR_BIN="/home/aidev/proyectos/dev-monitor/monitor.py"
if [ ! -f "$MONITOR_BIN" ]; then
    MONITOR_BIN="dev-monitor"
fi

if [ -n "$MONITOR_PANE" ] && [ "$MONITOR_PANE" != "null" ]; then
    echo "📊 Actualizando monitor en panel [Monitor] (${MONITOR_PANE})..."
    # Salir de cualquier monitor anterior
    herdr pane send-keys "${MONITOR_PANE}" "q" >/dev/null 2>&1 || true
    sleep 0.5
    # Ejecutar monitor apuntando al proyecto actual
    herdr pane run "${MONITOR_PANE}" "cd '${CURRENT_DIR}' && python3 '${MONITOR_BIN}' --project '${PROJECT_NAME}'" >/dev/null 2>&1 || true
fi

# 7. Asegurar que Soporte tenga una sesión lista si está libre
if [ -n "$SOPORTE_PANE" ] && [ "$SOPORTE_PANE" != "null" ]; then
    P_INFO=$(echo "$WORKSPACE_PANES" | jq -r ".[] | select(.pane_id == \"${SOPORTE_PANE}\")")
    S_AGENT=$(echo "$P_INFO" | jq -r '.agent // empty')
    if [ -z "$S_AGENT" ] || [ "$S_AGENT" = "null" ]; then
        echo "💬 Iniciando agente de soporte en panel [Soporte] (${SOPORTE_PANE})..."
        herdr pane run "${SOPORTE_PANE}" "agy --dangerously-skip-permissions --model gemini-3.8-flash-low" >/dev/null 2>&1 || true
    fi
fi

echo "✅ Modo Desarrollo activo y sincronizado:"
echo "   ├── [Principal] (${PRINCIPAL_PANE}): Vista principal de desarrollo"
echo "   ├── [Monitor]   (${MONITOR_PANE}): Telemetría y Docker (${PROJECT_NAME})"
echo "   └── [Soporte]   (${SOPORTE_PANE}): Consultas sin implementación"
