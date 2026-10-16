# ⬡ Dev Monitor TUI

> Monitor interactivo ultraligero de recursos globales (CPU, RAM, Sparklines) y contenedores Docker con visor de logs en tiempo real para entornos de desarrollo y servidores.

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-green.svg)
![UI: Curses TUI](https://img.shields.io/badge/UI-Curses%20TUI-cyan.svg)
![Status: Production Ready](https://img.shields.io/badge/Status-Ready-brightgreen.svg)

---

## ⚡ Características Principales

* **🚀 Zero-Lag (Arquitectura Asíncrona):** Hilos independientes para telemetría pesada (`ps` y `docker stats`) y lector de logs no bloqueante. La interfaz de usuario responde en `< 100ms` sin ningún congelamiento.
* **🔍 Auto-Detección de Proyectos:** Detecta automáticamente el proyecto Docker Compose en el directorio actual (vía label `com.docker.compose.project`, `.env` o nombre de carpeta). Funciona en **cualquier proyecto** (`thania`, `vitalab`, `coolify`, etc.).
* **📈 Sparklines en Vivo:** Gráfico de tendencia con caracteres unicode (` ▂▃▄▅▆▇█`) mostrando los picos de CPU y RAM en tiempo real.
* **🎛️ Modo Editor (Customizer):** Presiona `e` para activar o desactivar cualquiera de los 6 componentes de la vista con guardado automático en `~/.dev_monitor_config.json`.
* **📱 Diseño 100% Responsivo:** Se adapta de forma inteligente tanto a terminales ultra-anchas como a paneles divididos y compactos (2 columnas x 3 filas).
* **🔄 Switch Instantáneo de Logs:** Presiona `1`, `2`, `3` o `4` para cambiar en vivo de contenedor sin reiniciar el proceso.
* **🔎 Filtro Interactivo de Logs:** Presiona `/` para filtrar en tiempo real (ej. `error`, `auth`, `prisma`, `500`).
* **📜 Navegación & Scroll:** Scroll fluido en tablas Top (`↑ / ↓`, `j / k`) y en logs (`PgUp / PgDn`, `Home / End`, `G` para volver a tiempo real).

---

## 🖥️ Vista Previa

```text
  ⬡ DEV MONITOR  │  serverus  │  up 193h 48m         load: 1.37 1.13 1.15  2026-10-16 02:30:07
────────────────────────────────────────────────────────────────────────────────────────────────────────
  CPU  [█████░░░░░░░░░░░░░░░░░░░░░░░]  21.1% ▼  4c    ▄▄▆▃▂▂▃▃▃▂
  RAM  [███████████░░░░░░░░░░░░░░░░░]  7.7G/18.9G (40.5%)  ─   ▄▄▄▄▄▄▄▄▄▄▄
── THANIA SERVICES ─[proyecto: thania]──────────────────────────────────────────────────────────────────
 [✓] backend   CPU: 1.10%  RAM:  1.5G                [✓] frontend  CPU: 0.00%  RAM:  2.8G
 [✓] postgres  CPU: 0.00%  RAM:   77M                [✓] redis     CPU: 1.17%  RAM:    4M
 [✓] nginx     CPU: 0.00%  RAM:    3M                [✓] minio     CPU: 2.56%  RAM:  130M
── TOP CONSUMO (SISTEMA) ─[Rango: 1–4/25 │ ↑↓ Scroll │ 't' Alternar]────────────────────────────────────
  #  PROCESO             CPU%                         #  PROCESO             RAM     %MEM
  1. php                 25.3%                        1. next-server (v1    2.7G (14.3%)
  2. agy                  8.9%                        2. node               1.4G ( 7.1%)
  3. agy                  8.5%                        3. agy                382M ( 1.9%)
── LOGS [1:back*] 2:front 3:pg 4:redis ─[🔴 0 err  🟡 0 warn]─────────────────────────────────────[LIVE]
  GET /login 200 in 367ms (compile: 26ms, proxy.ts: 24ms, render: 317ms)
  ○ Compiling /[tenant]/[sede]/dashboard ...
  GET /ad592151-2f07-4a42-b3f7-8930ffd5dea4/dashboard 200 in 323ms
 1..4:Logs  e:Editor  /:Filtro  ↑↓:Top  PgUp/Dn:Log  t:Modo  q:Salir────────────────────────────────────
```

---

## 📦 Instalación

### Método 1: Enlace directo (Recomendado)
```bash
git clone https://github.com/russbellc/dev-monitor.git
cd dev-monitor
chmod +x install.sh && ./install.sh
```

Asegúrate de que `~/.local/bin` esté en tu `$PATH`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Método 2: Ejecución directa sin instalación
```bash
python3 monitor.py
```

---

## 🚀 Uso

### Auto-detección del proyecto actual
Ejecuta el comando dentro del directorio de cualquier proyecto que use Docker:
```bash
dev-monitor
```

### Especificar proyecto manualmente
```bash
dev-monitor --project vitalab
dev-monitor -p thania
```

### Ver todos los contenedores Docker del servidor
```bash
dev-monitor --all
```

---

## ⌨️ Atajos de Teclado

| Tecla | Acción |
|---|---|
| **`1` .. `4`** | Alternar instantáneamente entre los contenedores de logs del proyecto |
| **`e` / `c`** | Abrir **Modo Editor** para activar/desactivar componentes |
| **`/`** | Activar búsqueda/filtro de texto en los logs en vivo |
| **`c`** | Limpiar el filtro de logs activo |
| **`t`** | Alternar tablas TOP entre **Procesos del Sistema** y **Contenedores Docker** |
| **`↑` / `↓`** *(o `j`/`k`)* | Scroll en las tablas de mayor consumo TOP |
| **`PgUp` / `PgDn`** | Scroll en el historial de logs |
| **`Home` / `End`** *(o `G`)* | Ir al inicio del log o regresar al tiempo real (**`LIVE`**) |
| **`r`** | Resetear contadores de errores y estadísticas |
| **`q` / `ESC`** | Salir |

---

## 📄 Licencia

Distribuido bajo la Licencia **MIT**. Consulta `LICENSE` para más información.
