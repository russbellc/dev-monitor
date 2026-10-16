#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  DEV MONITOR TUI — Universal Realtime Resources & Docker Monitor         ║
║  Zero-Lag UI · Auto-Project Detection · Multi-Logs · Editor · Sparklines ║
╚══════════════════════════════════════════════════════════════════════════╝

Uso:
  dev-monitor                      # Auto-detecta el proyecto en el directorio actual
  dev-monitor --project thania     # Monitorea un proyecto compose específico
  dev-monitor --all                # Muestra todos los contenedores docker del host

Teclas dentro del monitor:
  1 .. 4   = Switch instantáneo entre contenedores del proyecto activo
  e / c    = Modo Editor (Personalizar / ocultar componentes)
  /        = Filtrar texto en Logs en vivo (Enter: buscar | 'c': limpiar)
  t        = Alternar Top: Procesos del Sistema vs Contenedores Docker
  ↑ / ↓    = Scroll en Tablas Top (o j / k)
  PgUp/PgDn= Scroll en Logs (Home: inicio, End / G: volver a tiempo real)
  r        = Resetear estadísticas y contadores
  q / ESC  = Salir
"""

import argparse
import curses
import json
import locale
import os
import re
import socket
import subprocess
import sys
import threading
import time
from collections import deque

VERSION = "1.0.0"

try:
    locale.setlocale(locale.LC_ALL, '')
except Exception:
    pass

# ── Configuración persistente ─────────────────────────────────────────────────
CONFIG_FILE = os.path.expanduser("~/.dev_monitor_config.json")

DEFAULT_CONFIG = {
    "show_header": True,
    "show_resources": True,
    "show_sparklines": True,
    "show_project_services": True,
    "show_top_tables": True,
    "show_logs": True,
    "log_filter": "",
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                cfg = DEFAULT_CONFIG.copy()
                cfg.update(data)
                return cfg
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

config = load_config()

# ── Detección dinámica del Proyecto ───────────────────────────────────────────
def detect_project_name(target_dir, explicit_project=None):
    if explicit_project:
        return explicit_project.strip()

    # 1. Variable de entorno
    env_proj = os.environ.get("DEV_PROJECT")
    if env_proj:
        return env_proj.strip()

    # 2. Archivo .env local con COMPOSE_PROJECT_NAME
    env_file = os.path.join(target_dir, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r") as f:
                for line in f:
                    if line.startswith("COMPOSE_PROJECT_NAME="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
        except Exception:
            pass

    # 3. docker-compose.yml con 'name:' en la raíz
    for compose_file in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
        cp_path = os.path.join(target_dir, compose_file)
        if os.path.exists(cp_path):
            try:
                with open(cp_path, "r") as f:
                    for line in f:
                        if line.startswith("name:"):
                            val = line.split(":", 1)[1].strip().strip('"').strip("'")
                            if val:
                                return val
            except Exception:
                pass

    # 4. Nombre de la carpeta actual (con alias comunes)
    folder_name = os.path.basename(os.path.abspath(target_dir)).lower()
    if folder_name in ["03medical_app", "thania"]:
        return "thania"

    return folder_name

# ── Variables de Ejecución y Estado Global ─────────────────────────────────────
running = True
view_mode = "system"       # 'system' | 'docker'
top_offset = 0
log_offset = 0             # 0 = LIVE
error_count = 0
warn_count = 0

active_project = "auto"
project_containers = []    # nombres de contenedores asociados al proyecto
current_container = ""     # contenedor activo en logs
filter_query = config.get("log_filter", "")
filter_mode_active = False
filter_input_buffer = ""
editor_mode_active = False
editor_cursor = 0

log_buffer = deque(maxlen=600)
cpu_history = deque(maxlen=40)
mem_history = deque(maxlen=40)

lock_metrics = threading.Lock()
lock_logs = threading.Lock()

shared_docker_by_cpu = []
shared_docker_by_mem = []
shared_project_status = {}
shared_host_top_cpu = []
shared_host_top_mem = []

SPARK_CHARS = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]


# ── Helpers Métricas Rápidas (/proc en RAM kernel < 0.1ms) ─────────────────────
def get_uptime() -> str:
    try:
        with open("/proc/uptime") as f:
            secs = float(f.read().split()[0])
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        return f"{h}h {m:02d}m"
    except Exception:
        return "n/a"

def get_loadavg() -> str:
    try:
        with open("/proc/loadavg") as f:
            p = f.read().split()
        return f"{p[0]} {p[1]} {p[2]}"
    except Exception:
        return "n/a"

def get_system_cpu(prev):
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        parts = [float(x) for x in line.split()[1:8]]
        idle = parts[3] + parts[4]
        total = sum(parts)
        if prev is None:
            return 0.0, (idle, total)
        d_idle = idle - prev[0]
        d_total = total - prev[1]
        pct = max(0.0, min(100.0, (1.0 - d_idle / d_total) * 100.0)) if d_total > 0 else 0.0
        return pct, (idle, total)
    except Exception:
        return 0.0, prev

def get_system_mem():
    try:
        mi = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                mi[k.strip()] = int(v.split()[0])
        total_kb = mi.get("MemTotal", 1)
        avail_kb = mi.get("MemAvailable", 0)
        used_kb = total_kb - avail_kb
        total_g = total_kb / 1_048_576
        used_g = used_kb / 1_048_576
        pct = (used_kb / total_kb) * 100.0
        return used_g, total_g, pct
    except Exception:
        return 0.0, 1.0, 0.0

def parse_mem_str(m: str) -> float:
    try:
        val = m.split('/')[0].strip()
        nums = re.findall(r"[\d\.]+", val)
        if not nums:
            return 0.0
        num = float(nums[0])
        if 'GiB' in val or 'GB' in val:
            return num * 1024
        if 'MiB' in val or 'MB' in val:
            return num
        if 'KiB' in val or 'KB' in val:
            return num / 1024
        return num
    except Exception:
        return 0.0

def parse_pct(s: str) -> float:
    try:
        return float(s.replace('%', '').strip())
    except Exception:
        return 0.0


# ── Background Worker (Telemetría ps & docker stats sin lag) ──────────────────
def metrics_background_worker():
    global running, shared_host_top_cpu, shared_host_top_mem
    global shared_docker_by_cpu, shared_docker_by_mem, shared_project_status
    global project_containers, current_container

    while running:
        # 1. Top de procesos del sistema Linux
        try:
            res_cpu = subprocess.run(
                ["ps", "-eo", "pid,%cpu,%mem,rss,comm", "--sort=-%cpu", "--no-headers"],
                capture_output=True, text=True, timeout=2.0
            )
            res_mem = subprocess.run(
                ["ps", "-eo", "pid,%cpu,%mem,rss,comm", "--sort=-%mem", "--no-headers"],
                capture_output=True, text=True, timeout=2.0
            )
            h_cpu = []
            for ln in res_cpu.stdout.strip().splitlines()[:25]:
                p = ln.split(None, 4)
                if len(p) >= 5:
                    rss_mb = int(p[3]) / 1024
                    mem_s = f"{rss_mb/1024:.1f}G" if rss_mb >= 1024 else f"{rss_mb:.0f}M"
                    h_cpu.append({
                        "pid": p[0], "comm": p[4][:20], "cpu": float(p[1]),
                        "cpu_s": f"{float(p[1]):.1f}%", "mem_p": float(p[2]), "mem_s": mem_s
                    })
            h_mem = []
            for ln in res_mem.stdout.strip().splitlines()[:25]:
                p = ln.split(None, 4)
                if len(p) >= 5:
                    rss_mb = int(p[3]) / 1024
                    mem_s = f"{rss_mb/1024:.1f}G" if rss_mb >= 1024 else f"{rss_mb:.0f}M"
                    h_mem.append({
                        "pid": p[0], "comm": p[4][:20], "cpu": float(p[1]),
                        "cpu_s": f"{float(p[1]):.1f}%", "mem_p": float(p[2]), "mem_s": mem_s
                    })
        except Exception:
            h_cpu, h_mem = [], []

        # 2. Descubrimiento de contenedores y estadísticas Docker
        try:
            # Obtener nombres, labels de proyecto y métricas
            res_labels = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}|{{.Label \"com.docker.compose.project\"}}"],
                capture_output=True, text=True, timeout=2.0
            )
            container_project_map = {}
            for ln in res_labels.stdout.strip().splitlines():
                if "|" in ln:
                    cname, cproj = ln.split("|", 1)
                    container_project_map[cname.strip()] = cproj.strip().lower()

            res_dock = subprocess.run(
                ["docker", "stats", "--no-stream", "--format",
                 "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}"],
                capture_output=True, text=True, timeout=3.5
            )
            d_items = []
            for ln in res_dock.stdout.strip().splitlines():
                if "|" not in ln:
                    continue
                p = ln.split("|")
                if len(p) < 3:
                    continue
                cname = p[0].strip()
                mem_mib = parse_mem_str(p[2])
                mem_s = f"{mem_mib/1024:.1f}G" if mem_mib >= 1024 else f"{mem_mib:.0f}M"
                d_items.append({
                    "name": cname,
                    "project": container_project_map.get(cname, ""),
                    "cpu_pct": parse_pct(p[1]),
                    "cpu_s": p[1].strip(),
                    "mem_mib": mem_mib,
                    "mem_s": mem_s,
                    "mem_p": parse_pct(p[3]) if len(p) > 3 else 0.0,
                })

            by_cpu = sorted(d_items, key=lambda x: x["cpu_pct"], reverse=True)
            by_mem = sorted(d_items, key=lambda x: x["mem_mib"], reverse=True)

            # Filtrar contenedores relevantes para este proyecto
            p_lower = active_project.lower()
            matched = []
            if p_lower != "all":
                for item in d_items:
                    c_proj = item["project"]
                    c_name = item["name"].lower()
                    if c_proj == p_lower or (p_lower in c_name and c_name != "dev-monitor"):
                        matched.append(item["name"])

            # Si el proyecto es thania o si no encontró por label directo, fallback inteligente
            if not matched and p_lower == "thania":
                for item in d_items:
                    if item["name"].startswith("medical_"):
                        matched.append(item["name"])

            # Si no hay coincidencias de proyecto, mostrar los primeros contenedores activos
            if not matched:
                matched = [x["name"] for x in by_mem[:6]]

            # Ordenar para consistencia
            matched.sort()
            project_containers = matched

            # Si no hay contenedor de logs seteado, asignar el primero
            if not current_container and matched:
                current_container = matched[0]

            # Mapeo de estado para la matriz de servicios
            by_name = {d["name"]: d for d in d_items}
            proj_st = {}
            for c in matched:
                if c in by_name:
                    d = by_name[c]
                    proj_st[c] = {"up": True, "cpu": d["cpu_s"], "mem": d["mem_s"]}
                else:
                    proj_st[c] = {"up": False, "cpu": "─", "mem": "OFF"}
        except Exception:
            by_cpu, by_mem, proj_st = [], [], {}

        with lock_metrics:
            shared_host_top_cpu = h_cpu
            shared_host_top_mem = h_mem
            shared_docker_by_cpu = by_cpu
            shared_docker_by_mem = by_mem
            shared_project_status = proj_st

        time.sleep(2.0)


# ── Worker de Logs Reactivo con Cambio Instantáneo ────────────────────────────
log_proc = None
restart_log_event = threading.Event()

def docker_logs_worker():
    global running, error_count, warn_count, current_container, log_proc

    while running:
        if not current_container:
            time.sleep(0.5)
            continue

        container_to_read = current_container
        restart_log_event.clear()

        with lock_logs:
            log_buffer.clear()
            log_buffer.append(f"── Conectando a logs de [{container_to_read}] ──")

        cmd = ["docker", "logs", "-f", "--tail", "60", container_to_read]
        try:
            log_proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
        except Exception as e:
            with lock_logs:
                log_buffer.append(f"[Error conectando a logs de {container_to_read}: {e}]")
            time.sleep(1.0)
            continue

        while running and not restart_log_event.is_set():
            if log_proc.poll() is not None:
                time.sleep(0.4)
                break

            line = log_proc.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue

            line = line.rstrip()
            ll = line.lower()
            with lock_logs:
                log_buffer.append(line)
                if any(x in ll for x in ["error", "exception", "failed", "fatal", "500"]):
                    error_count += 1
                elif any(x in ll for x in ["warn", "warning", "429", "timeout"]):
                    warn_count += 1

        if log_proc and log_proc.poll() is None:
            try:
                log_proc.kill()
                log_proc.wait(timeout=0.5)
            except Exception:
                pass


# ── Renderizado y Primitivas Curses ───────────────────────────────────────────
def safe_add(scr, y, x, s, attr=0):
    my, mx = scr.getmaxyx()
    if y < 0 or y >= my or x >= mx or x < 0:
        return
    avail = mx - x - 1
    if avail <= 0:
        return
    try:
        scr.addstr(y, x, s[:avail], attr)
    except curses.error:
        pass

def hline(scr, y, char="─", cp=6):
    _, mx = scr.getmaxyx()
    safe_add(scr, y, 0, char * mx, curses.color_pair(cp))

def section_hdr(scr, y, title, tag_info="", cp_title=4):
    _, mx = scr.getmaxyx()
    safe_add(scr, y, 0, "─" * mx, curses.color_pair(6) | curses.A_DIM)
    safe_add(scr, y, 2, f" {title} ", curses.color_pair(cp_title) | curses.A_BOLD)
    if tag_info and len(title) + len(tag_info) + 8 < mx:
        safe_add(scr, y, len(title) + 5, f"[{tag_info}]", curses.color_pair(6) | curses.A_DIM)

def draw_bar(pct, width):
    filled = max(0, min(width, int(pct / 100.0 * width)))
    if pct < 50:
        cp = curses.color_pair(1)
    elif pct < 80:
        cp = curses.color_pair(2)
    else:
        cp = curses.color_pair(3)
    return "█" * filled, "░" * (width - filled), cp

def render_sparkline(history, width=15):
    if not history or width <= 0:
        return ""
    vals = list(history)[-width:]
    chars = []
    for v in vals:
        idx = min(len(SPARK_CHARS) - 1, max(0, int(v / 100.0 * len(SPARK_CHARS))))
        chars.append(SPARK_CHARS[idx])
    return "".join(chars)

def trend_char(curr, prev, thr):
    if curr > prev + thr:
        return "▲", curses.color_pair(3)
    if curr < prev - thr:
        return "▼", curses.color_pair(1)
    return "─", curses.color_pair(6)

def log_style(line):
    ll = line.lower()
    if any(x in ll for x in ["error", "exception", "failed", "fatal", "500"]):
        return curses.color_pair(3) | curses.A_BOLD
    if any(x in ll for x in ["warn", "warning", "429", "timeout"]):
        return curses.color_pair(2)
    if any(x in ll for x in ["successfully started", "listening on", "ready in"]):
        return curses.color_pair(1) | curses.A_BOLD
    if "prisma:query" in ll:
        return curses.color_pair(6) | curses.A_DIM
    if any(x in ll for x in ["200", "201", "204"]):
        return curses.color_pair(1)
    if any(x in ll for x in ["401", "403", "404"]):
        return curses.color_pair(2)
    if line.startswith("── Conectando"):
        return curses.color_pair(4) | curses.A_BOLD
    return curses.color_pair(5)

def clamp(s, w):
    if len(s) > w:
        return s[:max(0, w - 1)] + "…"
    return s

def simplify_container_name(name, proj):
    s = name
    p = proj.lower()
    if s.startswith("medical_"):
        s = s.replace("medical_", "")
    elif s.startswith(p + "-"):
        s = s[len(p)+1:]
    elif s.startswith(p + "_"):
        s = s[len(p)+1:]
    return s[:12]


# ── Menú Editor Modal ─────────────────────────────────────────────────────────
EDITOR_ITEMS = [
    ("show_header",           "1", "Barra Superior (Host, Uptime, Reloj, Carga)"),
    ("show_resources",        "2", "Medidores Generales CPU & Memoria RAM"),
    ("show_sparklines",       "3", "Gráfico Sparkline en vivo (Tendencia)"),
    ("show_project_services", "4", "Matriz de Contenedores del Proyecto"),
    ("show_top_tables",       "5", "Tablas de Mayor Consumo Top CPU / RAM"),
    ("show_logs",             "6", "Panel de Logs de Docker en Vivo"),
]

def draw_editor_modal(stdscr, max_y, max_x, cursor_idx):
    box_w = min(66, max_x - 4)
    box_h = len(EDITOR_ITEMS) + 6
    start_y = max(1, (max_y - box_h) // 2)
    start_x = max(1, (max_x - box_w) // 2)

    for row in range(box_h):
        safe_add(stdscr, start_y + row, start_x, " " * box_w, curses.color_pair(5))

    border_cp = curses.color_pair(4) | curses.A_BOLD
    safe_add(stdscr, start_y, start_x, "┌" + "─" * (box_w - 2) + "┐", border_cp)
    safe_add(stdscr, start_y + 1, start_x, "│", border_cp)
    safe_add(stdscr, start_y + 1, start_x + 2, "⚙  MODO EDITOR DE VISTA (Personalizar Widgets)", curses.color_pair(4) | curses.A_BOLD)
    safe_add(stdscr, start_y + 1, start_x + box_w - 1, "│", border_cp)
    safe_add(stdscr, start_y + 2, start_x, "├" + "─" * (box_w - 2) + "┤", border_cp)

    for idx, (key, num_key, desc) in enumerate(EDITOR_ITEMS):
        is_on = config.get(key, True)
        status_box = "[✓] ACTIVO " if is_on else "[ ] OCULTO "
        box_attr = curses.color_pair(1) | curses.A_BOLD if is_on else curses.color_pair(6) | curses.A_DIM
        line_y = start_y + 3 + idx
        is_cursor = (idx == cursor_idx)

        prefix = " > " if is_cursor else "   "
        pref_attr = curses.color_pair(7) | curses.A_BOLD if is_cursor else curses.color_pair(5)

        safe_add(stdscr, line_y, start_x, "│", border_cp)
        safe_add(stdscr, line_y, start_x + 2, f"{prefix}{num_key}. {status_box}", box_attr)
        safe_add(stdscr, line_y, start_x + 20, desc[:box_w - 22], pref_attr)
        safe_add(stdscr, line_y, start_x + box_w - 1, "│", border_cp)

    safe_add(stdscr, start_y + box_h - 2, start_x, "├" + "─" * (box_w - 2) + "┤", border_cp)
    safe_add(stdscr, start_y + box_h - 1, start_x, "│", border_cp)
    footer_modal = " Espacio/Enter: Conmutar │ 1..6: Directo │ q/Esc/e: Guardar"
    safe_add(stdscr, start_y + box_h - 1, start_x + 2, footer_modal[:box_w - 4], curses.color_pair(5))
    safe_add(stdscr, start_y + box_h - 1, start_x + box_w - 1, "│", border_cp)
    safe_add(stdscr, start_y + box_h, start_x, "└" + "─" * (box_w - 2) + "┘", border_cp)


# ── Bucle Principal Curses ────────────────────────────────────────────────────
def run_monitor(stdscr):
    global running, view_mode, top_offset, log_offset, error_count, warn_count
    global current_container, filter_query, filter_mode_active, filter_input_buffer
    global editor_mode_active, editor_cursor, config, log_proc, active_project

    curses.curs_set(0)
    curses.use_default_colors()
    stdscr.nodelay(True)
    stdscr.keypad(True)
    stdscr.timeout(100)

    curses.init_pair(1,  curses.COLOR_GREEN,   -1)
    curses.init_pair(2,  curses.COLOR_YELLOW,  -1)
    curses.init_pair(3,  curses.COLOR_RED,     -1)
    curses.init_pair(4,  curses.COLOR_CYAN,    -1)
    curses.init_pair(5,  curses.COLOR_WHITE,   -1)
    curses.init_pair(6,  curses.COLOR_WHITE,   -1)
    curses.init_pair(7,  curses.COLOR_MAGENTA, -1)
    curses.init_pair(8,  curses.COLOR_BLACK,   curses.COLOR_CYAN)
    curses.init_pair(9,  curses.COLOR_BLACK,   curses.COLOR_GREEN)
    curses.init_pair(10, curses.COLOR_BLACK,   curses.COLOR_RED)

    t_metrics = threading.Thread(target=metrics_background_worker, daemon=True)
    t_metrics.start()

    t_logs = threading.Thread(target=docker_logs_worker, daemon=True)
    t_logs.start()

    prev_stat = None
    prev_cpu = 0.0
    prev_mem = 0.0
    hostname = socket.gethostname()
    num_cores = os.cpu_count() or 4
    last_ui_calc = 0.0

    while running:
        ch = stdscr.getch()

        if filter_mode_active:
            if ch in [10, 13]:   # ENTER
                filter_mode_active = False
                filter_query = filter_input_buffer.strip()
                config["log_filter"] = filter_query
                save_config(config)
            elif ch in [27]:      # ESC
                filter_mode_active = False
                filter_input_buffer = ""
            elif ch in [curses.KEY_BACKSPACE, 127, 8]:
                filter_input_buffer = filter_input_buffer[:-1]
            elif 32 <= ch <= 126:
                filter_input_buffer += chr(ch)
            continue

        if editor_mode_active:
            if ch in [ord('q'), ord('Q'), ord('e'), ord('E'), 27]:
                editor_mode_active = False
                save_config(config)
            elif ch in [curses.KEY_UP, ord('k')]:
                editor_cursor = max(0, editor_cursor - 1)
            elif ch in [curses.KEY_DOWN, ord('j')]:
                editor_cursor = min(len(EDITOR_ITEMS) - 1, editor_cursor + 1)
            elif ch in [ord(' '), 10, 13]:
                key = EDITOR_ITEMS[editor_cursor][0]
                config[key] = not config.get(key, True)
                save_config(config)
            elif ord('1') <= ch <= ord('6'):
                idx = ch - ord('1')
                if idx < len(EDITOR_ITEMS):
                    key = EDITOR_ITEMS[idx][0]
                    config[key] = not config.get(key, True)
                    save_config(config)
            continue

        # Teclas normales
        if ch in [ord('q'), ord('Q')]:
            running = False
            break
        elif ch in [ord('e'), ord('E')]:
            editor_mode_active = True
        elif ch in [ord('/'), ord('F')]:
            filter_mode_active = True
            filter_input_buffer = filter_query
        elif ch in [ord('c'), ord('C')]:
            filter_query = ""
            config["log_filter"] = ""
            save_config(config)
        elif ch in [ord('t'), ord('T'), 9]:
            view_mode = "docker" if view_mode == "system" else "system"
            top_offset = 0
        elif ord('1') <= ch <= ord('6'):
            c_idx = ch - ord('1')
            if c_idx < len(project_containers):
                target = project_containers[c_idx]
                if target != current_container:
                    current_container = target
                    log_offset = 0
                    restart_log_event.set()
                    if log_proc and log_proc.poll() is None:
                        try:
                            log_proc.kill()
                        except Exception:
                            pass
        elif ch in [curses.KEY_DOWN, ord('j')]:
            top_offset += 1
        elif ch in [curses.KEY_UP, ord('k')]:
            top_offset = max(0, top_offset - 1)
        elif ch in [curses.KEY_NPAGE]:
            log_offset = max(0, log_offset - 6)
        elif ch in [curses.KEY_PPAGE]:
            log_offset += 6
        elif ch in [curses.KEY_END, ord('G')]:
            log_offset = 0
        elif ch in [curses.KEY_HOME, ord('g')]:
            log_offset = 300
        elif ch in [ord('r'), ord('R')]:
            top_offset = 0
            log_offset = 0
            error_count = 0
            warn_count = 0

        now = time.time()
        max_y, max_x = stdscr.getmaxyx()

        if max_y < 12 or max_x < 48:
            stdscr.clear()
            safe_add(stdscr, 0, 0, "[ Terminal muy pequeña ]", curses.color_pair(2))
            stdscr.refresh()
            continue

        if now - last_ui_calc > 0.8:
            cpu_pct, prev_stat = get_system_cpu(prev_stat)
            used_g, total_g, mem_pct = get_system_mem()
            cpu_history.append(cpu_pct)
            mem_history.append(mem_pct)
            cpu_tr, cpu_tcp = trend_char(cpu_pct, prev_cpu, 1.0)
            mem_tr, mem_tcp = trend_char(mem_pct, prev_mem, 0.5)
            prev_cpu, prev_mem = cpu_pct, mem_pct
            last_ui_calc = now

        with lock_metrics:
            if view_mode == "system":
                list_cpu = list(shared_host_top_cpu)
                list_mem = list(shared_host_top_mem)
            else:
                list_cpu = list(shared_docker_by_cpu)
                list_mem = list(shared_docker_by_mem)
            proj_st = dict(shared_project_status)

        stdscr.erase()
        y = 0

        # ── 1. HEADER ─────────────────────────────────────────────────────────
        if config.get("show_header", True):
            now_s = time.strftime("%Y-%m-%d  %H:%M:%S")
            uptime = get_uptime()
            load = get_loadavg()
            hdr_l = f"  ⬡ DEV MONITOR  │  {hostname}  │  up {uptime}"
            hdr_r = f"load: {load}  {now_s}  "
            hdr_cp = curses.color_pair(8) | curses.A_BOLD
            safe_add(stdscr, y, 0, " " * max_x, hdr_cp)
            safe_add(stdscr, y, 0, hdr_l, hdr_cp)
            rx = max(len(hdr_l) + 2, max_x - len(hdr_r) - 1)
            safe_add(stdscr, y, rx, hdr_r, hdr_cp)
            y += 1

        # ── 2. METRICAS CPU / RAM + SPARKLINES ────────────────────────────────
        if config.get("show_resources", True):
            hline(stdscr, y)
            y += 1
            has_spark = config.get("show_sparklines", True)
            spark_w = 12 if max_x >= 95 else (8 if max_x >= 75 else 0)

            extra_meta = 35 + (spark_w + 3 if (has_spark and spark_w > 0) else 0)
            bar_w = min(28, max(8, max_x - extra_meta))

            f_cpu, e_cpu, bcp_cpu = draw_bar(prev_cpu, bar_w)
            safe_add(stdscr, y, 0, "  CPU  [", curses.color_pair(5))
            safe_add(stdscr, y, 8, f_cpu, bcp_cpu | curses.A_BOLD)
            safe_add(stdscr, y, 8 + len(f_cpu), e_cpu, curses.color_pair(6) | curses.A_DIM)
            pos_x = 8 + bar_w
            safe_add(stdscr, y, pos_x, f"] {prev_cpu:5.1f}% ", curses.color_pair(5))
            safe_add(stdscr, y, pos_x + 9, cpu_tr, cpu_tcp | curses.A_BOLD)
            safe_add(stdscr, y, pos_x + 11, f" {num_cores}c", curses.color_pair(6) | curses.A_DIM)

            if has_spark and spark_w > 0:
                spk = render_sparkline(cpu_history, spark_w)
                safe_add(stdscr, y, pos_x + 16, f" {spk}", bcp_cpu)
            y += 1

            f_ram, e_ram, bcp_ram = draw_bar(prev_mem, bar_w)
            safe_add(stdscr, y, 0, "  RAM  [", curses.color_pair(5))
            safe_add(stdscr, y, 8, f_ram, bcp_ram | curses.A_BOLD)
            safe_add(stdscr, y, 8 + len(f_ram), e_ram, curses.color_pair(6) | curses.A_DIM)
            pos_x = 8 + bar_w
            safe_add(stdscr, y, pos_x, f"] {used_g:4.1f}G/{total_g:4.1f}G ", curses.color_pair(5))
            safe_add(stdscr, y, pos_x + 14, f"({prev_mem:4.1f}%)", bcp_ram | curses.A_BOLD)
            safe_add(stdscr, y, pos_x + 22, f" {mem_tr}", mem_tcp | curses.A_BOLD)

            if has_spark and spark_w > 0:
                spk = render_sparkline(mem_history, spark_w)
                safe_add(stdscr, y, pos_x + 26, f" {spk}", bcp_ram)
            y += 1

        # ── 3. PROJECT SERVICES RESPONSIVE GRID ───────────────────────────────
        if config.get("show_project_services", True) and y < max_y - 6:
            p_display = active_project.upper()
            section_hdr(stdscr, y, f"{p_display} SERVICES", f"proyecto: {active_project}")
            y += 1

            if max_x >= 135:
                grid_cols = 3
            elif max_x >= 68:
                grid_cols = 2
            else:
                grid_cols = 1

            col_width = max_x // grid_cols
            items = list(project_containers)
            grid_rows = (len(items) + grid_cols - 1) // grid_cols if items else 0

            if not items:
                safe_add(stdscr, y, 2, f"(No se detectaron contenedores activos para '{active_project}')", curses.color_pair(6) | curses.A_DIM)
                y += 1
            else:
                for r in range(grid_rows):
                    if y >= max_y - 4:
                        break
                    for c_idx in range(grid_cols):
                        item_idx = r * grid_cols + c_idx
                        if item_idx >= len(items):
                            break
                        c_name = items[item_idx]
                        short_name = simplify_container_name(c_name, active_project)
                        st = proj_st.get(c_name, {"up": False, "cpu": "─", "mem": "─"})
                        cell_x = c_idx * col_width + 1

                        if st.get("up", False):
                            badge = "[✓]"
                            badge_attr = curses.color_pair(1) | curses.A_BOLD
                            if col_width >= 42:
                                info = f" {short_name:<10} CPU:{st['cpu']:>6}  RAM:{st['mem']:>6}"
                            elif col_width >= 30:
                                info = f" {short_name:<9} {st['cpu']:>5} {st['mem']:>5}"
                            else:
                                info = f" {short_name:<8} {st['mem']:>5}"
                            safe_add(stdscr, y, cell_x, badge, badge_attr)
                            safe_add(stdscr, y, cell_x + 3, clamp(info, col_width - 4), curses.color_pair(5))
                        else:
                            badge = "[✗]"
                            badge_attr = curses.color_pair(3) | curses.A_BOLD
                            info = f" {short_name:<10} OFFLINE"
                            safe_add(stdscr, y, cell_x, badge, badge_attr)
                            safe_add(stdscr, y, cell_x + 3, clamp(info, col_width - 4), curses.color_pair(3))
                    y += 1

        # ── 4. TOP PROCESOS RESPONSIVE ────────────────────────────────────────
        if config.get("show_top_tables", True) and y < max_y - 6:
            tag = "SISTEMA" if view_mode == "system" else "DOCKER"
            total_items = max(len(list_cpu), len(list_mem))
            top_rows_avail = 5 if max_y >= 32 else (4 if max_y >= 26 else 3)
            top_offset = min(top_offset, max(0, total_items - top_rows_avail))
            rng = f"{top_offset+1}–{min(top_offset + top_rows_avail, total_items)}/{total_items}"

            section_hdr(stdscr, y, f"TOP CONSUMO ({tag})", f"Rango: {rng} │ ↑↓ Scroll │ 't' Alternar")
            y += 1

            half_w = max_x // 2
            is_narrow_screen = max_x < 70

            if not is_narrow_screen:
                hdr_c = "  #  PROCESO             CPU%"
                hdr_m = "  #  PROCESO             RAM     %MEM"
                safe_add(stdscr, y, 0, clamp(hdr_c, half_w), curses.color_pair(6) | curses.A_DIM)
                safe_add(stdscr, y, half_w, clamp(hdr_m, max_x - half_w), curses.color_pair(6) | curses.A_DIM)
                y += 1

                for i in range(top_rows_avail):
                    if y >= max_y - 4:
                        break
                    idx = top_offset + i
                    rank_attr = curses.color_pair(7) | curses.A_BOLD if idx == 0 else curses.color_pair(5)

                    if idx < len(list_cpu):
                        p = list_cpu[idx]
                        nm = p["comm"] if view_mode == "system" else p["name"]
                        vs = p["cpu_s"]
                        pv = p["cpu"] if view_mode == "system" else p["cpu_pct"]
                        vcp = curses.color_pair(1) if pv < 40 else (curses.color_pair(2) if pv < 75 else curses.color_pair(3))
                        safe_add(stdscr, y, 0, f" {idx+1:>2}. ", rank_attr)
                        name_w = max(10, min(18, half_w - 14))
                        safe_add(stdscr, y, 5, clamp(f"{nm:<{name_w}}", name_w), curses.color_pair(5))
                        safe_add(stdscr, y, 5 + name_w + 1, f"{vs:>6}", vcp | curses.A_BOLD)

                    if idx < len(list_mem):
                        p = list_mem[idx]
                        nm = p["comm"] if view_mode == "system" else p["name"]
                        vs = p["mem_s"]
                        vp = p["mem_p"] if view_mode == "system" else p.get("mem_p", 0.0)
                        vcp = curses.color_pair(1) if vp < 6 else (curses.color_pair(2) if vp < 15 else curses.color_pair(3))
                        safe_add(stdscr, y, half_w, f" {idx+1:>2}. ", rank_attr)
                        name_w = max(10, min(16, (max_x - half_w) - 18))
                        safe_add(stdscr, y, half_w + 5, clamp(f"{nm:<{name_w}}", name_w), curses.color_pair(5))
                        safe_add(stdscr, y, half_w + 5 + name_w + 1, f"{vs:>6}", vcp | curses.A_BOLD)
                        safe_add(stdscr, y, half_w + 5 + name_w + 8, f"({vp:4.1f}%)", curses.color_pair(6) | curses.A_DIM)
                    y += 1
            else:
                safe_add(stdscr, y, 0, "  #  PROCESO             CPU%     RAM", curses.color_pair(6) | curses.A_DIM)
                y += 1
                for i in range(top_rows_avail):
                    if y >= max_y - 4:
                        break
                    idx = top_offset + i
                    if idx < len(list_cpu):
                        p = list_cpu[idx]
                        nm = p["comm"] if view_mode == "system" else p["name"]
                        vs = p["cpu_s"]
                        ms = p.get("mem_s", "─")
                        safe_add(stdscr, y, 0, f" {idx+1:>2}. ", curses.color_pair(5))
                        safe_add(stdscr, y, 5, clamp(f"{nm:<16}", 16), curses.color_pair(5))
                        safe_add(stdscr, y, 22, f"{vs:>6}", curses.color_pair(2) | curses.A_BOLD)
                        safe_add(stdscr, y, 30, f"{ms:>6}", curses.color_pair(6))
                    y += 1

        # ── 5. PANEL DE LOGS (DINÁMICO CON 1..4) ──────────────────────────────
        if config.get("show_logs", True) and y < max_y - 2:
            avail_log_lines = max_y - y - 1

            with lock_logs:
                raw_logs = list(log_buffer)

            if filter_query:
                fq_lower = filter_query.lower()
                filtered_logs = [ln for ln in raw_logs if fq_lower in ln.lower()]
            else:
                filtered_logs = raw_logs

            total_filtered = len(filtered_logs)
            log_offset = min(log_offset, max(0, total_filtered - avail_log_lines))

            if log_offset == 0:
                window = filtered_logs[-avail_log_lines:] if total_filtered > avail_log_lines else filtered_logs
                status_stream = "LIVE"
                st_cp = curses.color_pair(1) | curses.A_BOLD
            else:
                end_i = total_filtered - log_offset
                start_i = max(0, end_i - avail_log_lines)
                window = filtered_logs[start_i:end_i]
                status_stream = f"HISTORICO [-{log_offset}]"
                st_cp = curses.color_pair(2) | curses.A_BOLD

            # Botones numéricos 1..4 dinámicos según los contenedores del proyecto
            btn_strs = []
            for bi, cname in enumerate(project_containers[:4]):
                s_name = simplify_container_name(cname, active_project)
                if cname == current_container:
                    btn_strs.append(f"[{bi+1}:{s_name}*]")
                else:
                    btn_strs.append(f"{bi+1}:{s_name}")

            btns_formatted = " ".join(btn_strs) if btn_strs else "(Sin contenedores)"
            title_log = f"LOGS {btns_formatted}"
            sub_log = f"🔴 {error_count} err  🟡 {warn_count} warn"
            if filter_query:
                sub_log += f" │ Filtro: '{filter_query}' ('c' borrar)"

            section_hdr(stdscr, y, title_log, sub_log)
            safe_add(stdscr, y, max_x - len(status_stream) - 3, f"[{status_stream}]", st_cp)
            y += 1

            for li, line_text in enumerate(window):
                cur_ly = y + li
                if cur_ly >= max_y - 1:
                    break
                display = line_text if len(line_text) <= max_x - 2 else line_text[:max_x - 4] + " …"
                safe_add(stdscr, cur_ly, 1, display, log_style(line_text))

        # ── 6. FOOTER ─────────────────────────────────────────────────────────
        foot_y = max_y - 1
        hline(stdscr, foot_y)

        if filter_mode_active:
            filter_prompt = f" 🔍 Buscar en Logs: {filter_input_buffer}█  (Enter: aplicar | Esc: cancelar) "
            safe_add(stdscr, foot_y, 0, filter_prompt[:max_x], curses.color_pair(8) | curses.A_BOLD)
        else:
            foot_l = f" 1..{min(4, max(1, len(project_containers)))}:Logs  e:Editor  /:Filtro  ↑↓:Top  PgUp/Dn:Log  t:Modo  q:Salir"
            safe_add(stdscr, foot_y, 0, foot_l[:max_x], curses.color_pair(5) | curses.A_BOLD)

        # ── 7. MODAL EDITOR ───────────────────────────────────────────────────
        if editor_mode_active:
            draw_editor_modal(stdscr, max_y, max_x, editor_cursor)

        stdscr.refresh()

    running = False
    if log_proc and log_proc.poll() is None:
        try:
            log_proc.kill()
        except Exception:
            pass

def main():
    global active_project
    parser = argparse.ArgumentParser(
        description="Dev Monitor TUI — Telemetría en tiempo real y logs Docker para cualquier proyecto."
    )
    parser.add_argument(
        "-p", "--project", type=str, default=None,
        help="Nombre del proyecto Compose a monitorear (ej. thania, vitalab, coolify). Por defecto auto-detecta."
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Monitorear todos los contenedores Docker del host sin filtrar por proyecto."
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"Dev Monitor v{VERSION}"
    )

    args = parser.parse_args()

    if args.all:
        active_project = "all"
    else:
        active_project = detect_project_name(os.getcwd(), args.project)

    try:
        curses.wrapper(run_monitor)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
