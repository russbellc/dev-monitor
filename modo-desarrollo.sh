#!/usr/bin/env bash
# modo-desarrollo.sh — Configura el layout tri-panel de desarrollo en el TAB actual de Herdr
# Layout:
#   - Derecha (grande):  [Principal]  (Sesión de desarrollo activo con Agy)
#   - Izquierda-Arriba:  [Monitor]    (dev-monitor TUI en tiempo real)
#   - Izquierda-Abajo:   [Soporte]    (Consultas sin implementar)

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

if ! command -v herdr >/dev/null 2>&1; then
    echo "❌ Error: 'herdr' CLI no está disponible en este entorno."
    exit 1
fi

PANES_JSON=$(herdr pane list 2>/dev/null || echo "{}")
TABS_JSON=$(herdr tab list 2>/dev/null || echo "{}")

# 2. Identificar el TAB activo
CURRENT_TAB="${HERDR_TAB_ID}"

if [ -z "$CURRENT_TAB" ] || [ "$CURRENT_TAB" = "null" ]; then
    CURRENT_TAB=$(echo "$TABS_JSON" | jq -r '.result.tabs[] | select(.focused == true) | .tab_id' | head -1)
fi

if [ -z "$CURRENT_TAB" ] || [ "$CURRENT_TAB" = "null" ]; then
    CURRENT_TAB=$(echo "$PANES_JSON" | jq -r '.result.panes[] | select(.focused == true) | .tab_id' | head -1)
fi

if [ -z "$CURRENT_TAB" ] || [ "$CURRENT_TAB" = "null" ]; then
    CURRENT_TAB=$(echo "$PANES_JSON" | jq -r '.result.panes[0].tab_id' | head -1)
fi

echo "📌 Tab activo: ${CURRENT_TAB}"

# 3. Filtrar los panes que pertenecen EXCLUSIVAMENTE a este TAB
TAB_PANES=$(echo "$PANES_JSON" | jq -c "[.result.panes[] | select(.tab_id == \"${CURRENT_TAB}\")]")
NUM_PANES=$(echo "$TAB_PANES" | jq 'length')

echo "🔍 Paneles detectados en este tab: ${NUM_PANES}"

CALLER_PANE="${HERDR_PANE_ID}"
if [ -z "$CALLER_PANE" ] || [ "$CALLER_PANE" = "null" ]; then
    CALLER_PANE=$(echo "$TAB_PANES" | jq -r '.[] | select(.focused == true) | .pane_id' | head -1)
fi
if [ -z "$CALLER_PANE" ] || [ "$CALLER_PANE" = "null" ]; then
    CALLER_PANE=$(echo "$TAB_PANES" | jq -r '.[0].pane_id')
fi

# 4. Si el tab sólo tiene 1 panel: crear la distribución tri-panel
if [ "$NUM_PANES" -eq 1 ]; then
    echo "⚙️ Creando distribución tri-panel en este tab..."
    
    # 4.1. Split a la derecha con ratio 0.40: deja 40% a la izquierda y 60% a la derecha
    SPLIT_RIGHT=$(herdr pane split "${CALLER_PANE}" --direction right --ratio 0.40 2>/dev/null || echo "{}")
    NEW_RIGHT_PANE=$(echo "$SPLIT_RIGHT" | jq -r '.result.pane.pane_id // .result.pane_id // empty')
    
    # 4.2. Swap: intercambiar para que CALLER_PANE (la sesión de Agy actual) pase a la derecha
    if [ -n "$NEW_RIGHT_PANE" ]; then
        herdr pane swap --source-pane "${CALLER_PANE}" --target-pane "${NEW_RIGHT_PANE}" >/dev/null 2>&1 || true
        PRINCIPAL_PANE="${CALLER_PANE}"
        LEFT_PANE="${NEW_RIGHT_PANE}"
    else
        PRINCIPAL_PANE="${CALLER_PANE}"
        LEFT_PANE="${CALLER_PANE}"
    fi

    # 4.3. Split hacia abajo en el panel izquierdo para crear Soporte
    SPLIT_DOWN=$(herdr pane split "${LEFT_PANE}" --direction down --ratio 0.50 2>/dev/null || echo "{}")
    SOPORTE_PANE=$(echo "$SPLIT_DOWN" | jq -r '.result.pane.pane_id // .result.pane_id // empty')
    MONITOR_PANE="${LEFT_PANE}"

# Si tiene 2 paneles: dividir el izquierdo hacia abajo
elif [ "$NUM_PANES" -eq 2 ]; then
    echo "⚙️ Completando tercer panel en este tab..."
    P1=$(echo "$TAB_PANES" | jq -r '.[0].pane_id')
    P2=$(echo "$TAB_PANES" | jq -r '.[1].pane_id')
    PRINCIPAL_PANE="$P2"
    MONITOR_PANE="$P1"
    SPLIT_DOWN=$(herdr pane split "${MONITOR_PANE}" --direction down --ratio 0.50 2>/dev/null || echo "{}")
    SOPORTE_PANE=$(echo "$SPLIT_DOWN" | jq -r '.result.pane.pane_id // .result.pane_id // empty')

# Si ya tiene 3 o más paneles en este tab
elif [ "$NUM_PANES" -ge 3 ]; then
    PRINCIPAL_PANE=$(echo "$TAB_PANES" | jq -r '.[] | select(.label == "Principal") | .pane_id' | head -1)
    MONITOR_PANE=$(echo "$TAB_PANES" | jq -r '.[] | select(.label == "Monitor") | .pane_id' | head -1)
    SOPORTE_PANE=$(echo "$TAB_PANES" | jq -r '.[] | select(.label == "Soporte") | .pane_id' | head -1)

    if [ -z "$PRINCIPAL_PANE" ] || [ "$PRINCIPAL_PANE" = "null" ]; then
        PRINCIPAL_PANE=$(echo "$TAB_PANES" | jq -r '.[] | select(.focused == true) | .pane_id' | head -1)
    fi
    if [ -z "$MONITOR_PANE" ] || [ "$MONITOR_PANE" = "null" ]; then
        MONITOR_PANE=$(echo "$TAB_PANES" | jq -r ".[] | select(.pane_id != \"${PRINCIPAL_PANE}\") | .pane_id" | head -1)
    fi
    if [ -z "$SOPORTE_PANE" ] || [ "$SOPORTE_PANE" = "null" ]; then
        SOPORTE_PANE=$(echo "$TAB_PANES" | jq -r ".[] | select(.pane_id != \"${PRINCIPAL_PANE}\" and .pane_id != \"${MONITOR_PANE}\") | .pane_id" | head -1)
    fi
fi

# 5. Aplicar nombres y asegurar proporción 50% / 50%
if [ -n "$PRINCIPAL_PANE" ] && [ "$PRINCIPAL_PANE" != "null" ]; then
    herdr pane rename "${PRINCIPAL_PANE}" "Principal" >/dev/null 2>&1 || true
fi
if [ -n "$MONITOR_PANE" ] && [ "$MONITOR_PANE" != "null" ]; then
    herdr pane rename "${MONITOR_PANE}" "Monitor" >/dev/null 2>&1 || true
fi
if [ -n "$SOPORTE_PANE" ] && [ "$SOPORTE_PANE" != "null" ]; then
    herdr pane rename "${SOPORTE_PANE}" "Soporte" >/dev/null 2>&1 || true
fi

# 6. Lanzar dev-monitor en el panel Monitor
MONITOR_BIN="/home/aidev/proyectos/dev-monitor/monitor.py"
if [ ! -f "$MONITOR_BIN" ]; then
    MONITOR_BIN="dev-monitor"
fi

if [ -n "$MONITOR_PANE" ] && [ "$MONITOR_PANE" != "null" ]; then
    echo "📊 Iniciando dev-monitor en panel [Monitor] (${MONITOR_PANE})..."
    
    # Solo enviar 'q' si ya hay un monitor corriendo en primer plano
    IS_RUNNING_MONITOR=$(herdr pane process-info --pane "${MONITOR_PANE}" 2>/dev/null | jq -r '.result.process_info.foreground_processes[]? | select(.cmdline | test("monitor.py|dev-monitor")) | .pid' | head -1)
    if [ -n "$IS_RUNNING_MONITOR" ]; then
        herdr pane send-keys "${MONITOR_PANE}" "q" >/dev/null 2>&1 || true
        sleep 0.5
    fi

    herdr pane run "${MONITOR_PANE}" "cd '${CURRENT_DIR}' && python3 '${MONITOR_BIN}' --project '${PROJECT_NAME}'" >/dev/null 2>&1 || true
fi

# 7. Panel Soporte: Se deja como terminal libre a elección del usuario
if [ -n "$SOPORTE_PANE" ] && [ "$SOPORTE_PANE" != "null" ]; then
    echo "💻 Panel [Soporte] (${SOPORTE_PANE}) listo como terminal libre..."
    # Sincronizar directorio de trabajo
    herdr pane run "${SOPORTE_PANE}" "cd '${CURRENT_DIR}'" >/dev/null 2>&1 || true
fi

echo "✅ Modo Desarrollo activo en el tab [${CURRENT_TAB}]:"
echo "   ├── [Principal] (${PRINCIPAL_PANE}): Vista principal de desarrollo"
echo "   ├── [Monitor]   (${MONITOR_PANE}): Telemetría y Docker (${PROJECT_NAME})"
echo "   └── [Soporte]   (${SOPORTE_PANE}): Terminal libre (a tu elección)"
