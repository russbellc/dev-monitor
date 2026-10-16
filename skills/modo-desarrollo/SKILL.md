---
name: modo-desarrollo
description: Activa el espacio de trabajo tri-panel en Herdr (Principal a la derecha al 60%, Monitor y Soporte a la izquierda al 40%) y lanza el Dev Monitor configurado automáticamente para el proyecto actual. Usar cuando el usuario diga "modo desarrollo", "activa modo desarrollo", "inicia modo desarrollo", "modo dev" o similares.
---

# Modo Desarrollo — Tri-Panel Workspace con Dev Monitor

Esta skill organiza automáticamente el espacio de trabajo en Herdr en 3 paneles sincronizados según el estándar de desarrollo:

1. **Panel Principal (Derecha - 60% ancho):** Sesión interactiva de desarrollo con Agy.
2. **Panel Monitor (Izquierda-Arriba - 40% ancho):** `dev-monitor` TUI en tiempo real con auto-detección del proyecto actual.
3. **Panel Soporte (Izquierda-Abajo - 40% ancho):** Terminal libre en la raíz del proyecto para que el usuario elija qué ejecutar (bash, comandos, pruebas, agy, codex, etc.).

---

## Flujo de Activación

Cuando el usuario pida **"modo desarrollo"** (o "activa modo desarrollo", "abre modo desarrollo", "modo dev"):

1. **Detectar el proyecto actual:**
   - Si el usuario especificó un proyecto (ej. *"activa modo desarrollo para vitalab"*), usar ese nombre.
   - Si no, usar la carpeta actual (`thania`, `vitalab`, `pdf-studio`, etc.).

2. **Ejecutar el script automatizador:**
   ```bash
   modo-desarrollo [nombre_proyecto]
   ```
   *(O alternativamente: `bash ~/.local/bin/modo-desarrollo [nombre_proyecto]`)*

3. **Verificar los paneles:**
   El script se encarga de:
   - Identificar el TAB activo en Herdr (`HERDR_TAB_ID`).
   - Crear los 3 paneles en ese tab si no existen (con proporción 60% Principal / 40% Izquierda).
   - Renombrarlos a `Principal`, `Monitor`, `Soporte`.
   - Lanzar `dev-monitor --project <proyecto>` en el panel `Monitor`.
   - Dejar el panel `Soporte` como terminal libre en la raíz del proyecto.
   - Mantener el foco en el panel `Principal`.

4. **Confirmar al usuario:**
   Indicar brevemente que el layout tri-panel está listo, qué proyecto está siendo monitoreado y que puede comenzar a programar en el panel `Principal`.
