# Page ADMINISTRATION (/admin) : adresses du serveur (interface web,
# WebSocket des graphiques), etat du serveur (temps en ligne, clients
# connectes, base de donnees) et constantes du PC serveur (processeur,
# memoire, disque, temperature), rafraichies en direct.

from nicegui import Client, run, ui

import api
import database
import system_info
from app_config import SERVER_PORT
from layout import ADMIN_NAV_ITEMS, CARD_CLASSES, build_header, page_body, section_card
from paths import user_data_path

REFRESH_SECONDS = 2.0


def _copy_row(label: str, value: str) -> None:
    def copy() -> None:
        ui.clipboard.write(value)
        ui.notify(f"Copie : {value}", type="positive")

    with ui.row(wrap=False).classes("w-full items-center gap-3 rounded-xl bg-slate-100 dark:bg-slate-900/60 px-4 py-3"):
        ui.label(label).classes("w-40 shrink-0 text-xs font-bold uppercase tracking-wide text-slate-500")
        ui.label(value).classes("flex-1 text-xl font-mono font-bold text-slate-900 dark:text-slate-100 select-all")
        ui.button(icon="content_copy", on_click=copy).props("flat round").tooltip("Copier")


def _info_row(label: str, value: str) -> None:
    with ui.row(wrap=False).classes("w-full items-baseline justify-between gap-4 py-1"):
        ui.label(label).classes("text-sm text-slate-500")
        ui.label(value).classes("text-base font-bold text-slate-900 dark:text-slate-100 text-right")


#jauge horizontale (charge CPU, memoire, disque) : verte, orange puis rouge
def _gauge(label: str, percent: float | None, detail: str) -> None:
    color = "green" if (percent or 0) < 70 else "orange" if percent < 90 else "red"
    with ui.column().classes("w-full gap-1"):
        with ui.row(wrap=False).classes("w-full items-baseline justify-between"):
            ui.label(label).classes("text-sm text-slate-500")
            ui.label(f"{percent:.0f} %" if percent is not None else "-").classes(
                "text-lg font-bold font-mono text-slate-900 dark:text-slate-100"
            )
        ui.linear_progress(value=(percent or 0) / 100, show_value=False, color=color).props("rounded size=10px")
        ui.label(detail).classes("text-xs text-slate-400")


def build_system_page(config: dict) -> None:
    build_header(config, "admin", nav_items=ADMIN_NAV_ITEMS, tournament_selector=False)
    data_dir = user_data_path(".")

    with page_body().classes("max-w-[110rem] mx-auto"):
        ui.label("ADMINISTRATION").classes("text-2xl font-bold tracking-wide text-white mt-6")

        # --- adresses ------------------------------------------------------
        with section_card("ADRESSES DU SERVEUR", "lan"):
            ip = system_info.primary_ip()
            _copy_row("Adresse IP", ip)
            _copy_row("Interface web", f"http://{ip}:{SERVER_PORT}")
            _copy_row("WebSocket (graphiques)", f"ws://{ip}:{SERVER_PORT}{api.WEBSOCKET_PATH}")
            others = [(name, address) for name, address in system_info.local_ipv4s() if address != ip]
            if others:
                ui.label("Autres interfaces reseau du PC :").classes("text-sm text-slate-500 mt-1")
                for name, address in others:
                    _info_row(name, f"ws://{address}:{SERVER_PORT}{api.WEBSOCKET_PATH}")
            ui.label(
                "Si un autre poste n'arrive pas a se connecter, autorisez le port "
                f"{SERVER_PORT} dans le pare-feu Windows de ce PC."
            ).classes("text-xs text-slate-400")

        with ui.element("div").classes("w-full grid grid-cols-1 xl:grid-cols-2 gap-3"):
            server_card = ui.column().classes(CARD_CLASSES)
            pc_card = ui.column().classes(CARD_CLASSES)

    @ui.refreshable
    def server_status() -> None:
        snap = system_info.snapshot(data_dir)
        matches = database.list_matches()
        ui_clients = [c for c in Client.instances.values() if getattr(c, "has_socket_connection", True)]
        #base + fichiers WAL/SHM de SQLite, dans le dossier de la base
        db_size = sum(f.stat().st_size for f in database.DB_PATH.parent.glob(database.DB_PATH.name + "*")
                      if f.is_file())
        with ui.row(wrap=False).classes("w-full items-center justify-between"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("dns").classes("text-lg text-slate-500")
                ui.label("ETAT DU SERVEUR").classes("text-sm font-bold tracking-wide text-slate-500")
            ui.label("EN LIGNE").classes(
                "text-sm font-bold tracking-wide rounded-full px-4 py-1 border border-green-500 "
                "bg-green-600/20 text-green-500"
            )
        with ui.column().classes("w-full items-center gap-0 py-2"):
            ui.label("TEMPS EN LIGNE").classes("text-xs font-bold tracking-widest text-slate-500")
            ui.label(system_info.format_duration(snap["server_uptime"])).classes(
                "text-5xl font-mono font-bold text-slate-900 dark:text-slate-100"
            )
            ui.label(f"depuis le {snap['server_started'].strftime('%d/%m/%Y a %H:%M:%S')}").classes(
                "text-sm text-slate-500"
            )
        _info_row("Clients WebSocket connectes (graphiques)", str(api.connection_count()))
        _info_row("Postes ouverts sur l'interface", str(len(ui_clients)))
        _info_row("Matchs en cours", str(sum(1 for m in matches if m.status == "live")))
        _info_row("Matchs / joueurs / tournois",
                  f"{len(matches)} / {len(database.list_players())} / {len(database.list_tournaments())}")
        _info_row("Base de donnees", f"{database.DB_PATH} ({system_info.format_bytes(db_size)})")
        _info_row("Memoire utilisee par l'application", system_info.format_bytes(snap["process_memory"]))

    @ui.refreshable
    def pc_status() -> None:
        snap = system_info.snapshot(data_dir)
        temperature, source = system_info.cached_temperature()
        with ui.row().classes("items-center gap-2"):
            ui.icon("computer").classes("text-lg text-slate-500")
            ui.label("PC SERVEUR").classes("text-sm font-bold tracking-wide text-slate-500")
        _info_row("Nom du PC", snap["hostname"])
        _info_row("Systeme", snap["os"])
        _info_row("Processeur", snap["cpu_name"])
        _info_row("Coeurs / threads", f"{snap['cpu_cores']} / {snap['cpu_threads']}"
                  + (f" - {snap['cpu_freq_mhz']} MHz" if snap["cpu_freq_mhz"] else ""))
        _info_row("Allume depuis", system_info.format_duration(snap["pc_uptime"]))
        _info_row("Python", snap["python"])
        _gauge("Charge processeur", snap["cpu_percent"], f"{snap['cpu_threads']} threads")
        _gauge("Memoire", snap["ram_percent"],
               f"{system_info.format_bytes(snap['ram_used'])} / {system_info.format_bytes(snap['ram_total'])}")
        if snap["disk_percent"] is not None:
            _gauge("Disque (donnees)", snap["disk_percent"],
                   f"{system_info.format_bytes(snap['disk_used'])} / {system_info.format_bytes(snap['disk_total'])}")
        with ui.row(wrap=False).classes("w-full items-center justify-between gap-4 rounded-xl bg-slate-100 dark:bg-slate-900/60 px-4 py-3"):
            with ui.column().classes("gap-0"):
                ui.label("TEMPERATURE PROCESSEUR").classes("text-xs font-bold tracking-widest text-slate-500")
                ui.label(f"source : {source}" if temperature is not None else
                         "Non disponible : lancez LibreHardwareMonitor sur ce PC pour l'afficher").classes(
                    "text-xs text-slate-400"
                )
            color = ("text-slate-400" if temperature is None else "text-green-500" if temperature < 70
                     else "text-orange-500" if temperature < 85 else "text-red-500")
            ui.label(f"{temperature:.0f} °C" if temperature is not None else "--").classes(
                f"text-4xl font-mono font-bold {color}"
            )

    with server_card:
        server_status()
    with pc_card:
        pc_status()

    async def tick() -> None:
        server_status.refresh()
        pc_status.refresh()

    async def update_temperature() -> None:
        await run.io_bound(system_info.refresh_temperature)
        pc_status.refresh()

    ui.timer(REFRESH_SECONDS, tick)
    ui.timer(system_info.TEMPERATURE_CACHE_SECONDS, update_temperature)
    ui.timer(0.1, update_temperature, once=True)
